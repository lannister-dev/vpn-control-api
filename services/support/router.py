import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from services.auth.dependencies import admin_auth, current_admin_user_id
from services.config import get_settings
from services.support.exceptions import (
    BroadcastNotFound,
    EmptyMessage,
    InvalidStateTransition,
    SupportActionFailed,
    TemplateAlreadyExists,
    TemplateNotFound,
    TicketClosed,
    TicketNotFound,
)
from services.support.schemas import (
    BroadcastAudience,
    BroadcastAudienceCount,
    BroadcastListOut,
    BroadcastOut,
    BroadcastStatus,
    MessageListOut,
    MessageOut,
    RecurringBroadcastCreateIn,
    RecurringBroadcastListOut,
    RecurringBroadcastOut,
    RecurringBroadcastUpdateIn,
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
)
from services.support.service import SupportService, get_support_service
from shared.telegram.file_proxy import resolve_file_path, stream_file

router = APIRouter(prefix="/support", tags=["Support"], dependencies=[Depends(admin_auth)])


@router.get("/tickets/stats", response_model=TicketStatsOut)
async def tickets_stats(service: SupportService = Depends(get_support_service)):
    return await service.stats()


@router.get("/tickets", response_model=TicketListOut)
async def list_tickets(
    search: str | None = Query(None),
    status_: TicketStatus | None = Query(None, alias="status"),
    category: TicketCategory | None = Query(None),
    priority: TicketPriority | None = Query(None),
    assignee: str | None = Query(None),
    unanswered_minutes: int | None = Query(None, ge=1),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    assignee_id: UUID | None = None
    if assignee:
        if assignee == "me" and actor_admin_id is not None:
            assignee_id = actor_admin_id
        elif assignee == "unassigned":
            assignee_id = None
        else:
            try:
                assignee_id = UUID(assignee)
            except ValueError:
                assignee_id = await service._resolve_admin_id(assignee)
    return await service.list_tickets(
        search=search,
        status=status_,
        category=category,
        priority=priority,
        assignee_admin_id=assignee_id,
        unanswered_minutes=unanswered_minutes,
        limit=limit,
        offset=offset,
    )


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    data: TicketCreateIn,
    service: SupportService = Depends(get_support_service),
):
    return await service.create_ticket(data)


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        return await service.get_ticket(ticket_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def patch_ticket(
    ticket_id: UUID,
    data: TicketPatchIn,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    try:
        return await service.patch_ticket(ticket_id, data, actor_admin_id=actor_admin_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")


@router.post("/tickets/bulk-update")
async def bulk_update(
    data: TicketBulkUpdateIn,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    n = await service.bulk_update(data, actor_admin_id=actor_admin_id)
    return {"updated": n}


@router.get("/tickets/{ticket_id}/messages", response_model=MessageListOut)
async def list_messages(
    ticket_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        return await service.list_messages(ticket_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")


@router.post("/tickets/{ticket_id}/messages", response_model=MessageOut)
async def post_message(
    ticket_id: UUID,
    text: Annotated[str, Form()] = "",
    is_note: Annotated[bool, Form()] = False,
    files: Annotated[list[UploadFile] | None, File()] = None,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    attachments: list = []
    if files:
        settings = get_settings()
        if not settings.s3.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 не настроен — загрузка файлов недоступна",
            )
        from services.support.schemas import SupportAttachmentCreate as _AttC
        from shared.s3 import S3Client
        s3 = S3Client(settings.s3)
        for f in files:
            data = await f.read()
            if not data:
                continue
            ct = f.content_type or "application/octet-stream"
            kind = "image" if ct.startswith("image/") else "video" if ct.startswith("video/") else "audio" if ct.startswith("audio/") else "document"
            from uuid import uuid4 as _u
            ext = (f.filename or "").rsplit(".", 1)
            suffix = f".{ext[1]}" if len(ext) == 2 else ""
            key = f"support/tickets/{ticket_id}/{_u().hex}{suffix}"
            up = await s3.upload_bytes(key=key, data=data, content_type=ct, cache_control="public, max-age=2592000")
            attachments.append(_AttC(
                kind=kind,
                file_name=f.filename or "",
                file_size=up.size,
                mime_type=ct,
                storage_url=up.public_url,
            ))
    try:
        return await service.post_operator_message(
            ticket_id,
            text=text,
            is_note=is_note,
            actor_admin_id=actor_admin_id,
            attachments=attachments or None,
        )
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")
    except EmptyMessage:
        raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
    except TicketClosed:
        raise HTTPException(status_code=409, detail="Тикет закрыт. Переоткройте его, чтобы продолжить переписку.")


@router.post("/tickets/{ticket_id}/grant-day")
async def grant_day(
    ticket_id: UUID,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    try:
        await service.grant_day(ticket_id, actor_admin_id=actor_admin_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")
    except SupportActionFailed as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/tickets/{ticket_id}/refund")
async def refund(
    ticket_id: UUID,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    try:
        await service.refund_last_order(ticket_id, actor_admin_id=actor_admin_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")
    except SupportActionFailed as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/media/{file_id}")
async def get_media(file_id: str):
    settings = get_settings()
    if not settings.support.bot_token:
        raise HTTPException(status_code=503, detail="Support bot token not configured")
    file_path, mime = await resolve_file_path(
        bot_token=settings.support.bot_token,
        file_id=file_id,
        timeout_sec=settings.support.media_proxy_timeout_sec,
    )
    return StreamingResponse(
        stream_file(
            bot_token=settings.support.bot_token,
            file_path=file_path,
            timeout_sec=settings.support.media_proxy_timeout_sec,
        ),
        media_type=mime or "application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{file_path.split("/")[-1]}"',
        },
    )


@router.get("/templates", response_model=TemplateListOut)
async def list_templates(service: SupportService = Depends(get_support_service)):
    return await service.list_templates()


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreateIn,
    service: SupportService = Depends(get_support_service),
):
    try:
        return await service.create_template(data)
    except TemplateAlreadyExists:
        raise HTTPException(status_code=409, detail="Template already exists")


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: UUID,
    data: TemplateUpdateIn,
    service: SupportService = Depends(get_support_service),
):
    try:
        return await service.update_template(template_id, data)
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail="Template not found")


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        await service.delete_template(template_id)
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}


@router.get("/broadcasts", response_model=BroadcastListOut)
async def list_broadcasts(service: SupportService = Depends(get_support_service)):
    return await service.list_broadcasts()


@router.post("/broadcasts/{broadcast_id}/cancel", response_model=BroadcastOut)
async def cancel_broadcast(
    broadcast_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        return await service.cancel_broadcast(broadcast_id)
    except BroadcastNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/broadcasts/{broadcast_id}/repeat", response_model=BroadcastOut, status_code=status.HTTP_201_CREATED)
async def repeat_broadcast(
    broadcast_id: UUID,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    try:
        return await service.repeat_broadcast(broadcast_id, actor_admin_id=actor_admin_id)
    except BroadcastNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")


@router.get("/recurring-broadcasts", response_model=RecurringBroadcastListOut)
async def list_recurring_broadcasts(service: SupportService = Depends(get_support_service)):
    return await service.list_recurring()


@router.post("/recurring-broadcasts", response_model=RecurringBroadcastOut, status_code=status.HTTP_201_CREATED)
async def create_recurring_broadcast(
    data: RecurringBroadcastCreateIn,
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    return await service.create_recurring(data, actor_admin_id=actor_admin_id)


@router.patch("/recurring-broadcasts/{schedule_id}", response_model=RecurringBroadcastOut)
async def update_recurring_broadcast(
    schedule_id: UUID,
    data: RecurringBroadcastUpdateIn,
    service: SupportService = Depends(get_support_service),
):
    try:
        return await service.update_recurring(schedule_id, data)
    except BroadcastNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")


@router.delete("/recurring-broadcasts/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_broadcast(
    schedule_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        await service.delete_recurring(schedule_id)
    except BroadcastNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/broadcasts/audience-size", response_model=BroadcastAudienceCount)
async def audience_size(
    audience: BroadcastAudience,
    plan_id: UUID | None = Query(None),
    service: SupportService = Depends(get_support_service),
):
    return await service.audience_size(audience, plan_id)


@router.post("/broadcasts", response_model=BroadcastOut, status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    audience: Annotated[BroadcastAudience, Form()],
    text: Annotated[str, Form()],
    status_: Annotated[BroadcastStatus, Form(alias="status")] = BroadcastStatus.DRAFT,
    plan_id: Annotated[UUID | None, Form()] = None,
    buttons: Annotated[str | None, Form()] = None,
    scheduled_at: Annotated[datetime | None, Form()] = None,
    media: UploadFile | None = File(None),
    service: SupportService = Depends(get_support_service),
    actor_admin_id: UUID | None = Depends(current_admin_user_id),
):
    parsed_buttons: list[dict] | None = None
    if buttons:
        try:
            parsed_buttons = json.loads(buttons)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid buttons JSON")
    media_kind = None
    media_url = None
    if media is not None and media.filename:
        settings = get_settings()
        if not settings.s3.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 не настроен — загрузка медиа недоступна",
            )
        from uuid import uuid4 as _u

        from shared.s3 import S3Client
        data = await media.read()
        if data:
            ct = media.content_type or "application/octet-stream"
            media_kind = "image" if ct.startswith("image/") else "video" if ct.startswith("video/") else "audio" if ct.startswith("audio/") else "document"
            ext = (media.filename or "").rsplit(".", 1)
            suffix = f".{ext[1]}" if len(ext) == 2 else ""
            key = f"support/broadcasts/{_u().hex}{suffix}"
            s3c = S3Client(settings.s3)
            up = await s3c.upload_bytes(key=key, data=data, content_type=ct, cache_control="public, max-age=2592000")
            media_url = up.public_url
    return await service.create_broadcast(
        audience=audience,
        plan_id=plan_id,
        text=text,
        buttons=parsed_buttons,
        media_kind=media_kind,
        media_url=media_url,
        status=status_,
        scheduled_at=scheduled_at,
        actor_admin_id=actor_admin_id,
    )
