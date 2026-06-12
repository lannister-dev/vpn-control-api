from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from services.promo.models import PromoActivation, PromoCode
from shared.database.base_repository import BaseRepository


class PromoCodeRepository(BaseRepository[PromoCode]):
    def __init__(self, session: AsyncSession):
        super().__init__(PromoCode, session)

    async def get_by_code(self, code: str) -> PromoCode | None:
        res = await self.session.execute(
            select(PromoCode).where(func.upper(PromoCode.code) == code.upper())
        )
        return res.scalar_one_or_none()

    async def get_by_code_for_update(self, code: str) -> PromoCode | None:
        res = await self.session.execute(
            select(PromoCode)
            .where(func.upper(PromoCode.code) == code.upper())
            .with_for_update()
        )
        return res.scalar_one_or_none()

    async def list_all(self) -> list[PromoCode]:
        res = await self.session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return list(res.scalars().all())

    async def increment_activation(self, promo_code_id: UUID) -> None:
        await self.session.execute(
            sa_update(PromoCode)
            .where(PromoCode.id == promo_code_id)
            .values(activation_count=PromoCode.activation_count + 1)
        )


class PromoActivationRepository(BaseRepository[PromoActivation]):
    def __init__(self, session: AsyncSession):
        super().__init__(PromoActivation, session)

    async def count_for_user(self, promo_code_id: UUID, user_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(PromoActivation.id)).where(
                PromoActivation.promo_code_id == promo_code_id,
                PromoActivation.user_id == user_id,
            )
        )
        return int(res.scalar() or 0)

    async def list_by_promo(
        self, promo_code_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[PromoActivation], int]:
        base = select(PromoActivation).where(
            PromoActivation.promo_code_id == promo_code_id
        )
        total = (
            await self.session.execute(
                select(func.count(PromoActivation.id)).where(
                    PromoActivation.promo_code_id == promo_code_id
                )
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                base.order_by(PromoActivation.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def stats(self, promo_code_id: UUID) -> tuple[int, int, float, float]:
        row = (
            await self.session.execute(
                select(
                    func.count(PromoActivation.id),
                    func.count(func.distinct(PromoActivation.user_id)),
                    func.coalesce(func.sum(PromoActivation.discount_applied), 0),
                    func.coalesce(func.sum(PromoActivation.amount_after), 0),
                ).where(PromoActivation.promo_code_id == promo_code_id)
            )
        ).one()
        return int(row[0]), int(row[1]), float(row[2]), float(row[3])
