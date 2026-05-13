from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from services.auth.dependencies import admin_auth, current_admin_actor
from services.support.constants import (
    BroadcastAudience,
    BroadcastStatus,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from services.support.exceptions import (
    TemplateAlreadyExists,
    TemplateNotFound,
    TicketNotFound,
)
from services.support.schemas import (
    BroadcastAudienceCount,
    BroadcastListOut,
    BroadcastOut,
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
)
from services.support.service import SupportService, get_support_service

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
):
    assignee_id: UUID | None = None
    if assignee and assignee not in ("me", "unassigned"):
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
    actor: str = Depends(current_admin_actor),
):
    try:
        return await service.patch_ticket(ticket_id, data, actor_admin_id=None)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")


@router.post("/tickets/bulk-update")
async def bulk_update(
    data: TicketBulkUpdateIn,
    service: SupportService = Depends(get_support_service),
    actor: str = Depends(current_admin_actor),
):
    n = await service.bulk_update(data, actor_admin_id=None)
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
    actor: str = Depends(current_admin_actor),
):
    try:
        return await service.post_operator_message(
            ticket_id,
            text=text,
            is_note=is_note,
            actor_admin_id=None,
        )
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")


@router.post("/tickets/{ticket_id}/grant-day")
async def grant_day(
    ticket_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        await service.get_ticket(ticket_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ok": True}


@router.post("/tickets/{ticket_id}/refund")
async def refund(
    ticket_id: UUID,
    service: SupportService = Depends(get_support_service),
):
    try:
        await service.get_ticket(ticket_id)
    except TicketNotFound:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ok": True}


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
):
    import json

    parsed_buttons: list[dict] | None = None
    if buttons:
        try:
            parsed_buttons = json.loads(buttons)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid buttons JSON")
    media_kind = None
    media_url = None
    if media is not None and media.filename:
        media_kind = (media.content_type or "").split("/")[0] or "document"
        media_url = f"/api/v1/support/media/{media.filename}"
    return await service.create_broadcast(
        audience=audience,
        plan_id=plan_id,
        text=text,
        buttons=parsed_buttons,
        media_kind=media_kind,
        media_url=media_url,
        status=status_,
        scheduled_at=scheduled_at,
        actor_admin_id=None,
    )
