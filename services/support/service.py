import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import StructuredLogger

logger_support = StructuredLogger(logging.getLogger("support-service"))

from services.auth.admin.repository import AdminUserRepository
from services.billing.models import BalanceTransaction
from services.billing.repository import OrderRepository
from services.support.constants import (
    REOPEN_WINDOW_MIN,
    SUBJECT_PREVIEW_LEN,
    SUPPORT_OUTBOUND_SUBJECT,
)
from services.support.exceptions import (
    EmptyMessage,
    SupportActionFailed,
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
    BroadcastAudience,
    BroadcastAudienceCount,
    BroadcastCreate,
    BroadcastListOut,
    BroadcastOut,
    BroadcastStatus,
    MessageAuthorRef,
    MessageListOut,
    MessageOut,
    MessageSenderKind,
    SupportAttachmentCreate,
    SupportMessageCreate,
    SupportOutboundPayload,
    SupportTicketCreate,
    TemplateCreateIn,
    TemplateListOut,
    TemplateOut,
    TemplateUpdateIn,
    TicketBulkUpdateIn,
    TicketCategory,
    TicketCreateIn,
    TicketListOut,
    TicketOut,
    TicketPatchIn,
    TicketPriority,
    TicketStatsOut,
    TicketStatus,
    TicketUserRef,
)
from services.support.texts import (
    GRANT_DAY_SYSTEM,
    REFUND_DESCRIPTION,
    REFUND_SYSTEM,
    TICKET_CLOSED_SYSTEM,
    TICKET_CLOSED_USER_NOTIFY,
)
from services.users.repository import UserRepository
from services.vpn.subscriptions.repository import SubscriptionRepository
from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient


