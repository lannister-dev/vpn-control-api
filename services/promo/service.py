from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.promo.exceptions import (
    PromoCodeExists,
    PromoExhausted,
    PromoInvalid,
    PromoNotEligible,
    PromoNotFound,
)
from services.promo.repository import (
    PromoActivationRepository,
    PromoCodeRepository,
)
from services.promo.schemas import (
    PromoActivationListOut,
    PromoActivationOut,
    PromoCodeCreateIn,
    PromoCodeListOut,
    PromoCodeOut,
    PromoCodeUpdateIn,
    PromoQuoteOut,
    PromoStatsOut,
)
from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase


class PromoService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.promo_repo = PromoCodeRepository(session)
        self.activation_repo = PromoActivationRepository(session)
        self.sub_repo = SubscriptionRepository(session)

    # ── CRUD ───────────────────────────────────────────────────

    async def create_promo(
        self, data: PromoCodeCreateIn, *, actor_admin_id: UUID | None = None
    ) -> PromoCodeOut:
        if await self.promo_repo.get_by_code(data.code) is not None:
            raise PromoCodeExists(f"Promo code {data.code} already exists")
        payload = data.model_dump()
        payload["code"] = data.code.upper()
        payload["discount_type"] = data.discount_type.value
        payload["audience"] = data.audience.value
        payload["applies_to"] = data.applies_to.value
        payload["plan_ids"] = [str(p) for p in data.plan_ids] if data.plan_ids else None
        payload["created_by_admin_id"] = actor_admin_id
        row = await self.promo_repo.create(payload)
        return PromoCodeOut.model_validate(row)

    async def list_promos(self) -> PromoCodeListOut:
        rows = await self.promo_repo.list_all()
        return PromoCodeListOut(items=[PromoCodeOut.model_validate(r) for r in rows])

    async def update_promo(
        self, promo_id: UUID, data: PromoCodeUpdateIn
    ) -> PromoCodeOut:
        existing = await self.promo_repo.get_by_id(promo_id)
        if existing is None:
            raise PromoNotFound(f"Promo {promo_id} not found")
        patch = data.model_dump(exclude_unset=True)
        for key in ("discount_type", "audience", "applies_to"):
            if patch.get(key) is not None:
                patch[key] = patch[key].value
        if "plan_ids" in patch:
            patch["plan_ids"] = (
                [str(p) for p in patch["plan_ids"]] if patch["plan_ids"] else None
            )
        row = await self.promo_repo.update_by_id(promo_id, patch)
        return PromoCodeOut.model_validate(row)

    async def delete_promo(self, promo_id: UUID) -> None:
        existing = await self.promo_repo.get_by_id(promo_id)
        if existing is None:
            raise PromoNotFound(f"Promo {promo_id} not found")
        await self.promo_repo.delete_by_id(promo_id)

    # ── Validation / quoting ───────────────────────────────────

    @staticmethod
    def _compute_discount(promo, amount: Decimal) -> Decimal:
        if promo.discount_type == "percent":
            d = (amount * promo.discount_value / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if promo.max_discount_rub is not None:
                d = min(d, promo.max_discount_rub)
        else:
            d = min(promo.discount_value, amount)
        return max(Decimal("0"), d)

    async def _check_audience(self, promo, user_id: UUID, plan_id: UUID | None) -> None:
        if promo.audience == "all":
            return
        if promo.audience == "by_plan":
            allowed = set(promo.plan_ids or [])
            if plan_id is None or str(plan_id) not in allowed:
                raise PromoNotEligible("Promo is limited to specific plans")
            return
        subs = await self.sub_repo.list_by_user_id(user_id=user_id, active_only=True)
        has_live = any(
            s.expires_at is None or s.expires_at > datetime.now(timezone.utc)
            for s in subs
        )
        if promo.audience == "no_subscription" and has_live:
            raise PromoNotEligible("Promo is only for users without an active subscription")
        if promo.audience == "has_subscription" and not has_live:
            raise PromoNotEligible("Promo requires an active subscription")

    async def validate_and_quote(
        self,
        *,
        code: str,
        user_id: UUID,
        plan_id: UUID | None,
        order_type: str,
        amount_rub: Decimal,
    ) -> PromoQuoteOut:
        promo = await self.promo_repo.get_by_code(code)
        if promo is None or not promo.is_active:
            raise PromoInvalid("Promo code not found or inactive")
        now = datetime.now(timezone.utc)
        if promo.starts_at and now < promo.starts_at:
            raise PromoInvalid("Promo is not active yet")
        if promo.expires_at and now >= promo.expires_at:
            raise PromoInvalid("Promo has expired")
        if promo.min_amount_rub is not None and amount_rub < promo.min_amount_rub:
            raise PromoInvalid("Order amount is below the promo minimum")
        if promo.applies_to == "new_purchase" and order_type != "plan_purchase":
            raise PromoNotEligible("Promo applies to new purchases only")
        if promo.applies_to == "renewal" and order_type != "subscription_renewal":
            raise PromoNotEligible("Promo applies to renewals only")
        await self._check_audience(promo, user_id, plan_id)
        if promo.max_activations is not None and promo.activation_count >= promo.max_activations:
            raise PromoExhausted("Promo activation limit reached")
        used = await self.activation_repo.count_for_user(promo.id, user_id)
        if used >= promo.max_per_user:
            raise PromoExhausted("Per-user promo limit reached")

        discount = self._compute_discount(promo, amount_rub)
        amount_after = max(Decimal("0"), amount_rub - discount)
        return PromoQuoteOut(
            code=promo.code,
            promo_code_id=promo.id,
            amount_before=amount_rub,
            discount_rub=discount,
            amount_after=amount_after,
        )

    # ── Activation ledger ──────────────────────────────────────

    async def record_activation(
        self,
        *,
        promo_code_id: UUID,
        user_id: UUID,
        order_id: UUID | None,
        amount_before: Decimal,
        discount_applied: Decimal,
        amount_after: Decimal,
    ) -> None:
        await self.activation_repo.create(
            {
                "promo_code_id": promo_code_id,
                "user_id": user_id,
                "order_id": order_id,
                "amount_before": amount_before,
                "discount_applied": discount_applied,
                "amount_after": amount_after,
            }
        )
        await self.promo_repo.increment_activation(promo_code_id)

    async def list_activations(
        self, promo_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> PromoActivationListOut:
        rows, total = await self.activation_repo.list_by_promo(
            promo_id, limit=limit, offset=offset
        )
        return PromoActivationListOut(
            items=[PromoActivationOut.model_validate(r) for r in rows], total=total
        )

    async def stats(self, promo_id: UUID) -> PromoStatsOut:
        if await self.promo_repo.get_by_id(promo_id) is None:
            raise PromoNotFound(f"Promo {promo_id} not found")
        acts, users, discount, revenue = await self.activation_repo.stats(promo_id)
        return PromoStatsOut(
            promo_code_id=promo_id,
            activations=acts,
            unique_users=users,
            total_discount_rub=Decimal(str(discount)),
            revenue_after_rub=Decimal(str(revenue)),
        )


def get_promo_service(
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> PromoService:
    return PromoService(session)
