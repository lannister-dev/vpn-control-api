from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth.admin.models import AdminUser
from services.billing.models import PaymentOrder
from services.plans.models import Plan
from services.support.constants import (
    REOPEN_WINDOW_MIN,
    SUBJECT_PREVIEW_LEN,
    BroadcastAudience,
    BroadcastStatus,
    MessageSenderKind,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from services.support.exceptions import (
    TemplateAlreadyExists,
    TemplateNotFound,
    TicketNotFound,
)
from services.support.models import (
    SupportMessage,
    SupportTicket,
)
from services.support.repository import (
    BroadcastLogRepository,
    BroadcastRepository,
    SupportAttachmentRepository,
    SupportMessageRepository,
    SupportTemplateRepository,
    SupportTicketRepository,
)
from services.support.schemas import (
    AttachmentOut,
    BroadcastAudienceCount,
    BroadcastListOut,
    BroadcastOut,
    MessageAuthorRef,
    MessageListOut,
    MessageOut,
    TemplateCreateIn,
    TemplateListOut,
    TemplateOut,
    TemplateUpdateIn,
    TicketBulkUpdateIn,
    TicketCreateIn,
    TicketListOut,
    TicketOut,
    TicketPatchIn,
    TicketStatsOut,
    TicketUserRef,
)
from services.users.models import User
from services.vpn.subscriptions.model import Subscription
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient


class SupportService:
    def __init__(self, session: AsyncSession, *, nats_client: NatsClient | None = None):
        self.session = session
        self.tickets = SupportTicketRepository(session)
        self.messages = SupportMessageRepository(session)
        self.attachments = SupportAttachmentRepository(session)
        self.templates = SupportTemplateRepository(session)
        self.broadcasts = BroadcastRepository(session)
        self.broadcast_log = BroadcastLogRepository(session)
        self._nats = nats_client

    async def list_tickets(
        self,
        *,
        search: str | None,
        status: TicketStatus | None,
        category: TicketCategory | None,
        priority: TicketPriority | None,
        assignee_admin_id: UUID | None,
        unanswered_minutes: int | None,
        limit: int,
        offset: int,
    ) -> TicketListOut:
        rows, total = await self.tickets.list_filtered(
            search=search,
            status=status,
            category=category.value if category else None,
            priority=priority.value if priority else None,
            assignee_admin_id=assignee_admin_id,
            unanswered_minutes=unanswered_minutes,
            limit=limit,
            offset=offset,
        )
        if not rows:
            return TicketListOut(items=[], total=total)

        ids = [t.id for t in rows]
        media = await self.messages.has_media_flags(ids)
        users = await self._fetch_users_with_meta([t.user_id for t in rows])
        assignees = await self._fetch_admin_usernames([t.assignee_admin_id for t in rows if t.assignee_admin_id])

        items = []
        for t in rows:
            has_media, att_count = media.get(t.id, (False, 0))
            user_ref = users.get(t.user_id) or TicketUserRef(id=t.user_id, telegram_id=0)
            items.append(
                TicketOut(
                    id=t.id,
                    subject=t.subject or "",
                    status=TicketStatus(t.status),
                    priority=TicketPriority(t.priority),
                    category=TicketCategory(t.category),
                    assignee=assignees.get(t.assignee_admin_id) if t.assignee_admin_id else None,
                    has_media=has_media,
                    attachments_count=att_count,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                    last_activity_at=t.last_activity_at,
                    user=user_ref,
                )
            )
        return TicketListOut(items=items, total=total)

    async def stats(self) -> TicketStatsOut:
        s = await self.tickets.stats()
        return TicketStatsOut(
            open=s["open"],
            unanswered=s["unanswered"],
            avg_reply_minutes=s["avg_reply_minutes"],
            avg_reply_change=None,
            closed_today=s["closed_today"],
            open_spark_24h=[],
            reply_spark_24h=[],
        )

    async def get_ticket(self, ticket_id: UUID) -> TicketOut:
        t = await self.tickets.get_by_id(ticket_id)
        if not t:
            raise TicketNotFound(str(ticket_id))
        users = await self._fetch_users_with_meta([t.user_id])
        media = await self.messages.has_media_flags([t.id])
        has_media, att_count = media.get(t.id, (False, 0))
        assignees = await self._fetch_admin_usernames([t.assignee_admin_id] if t.assignee_admin_id else [])
        return TicketOut(
            id=t.id,
            subject=t.subject or "",
            status=TicketStatus(t.status),
            priority=TicketPriority(t.priority),
            category=TicketCategory(t.category),
            assignee=assignees.get(t.assignee_admin_id) if t.assignee_admin_id else None,
            has_media=has_media,
            attachments_count=att_count,
            created_at=t.created_at,
            updated_at=t.updated_at,
            last_activity_at=t.last_activity_at,
            user=users.get(t.user_id) or TicketUserRef(id=t.user_id, telegram_id=0),
        )

    async def create_ticket(self, data: TicketCreateIn) -> TicketOut:
        ticket = await self.tickets.create(
            {
                "user_id": data.user_id,
                "subject": (data.subject or "")[:SUBJECT_PREVIEW_LEN],
                "category": data.category.value,
                "priority": data.priority.value,
                "status": TicketStatus.NEW.value,
                "last_activity_at": datetime.now(timezone.utc),
            }
        )
        await self.session.commit()
        return await self.get_ticket(ticket.id)

    async def patch_ticket(self, ticket_id: UUID, data: TicketPatchIn, *, actor_admin_id: UUID | None = None) -> TicketOut:
        ticket = await self.tickets.get_by_id(ticket_id)
        if not ticket:
            raise TicketNotFound(str(ticket_id))

        changed = False
        if data.status is not None and data.status.value != ticket.status:
            ticket.status = data.status.value
            if data.status == TicketStatus.CLOSED:
                ticket.closed_at = datetime.now(timezone.utc)
            changed = True
        if data.priority is not None and data.priority.value != ticket.priority:
            ticket.priority = data.priority.value
            changed = True
        if data.category is not None and data.category.value != ticket.category:
            ticket.category = data.category.value
            changed = True
        if data.assignee is not None:
            new_admin_id = await self._resolve_admin_id(data.assignee, fallback_self=actor_admin_id)
            if new_admin_id != ticket.assignee_admin_id:
                ticket.assignee_admin_id = new_admin_id
                changed = True

        if changed:
            ticket.last_activity_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.commit()
        return await self.get_ticket(ticket_id)

    async def bulk_update(self, data: TicketBulkUpdateIn, *, actor_admin_id: UUID | None = None) -> int:
        if not data.ids:
            return 0
        new_assignee_id: UUID | None = None
        if data.assignee is not None:
            new_assignee_id = await self._resolve_admin_id(data.assignee, fallback_self=actor_admin_id)
        n_updated = 0
        for tid in data.ids:
            t = await self.tickets.get_by_id(tid)
            if not t:
                continue
            if data.status is not None:
                t.status = data.status.value
                if data.status == TicketStatus.CLOSED:
                    t.closed_at = datetime.now(timezone.utc)
            if data.priority is not None:
                t.priority = data.priority.value
            if data.assignee is not None:
                t.assignee_admin_id = new_assignee_id
            t.last_activity_at = datetime.now(timezone.utc)
            n_updated += 1
        if n_updated:
            await self.session.flush()
            await self.session.commit()
        return n_updated

    async def list_messages(self, ticket_id: UUID) -> MessageListOut:
        ticket = await self.tickets.get_by_id(ticket_id)
        if not ticket:
            raise TicketNotFound(str(ticket_id))

        rows = await self.messages.list_for_ticket(ticket_id)
        if not rows:
            return MessageListOut(items=[])

        attachments = await self.messages.attachments_by_message_ids([m.id for m in rows])
        admin_ids = [m.sender_admin_id for m in rows if m.sender_admin_id]
        admin_names = await self._fetch_admin_usernames(admin_ids)

        items: list[MessageOut] = []
        for m in rows:
            media_list = []
            for a in attachments.get(m.id, []):
                url = a.storage_url or (f"tg://file/{a.tg_file_id}" if a.tg_file_id else "")
                media_list.append(
                    AttachmentOut(
                        kind=a.kind,
                        url=url,
                        thumb_url=None,
                        file_name=a.file_name,
                        file_size=a.file_size,
                        duration=a.duration,
                    )
                )
            items.append(
                MessageOut(
                    id=m.id,
                    **{"from": MessageSenderKind(m.sender_kind)},
                    kind="text",
                    text=m.body or "",
                    media=media_list,
                    created_at=m.created_at,
                    delivered=m.delivered,
                    read=m.read_at is not None,
                    is_note=m.is_note,
                    author=(
                        MessageAuthorRef(label=admin_names.get(m.sender_admin_id) or "admin")
                        if m.sender_admin_id else None
                    ),
                )
            )
        return MessageListOut(items=items)

    async def post_operator_message(
        self,
        ticket_id: UUID,
        *,
        text: str,
        is_note: bool,
        actor_admin_id: UUID | None,
    ) -> MessageOut:
        ticket = await self.tickets.get_by_id(ticket_id)
        if not ticket:
            raise TicketNotFound(str(ticket_id))

        msg = await self.messages.create(
            {
                "ticket_id": ticket_id,
                "sender_kind": MessageSenderKind.OPERATOR.value,
                "sender_admin_id": actor_admin_id,
                "body": text or "",
                "is_note": is_note,
                "delivered": False,
            }
        )

        if not is_note:
            if ticket.status in (TicketStatus.NEW.value, TicketStatus.IN_PROGRESS.value, TicketStatus.WAITING_USER.value):
                ticket.status = TicketStatus.WAITING_USER.value
            if ticket.first_user_msg_at and not ticket.first_reply_at:
                ticket.first_reply_at = datetime.now(timezone.utc)
        ticket.last_activity_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.commit()

        if not is_note:
            await self._publish_outbound(ticket, msg, text=text)

        list_msg = await self.list_messages(ticket_id)
        return next((m for m in list_msg.items if m.id == msg.id), list_msg.items[-1])

    async def ingest_user_message(
        self,
        *,
        user_id: UUID,
        text: str,
        attachments_payload: list[dict] | None = None,
    ) -> tuple[SupportTicket, SupportMessage]:
        ticket = await self.tickets.find_open_by_user(user_id)
        if ticket is None:
            recent = await self.tickets.find_recent_closed_by_user(user_id, within_minutes=REOPEN_WINDOW_MIN)
            if recent is not None:
                recent.status = TicketStatus.NEW.value
                recent.closed_at = None
                ticket = recent
            else:
                ticket = await self.tickets.create(
                    {
                        "user_id": user_id,
                        "subject": (text or "")[:SUBJECT_PREVIEW_LEN],
                        "status": TicketStatus.NEW.value,
                        "category": TicketCategory.OTHER.value,
                        "priority": TicketPriority.NORMAL.value,
                        "last_activity_at": datetime.now(timezone.utc),
                        "first_user_msg_at": datetime.now(timezone.utc),
                    }
                )

        if not ticket.subject:
            ticket.subject = (text or "")[:SUBJECT_PREVIEW_LEN]
        if not ticket.first_user_msg_at:
            ticket.first_user_msg_at = datetime.now(timezone.utc)
        ticket.last_activity_at = datetime.now(timezone.utc)

        msg = await self.messages.create(
            {
                "ticket_id": ticket.id,
                "sender_kind": MessageSenderKind.USER.value,
                "body": text or "",
                "is_note": False,
                "delivered": True,
            }
        )

        for att in attachments_payload or []:
            await self.attachments.create({"message_id": msg.id, **att})

        await self.session.commit()
        return ticket, msg

    async def list_templates(self) -> TemplateListOut:
        rows = await self.templates.list_all()
        return TemplateListOut(items=[TemplateOut.model_validate(t) for t in rows])

    async def create_template(self, data: TemplateCreateIn) -> TemplateOut:
        existing = await self.templates.get_by_tag_title(data.tag, data.title)
        if existing:
            raise TemplateAlreadyExists(f"{data.tag}/{data.title}")
        t = await self.templates.create(data.model_dump())
        await self.session.commit()
        return TemplateOut.model_validate(t)

    async def update_template(self, template_id: UUID, data: TemplateUpdateIn) -> TemplateOut:
        t = await self.templates.get_by_id(template_id)
        if not t:
            raise TemplateNotFound(str(template_id))
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(t, k, v)
        await self.session.flush()
        await self.session.commit()
        return TemplateOut.model_validate(t)

    async def delete_template(self, template_id: UUID) -> None:
        t = await self.templates.get_by_id(template_id)
        if not t:
            raise TemplateNotFound(str(template_id))
        await self.session.delete(t)
        await self.session.commit()

    async def list_broadcasts(self) -> BroadcastListOut:
        rows = await self.broadcasts.list_all()
        items: list[BroadcastOut] = []
        for b in rows:
            items.append(
                BroadcastOut(
                    id=b.id,
                    audience=BroadcastAudience(b.audience),
                    audience_label=b.audience_label,
                    preview=(b.text_body or "")[:160],
                    status=BroadcastStatus(b.status),
                    delivered=b.delivered,
                    errors=b.errors,
                    clicks=b.clicks,
                    target_count=b.target_count,
                    sent_at=b.sent_at,
                    scheduled_at=b.scheduled_at,
                    created_at=b.created_at,
                )
            )
        return BroadcastListOut(items=items)

    async def audience_size(
        self, audience: BroadcastAudience, plan_id: UUID | None
    ) -> BroadcastAudienceCount:
        ids = await self._resolve_audience(audience, plan_id)
        return BroadcastAudienceCount(count=len(ids))

    async def create_broadcast(
        self,
        *,
        audience: BroadcastAudience,
        plan_id: UUID | None,
        text: str,
        buttons: list[dict] | None,
        media_kind: str | None,
        media_url: str | None,
        status: BroadcastStatus,
        scheduled_at: datetime | None,
        actor_admin_id: UUID | None,
    ) -> BroadcastOut:
        target_ids = await self._resolve_audience(audience, plan_id)
        b = await self.broadcasts.create(
            {
                "audience": audience.value,
                "audience_label": None,
                "plan_id": plan_id,
                "text_body": text,
                "media_kind": media_kind,
                "media_url": media_url,
                "inline_buttons": buttons,
                "status": status.value,
                "scheduled_at": scheduled_at,
                "target_count": len(target_ids),
                "created_by_admin_id": actor_admin_id,
            }
        )
        await self.session.commit()
        return BroadcastOut(
            id=b.id,
            audience=audience,
            audience_label=None,
            preview=(text or "")[:160],
            status=status,
            delivered=0,
            errors=0,
            clicks=0,
            target_count=len(target_ids),
            sent_at=None,
            scheduled_at=scheduled_at,
            created_at=b.created_at,
        )

    async def _resolve_audience(
        self, audience: BroadcastAudience, plan_id: UUID | None
    ) -> list[UUID]:
        now = datetime.now(timezone.utc)
        if audience == BroadcastAudience.ALL:
            stmt = select(User.id)
        elif audience == BroadcastAudience.ACTIVE:
            stmt = (
                select(User.id)
                .join(Subscription, Subscription.user_id == User.id)
                .where(Subscription.expires_at.isnot(None), Subscription.expires_at >= now)
                .distinct()
            )
        elif audience == BroadcastAudience.EXPIRING:
            from datetime import timedelta
            horizon = now + timedelta(days=7)
            stmt = (
                select(User.id)
                .join(Subscription, Subscription.user_id == User.id)
                .where(
                    Subscription.expires_at.isnot(None),
                    Subscription.expires_at >= now,
                    Subscription.expires_at <= horizon,
                )
                .distinct()
            )
        elif audience == BroadcastAudience.BY_PLAN:
            if plan_id is None:
                return []
            stmt = (
                select(User.id)
                .join(Subscription, Subscription.user_id == User.id)
                .where(Subscription.plan_id == plan_id)
                .distinct()
            )
        elif audience == BroadcastAudience.NO_SUB:
            sub_exists = select(Subscription.id).where(Subscription.user_id == User.id).exists()
            stmt = select(User.id).where(~sub_exists)
        elif audience == BroadcastAudience.TRIAL:
            stmt = (
                select(User.id)
                .join(Subscription, Subscription.user_id == User.id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Plan.price_rub == Decimal("0"))
                .distinct()
            )
        else:
            return []
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def _publish_outbound(self, ticket: SupportTicket, msg: SupportMessage, *, text: str) -> None:
        if self._nats is None:
            return
        from services.support.constants import SUPPORT_OUTBOUND_SUBJECT

        user = (await self.session.execute(select(User).where(User.id == ticket.user_id))).scalar_one_or_none()
        if not user:
            return
        payload = {
            "ticket_id": str(ticket.id),
            "message_id": str(msg.id),
            "telegram_id": user.telegram_id,
            "text": text or "",
            "media": [],
        }
        try:  # noqa: SIM105
            await self._nats.publish_jetstream(subject=SUPPORT_OUTBOUND_SUBJECT, payload=payload, msg_id=str(msg.id))
        except Exception:
            pass

    async def _fetch_users_with_meta(self, user_ids: list[UUID]) -> dict[UUID, TicketUserRef]:
        ids = [u for u in user_ids if u]
        if not ids:
            return {}
        users_q = select(User).where(User.id.in_(ids))
        users = (await self.session.execute(users_q)).scalars().all()

        sub_q = (
            select(
                Subscription.user_id,
                func.max(Subscription.expires_at).label("max_expires"),
            )
            .where(Subscription.user_id.in_(ids))
            .group_by(Subscription.user_id)
        )
        sub_rows = (await self.session.execute(sub_q)).all()
        subs_max: dict[UUID, datetime | None] = dict(sub_rows)

        sub_plan_q = (
            select(Subscription.user_id, Plan.name, Subscription.expires_at)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.user_id.in_(ids))
            .order_by(desc(Subscription.expires_at))
        )
        plan_rows = (await self.session.execute(sub_plan_q)).all()
        plan_map: dict[UUID, str] = {}
        for uid, pname, _ in plan_rows:
            if uid not in plan_map:
                plan_map[uid] = pname

        spend_q = (
            select(PaymentOrder.user_id, func.coalesce(func.sum(PaymentOrder.amount_rub), 0))
            .where(PaymentOrder.user_id.in_(ids), PaymentOrder.status == "paid")
            .group_by(PaymentOrder.user_id)
        )
        try:
            spend_rows = (await self.session.execute(spend_q)).all()
            spend_map: dict[UUID, Decimal] = {uid: Decimal(s) for uid, s in spend_rows}
        except Exception:
            spend_map = {}

        out: dict[UUID, TicketUserRef] = {}
        for u in users:
            out[u.id] = TicketUserRef(
                id=u.id,
                username=u.username,
                telegram_id=u.telegram_id,
                balance=u.balance or Decimal("0"),
                plan_name=plan_map.get(u.id),
                expires_at=subs_max.get(u.id),
                lifetime_spend=spend_map.get(u.id) or Decimal("0"),
            )
        return out

    async def _fetch_admin_usernames(self, admin_ids: list[UUID | None]) -> dict[UUID, str]:
        ids = [a for a in admin_ids if a]
        if not ids:
            return {}
        rows = (
            await self.session.execute(select(AdminUser.id, AdminUser.username).where(AdminUser.id.in_(ids)))
        ).all()
        return dict(rows)

    async def _resolve_admin_id(
        self, value: str, *, fallback_self: UUID | None = None
    ) -> UUID | None:
        if not value:
            return None
        if value == "me" and fallback_self:
            return fallback_self
        if value == "unassigned":
            return None
        try:
            return UUID(value)
        except (ValueError, TypeError):
            pass
        admin = (
            await self.session.execute(select(AdminUser).where(AdminUser.username == value))
        ).scalar_one_or_none()
        return admin.id if admin else None


def get_support_service(
    request: Request,
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> SupportService:
    nats_client = getattr(request.app.state, "nats_client", None)
    return SupportService(session, nats_client=nats_client)
