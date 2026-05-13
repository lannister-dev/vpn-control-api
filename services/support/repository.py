from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.support.constants import (
    MessageSenderKind,
    TicketStatus,
)
from services.support.models import (
    Broadcast,
    BroadcastLog,
    SupportAttachment,
    SupportMessage,
    SupportTemplate,
    SupportTicket,
)
from shared.database.base_repository import BaseRepository


class SupportTicketRepository(BaseRepository[SupportTicket]):
    def __init__(self, session: AsyncSession):
        super().__init__(SupportTicket, session)

    async def list_filtered(
        self,
        *,
        search: str | None = None,
        status: TicketStatus | None = None,
        category: str | None = None,
        priority: str | None = None,
        assignee_admin_id: UUID | None = None,
        unanswered_minutes: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[SupportTicket], int]:
        stmt = select(SupportTicket)
        cstmt = select(func.count(SupportTicket.id))

        conds = []
        if status:
            conds.append(SupportTicket.status == status.value)
        if category:
            conds.append(SupportTicket.category == category)
        if priority:
            conds.append(SupportTicket.priority == priority)
        if assignee_admin_id:
            conds.append(SupportTicket.assignee_admin_id == assignee_admin_id)
        if unanswered_minutes is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=unanswered_minutes)
            conds.append(
                and_(
                    SupportTicket.status.in_([TicketStatus.NEW.value, TicketStatus.IN_PROGRESS.value]),
                    SupportTicket.last_activity_at <= cutoff,
                )
            )
        if search:
            like = f"%{search.lower()}%"
            conds.append(func.lower(SupportTicket.subject).like(like))

        if conds:
            stmt = stmt.where(*conds)
            cstmt = cstmt.where(*conds)

        stmt = (
            stmt.order_by(SupportTicket.last_activity_at.desc())
            .limit(limit)
            .offset(offset)
        )

        rows = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(cstmt)).scalar_one()
        return list(rows), int(total or 0)

    async def stats(self) -> dict:
        open_q = select(func.count(SupportTicket.id)).where(
            SupportTicket.status.in_([TicketStatus.NEW.value, TicketStatus.IN_PROGRESS.value, TicketStatus.WAITING_USER.value])
        )
        open_count = int((await self.session.execute(open_q)).scalar_one() or 0)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        unanswered_q = select(func.count(SupportTicket.id)).where(
            SupportTicket.status.in_([TicketStatus.NEW.value, TicketStatus.IN_PROGRESS.value]),
            SupportTicket.last_activity_at <= cutoff,
        )
        unanswered = int((await self.session.execute(unanswered_q)).scalar_one() or 0)

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        closed_today_q = select(func.count(SupportTicket.id)).where(
            SupportTicket.status == TicketStatus.CLOSED.value,
            SupportTicket.closed_at >= today_start,
        )
        closed_today = int((await self.session.execute(closed_today_q)).scalar_one() or 0)

        reply_q = select(
            func.avg(
                func.extract("epoch", SupportTicket.first_reply_at - SupportTicket.first_user_msg_at) / 60
            )
        ).where(
            SupportTicket.first_reply_at.is_not(None),
            SupportTicket.first_user_msg_at.is_not(None),
            SupportTicket.first_reply_at >= datetime.now(timezone.utc) - timedelta(days=1),
        )
        avg_minutes = (await self.session.execute(reply_q)).scalar_one_or_none()
        avg_minutes_int = int(avg_minutes) if avg_minutes is not None else None

        return {
            "open": open_count,
            "unanswered": unanswered,
            "closed_today": closed_today,
            "avg_reply_minutes": avg_minutes_int,
        }

    async def find_open_by_user(self, user_id: UUID) -> SupportTicket | None:
        stmt = (
            select(SupportTicket)
            .where(
                SupportTicket.user_id == user_id,
                SupportTicket.status != TicketStatus.CLOSED.value,
            )
            .order_by(SupportTicket.last_activity_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_recent_closed_by_user(
        self, user_id: UUID, *, within_minutes: int
    ) -> SupportTicket | None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
        stmt = (
            select(SupportTicket)
            .where(
                SupportTicket.user_id == user_id,
                SupportTicket.status == TicketStatus.CLOSED.value,
                SupportTicket.closed_at.is_not(None),
                SupportTicket.closed_at >= cutoff,
            )
            .order_by(SupportTicket.closed_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def touch_activity(self, ticket_id: UUID) -> None:
        ticket = await self.get_by_id(ticket_id)
        if ticket:
            ticket.last_activity_at = datetime.now(timezone.utc)
            await self.session.flush()


class SupportMessageRepository(BaseRepository[SupportMessage]):
    def __init__(self, session: AsyncSession):
        super().__init__(SupportMessage, session)

    async def list_for_ticket(self, ticket_id: UUID) -> list[SupportMessage]:
        stmt = (
            select(SupportMessage)
            .where(SupportMessage.ticket_id == ticket_id)
            .order_by(SupportMessage.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def attachments_by_message_ids(self, message_ids: list[UUID]) -> dict[UUID, list[SupportAttachment]]:
        if not message_ids:
            return {}
        stmt = select(SupportAttachment).where(SupportAttachment.message_id.in_(message_ids))
        rows = (await self.session.execute(stmt)).scalars().all()
        out: dict[UUID, list[SupportAttachment]] = {}
        for a in rows:
            out.setdefault(a.message_id, []).append(a)
        return out

    async def has_media_flags(self, ticket_ids: list[UUID]) -> dict[UUID, tuple[bool, int]]:
        if not ticket_ids:
            return {}
        stmt = (
            select(
                SupportMessage.ticket_id,
                func.count(SupportAttachment.id),
            )
            .join(SupportAttachment, SupportAttachment.message_id == SupportMessage.id)
            .where(SupportMessage.ticket_id.in_(ticket_ids))
            .group_by(SupportMessage.ticket_id)
        )
        rows = (await self.session.execute(stmt)).all()
        out: dict[UUID, tuple[bool, int]] = dict.fromkeys(ticket_ids, (False, 0))
        for tid, cnt in rows:
            out[tid] = (cnt > 0, int(cnt))
        return out

    async def first_operator_reply_for_ticket(self, ticket_id: UUID) -> SupportMessage | None:
        stmt = (
            select(SupportMessage)
            .where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.sender_kind == MessageSenderKind.OPERATOR.value,
                SupportMessage.is_note.is_(False),
            )
            .order_by(SupportMessage.created_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class SupportAttachmentRepository(BaseRepository[SupportAttachment]):
    def __init__(self, session: AsyncSession):
        super().__init__(SupportAttachment, session)


class SupportTemplateRepository(BaseRepository[SupportTemplate]):
    def __init__(self, session: AsyncSession):
        super().__init__(SupportTemplate, session)

    async def list_all(self) -> list[SupportTemplate]:
        stmt = select(SupportTemplate).order_by(SupportTemplate.tag.asc(), SupportTemplate.title.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_tag_title(self, tag: str, title: str) -> SupportTemplate | None:
        stmt = select(SupportTemplate).where(
            func.lower(SupportTemplate.tag) == tag.lower(),
            func.lower(SupportTemplate.title) == title.lower(),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class BroadcastRepository(BaseRepository[Broadcast]):
    def __init__(self, session: AsyncSession):
        super().__init__(Broadcast, session)

    async def list_all(self, *, limit: int = 100) -> list[Broadcast]:
        stmt = (
            select(Broadcast)
            .order_by(Broadcast.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


class BroadcastLogRepository(BaseRepository[BroadcastLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(BroadcastLog, session)