class SupportService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        nats_client: NatsClient | None = None,
        outbound_subject: str = SUPPORT_OUTBOUND_SUBJECT,
    ):
        self.session = session
        self.tickets = SupportTicketRepository(session)
        self.messages = SupportMessageRepository(session)
        self.attachments = SupportAttachmentRepository(session)
        self.templates = SupportTemplateRepository(session)
        self.broadcasts = BroadcastRepository(session)
        self.broadcast_log = BroadcastLogRepository(session)
        self.users = UserRepository(session)
        self.admins = AdminUserRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.orders = OrderRepository(session)
        self._nats = nats_client
        self._outbound_subject = outbound_subject

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
        assignees = await self.admins.list_usernames_by_ids([t.assignee_admin_id for t in rows if t.assignee_admin_id])

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
            open=s.open,
            unanswered=s.unanswered,
            avg_reply_minutes=s.avg_reply_minutes,
            avg_reply_change=None,
            closed_today=s.closed_today,
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
        assignees = await self.admins.list_usernames_by_ids([t.assignee_admin_id] if t.assignee_admin_id else [])
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
            SupportTicketCreate(
                user_id=data.user_id,
                subject=(data.subject or "")[:SUBJECT_PREVIEW_LEN],
                category=data.category,
                priority=data.priority,
                status=TicketStatus.NEW,
                last_activity_at=datetime.now(timezone.utc),
            ).model_dump()
        )
        await self.session.commit()
        return await self.get_ticket(ticket.id)

    async def patch_ticket(self, ticket_id: UUID, data: TicketPatchIn, *, actor_admin_id: UUID | None = None) -> TicketOut:
        ticket = await self.tickets.get_by_id(ticket_id)
        if not ticket:
            raise TicketNotFound(str(ticket_id))

        changed = False
        just_closed = False
        if data.status is not None and data.status.value != ticket.status:
            ticket.status = data.status.value
            if data.status == TicketStatus.CLOSED:
                ticket.closed_at = datetime.now(timezone.utc)
                just_closed = True
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

        if just_closed:
            sys_msg = await self._add_system_message(ticket_id, TICKET_CLOSED_SYSTEM, actor_admin_id)
            await self.session.commit()
            await self._publish_outbound(ticket, sys_msg, text=TICKET_CLOSED_USER_NOTIFY)
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
        admin_names = await self.admins.list_usernames_by_ids(admin_ids)

        items: list[MessageOut] = []
        for m in rows:
            media_list = []
            for a in attachments.get(m.id, []):
                url = a.storage_url or (f"/api/v1/support/media/{a.tg_file_id}" if a.tg_file_id else "")
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

        clean_text = (text or "").strip()
        if not clean_text:
            raise EmptyMessage("Message must contain text")

        msg = await self.messages.create(
            SupportMessageCreate(
                ticket_id=ticket_id,
                sender_kind=MessageSenderKind.OPERATOR,
                sender_admin_id=actor_admin_id,
                body=clean_text,
                is_note=is_note,
                delivered=False,
            ).model_dump()
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
            await self._publish_outbound(ticket, msg, text=clean_text)

        list_msg = await self.list_messages(ticket_id)
        return next((m for m in list_msg.items if m.id == msg.id), list_msg.items[-1])

    async def grant_day(self, ticket_id: UUID, *, actor_admin_id: UUID | None) -> SupportTicket:
        ticket = await self.tickets.get_by_id(ticket_id)
        if not ticket:
            raise TicketNotFound(str(ticket_id))

        subscription = await self.subscriptions.get_latest_for_user(ticket.user_id)
        if subscription is None or subscription.expires_at is None:
            raise SupportActionFailed("У пользователя нет активной подписки")

        now = datetime.now(timezone.utc)
        base = subscription.expires_at if subscription.expires_at > now else now
        subscription.expires_at = base + timedelta(days=1)

        await self._add_system_message(ticket_id, GRANT_DAY_SYSTEM, actor_admin_id)
        ticket.last_activity_at = now
        await self.session.flush()
        await self.session.commit()
        return ticket

    async def refund_last_order(self, ticket_id: UUID, *, actor_admin_id: UUID | None) -> SupportTicket:
        ticket = await self.tickets.get_by_id(ticket_id)
        if not ticket:
            raise TicketNotFound(str(ticket_id))

        order = await self.orders.get_last_paid_for_user(ticket.user_id)
        if order is None:
            raise SupportActionFailed("У пользователя нет оплаченных заказов")

        user = await self.users.get_by_id(ticket.user_id)
        if user is None:
            raise SupportActionFailed("Пользователь не найден")

        amount = Decimal(order.amount_rub)
        new_balance = (user.balance or Decimal("0")) + amount
        user.balance = new_balance
        order.status = "refunded"
        self.session.add(
            BalanceTransaction(
                user_id=user.id,
                amount=amount,
                balance_after=new_balance,
                type="refund",
                order_id=order.id,
                description=REFUND_DESCRIPTION.format(order_id=order.id, ticket_id=ticket_id),
            )
        )

        await self._add_system_message(
            ticket_id,
            REFUND_SYSTEM.format(amount=amount),
            actor_admin_id,
        )
        ticket.last_activity_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.commit()
        return ticket

    async def _add_system_message(
        self, ticket_id: UUID, body: str, actor_admin_id: UUID | None
    ) -> SupportMessage:
        return await self.messages.create(
            SupportMessageCreate(
                ticket_id=ticket_id,
                sender_kind=MessageSenderKind.SYSTEM,
                sender_admin_id=actor_admin_id,
                body=body,
                is_note=False,
                delivered=True,
            ).model_dump()
        )

    async def ingest_user_message(
        self,
        *,
        user_id: UUID,
        text: str,
        attachments_payload: list[dict] | None = None,
    ) -> tuple[SupportTicket, SupportMessage]:
        now = datetime.now(timezone.utc)
        ticket = await self.tickets.find_open_by_user(user_id)
        if ticket is None:
            recent = await self.tickets.find_recent_closed_by_user(user_id, within_minutes=REOPEN_WINDOW_MIN)
            if recent is not None:
                recent.status = TicketStatus.NEW.value
                recent.closed_at = None
                ticket = recent
            else:
                ticket = await self.tickets.create(
                    SupportTicketCreate(
                        user_id=user_id,
                        subject=(text or "")[:SUBJECT_PREVIEW_LEN],
                        status=TicketStatus.NEW,
                        category=TicketCategory.OTHER,
                        priority=TicketPriority.NORMAL,
                        last_activity_at=now,
                        first_user_msg_at=now,
                    ).model_dump()
                )

        if not ticket.subject:
            ticket.subject = (text or "")[:SUBJECT_PREVIEW_LEN]
        if not ticket.first_user_msg_at:
            ticket.first_user_msg_at = now
        ticket.last_activity_at = now

        msg = await self.messages.create(
            SupportMessageCreate(
                ticket_id=ticket.id,
                sender_kind=MessageSenderKind.USER,
                body=text or "",
                is_note=False,
                delivered=True,
            ).model_dump()
        )

        for att in attachments_payload or []:
            await self.attachments.create(
                SupportAttachmentCreate(message_id=msg.id, **att).model_dump()
            )

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
            BroadcastCreate(
                audience=audience,
                plan_id=plan_id,
                text_body=text,
                media_kind=media_kind,
                media_url=media_url,
                inline_buttons=buttons,
                status=status,
                scheduled_at=scheduled_at,
                target_count=len(target_ids),
                created_by_admin_id=actor_admin_id,
            ).model_dump()
        )
        await self.session.commit()

        delivered = 0
        sent_at: datetime | None = None
        final_status = status
        if status == BroadcastStatus.SENDING and target_ids:
            delivered = await self._fan_out_broadcast(b.id, target_ids, text)
            sent_at = datetime.now(timezone.utc)
            final_status = BroadcastStatus.SENT
            b.delivered = delivered
            b.sent_at = sent_at
            b.status = final_status.value
            await self.session.flush()
            await self.session.commit()

        return BroadcastOut(
            id=b.id,
            audience=audience,
            audience_label=None,
            preview=(text or "")[:160],
            status=final_status,
            delivered=delivered,
            errors=max(0, len(target_ids) - delivered) if status == BroadcastStatus.SENDING else 0,
            clicks=0,
            target_count=len(target_ids),
            sent_at=sent_at,
            scheduled_at=scheduled_at,
            created_at=b.created_at,
        )

    async def _fan_out_broadcast(
        self, broadcast_id: UUID, user_ids: list[UUID], text: str,
    ) -> int:
        if self._nats is None or not user_ids:
            return 0
        users = await self.users.list_by_ids(user_ids)
        targets = [(str(u.id), int(u.telegram_id)) for u in users if u.telegram_id]
        if not targets:
            return 0

        sem = asyncio.Semaphore(20)

        async def _one(_user_id: str, tg_id: int) -> bool:
            payload = SupportOutboundPayload(
                ticket_id=str(broadcast_id),
                message_id=str(uuid4()),
                telegram_id=tg_id,
                text=text,
                media=[],
            )
            async with sem:
                try:
                    await self._nats.publish_jetstream(
                        subject=self._outbound_subject,
                        payload=payload.model_dump(),
                        msg_id=payload.message_id,
                    )
                    return True
                except Exception:
                    logger_support.exception(
                        "broadcast_publish_failed",
                        broadcast_id=str(broadcast_id),
                        telegram_id=tg_id,
                    )
                    return False

        results = await asyncio.gather(*(_one(uid, tg) for uid, tg in targets))
        return sum(1 for ok in results if ok)

    async def _resolve_audience(
        self, audience: BroadcastAudience, plan_id: UUID | None
    ) -> list[UUID]:
        return await self.broadcasts.resolve_audience_user_ids(
            audience, plan_id=plan_id, now=datetime.now(timezone.utc)
        )

    async def _publish_outbound(self, ticket: SupportTicket, msg: SupportMessage, *, text: str) -> None:
        if self._nats is None:
            return

        user = await self.users.get_by_id(ticket.user_id)
        if not user:
            return
        payload = SupportOutboundPayload(
            ticket_id=str(ticket.id),
            message_id=str(msg.id),
            telegram_id=user.telegram_id,
            text=text or "",
            media=[],
        )
        try:
            await self._nats.publish_jetstream(
                subject=self._outbound_subject,
                payload=payload.model_dump(),
                msg_id=str(msg.id),
            )
        except Exception:
            logger_support.exception(
                "support_outbound_publish_failed",
                subject=self._outbound_subject,
                message_id=str(msg.id),
            )

    async def _fetch_users_with_meta(self, user_ids: list[UUID]) -> dict[UUID, TicketUserRef]:
        ids = [u for u in user_ids if u]
        if not ids:
            return {}
        users = await self.users.list_by_ids(ids)
        sub_meta = await self.tickets.aggregate_subscription_meta(ids)
        spend_map = await self.tickets.aggregate_lifetime_spend(ids)

        out: dict[UUID, TicketUserRef] = {}
        for u in users:
            expires_at, plan_name = sub_meta.get(u.id, (None, None))
            out[u.id] = TicketUserRef(
                id=u.id,
                username=u.username,
                telegram_id=u.telegram_id,
                balance=u.balance or Decimal("0"),
                plan_name=plan_name,
                expires_at=expires_at,
                lifetime_spend=spend_map.get(u.id) or Decimal("0"),
            )
        return out

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
        admin = await self.admins.get_by_username(value)
        return admin.id if admin else None


def get_support_service(
    request: Request,
    session: AsyncSession = Depends(AsyncDatabase.get_session),
) -> SupportService:
    nats_client = getattr(request.app.state, "nats_client", None)
    nats_config = getattr(request.app.state, "nats_config", None)
    outbound_subject = (
        nats_config.support_outbound_subject
        if nats_config is not None
        else SUPPORT_OUTBOUND_SUBJECT
    )
    return SupportService(session, nats_client=nats_client, outbound_subject=outbound_subject)
