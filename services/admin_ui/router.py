from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles

from services.auth.admin.constants import SESSION_COOKIE_NAME
from services.auth.admin.crypto import hash_session_id
from services.auth.admin.service import AdminAuthService
from shared.database.session import AsyncDatabase

router = APIRouter(tags=["Admin UI"])

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "panel.html"
_PANEL_HTML = _TEMPLATE_PATH.read_text(encoding="utf-8")
STATIC_DIR = Path(__file__).parent / "static"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def admin_control_panel(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return RedirectResponse(url="/api/v1/auth/admin/login", status_code=307)
    session_hash = hash_session_id(session_id)
    async with AsyncDatabase.get_session_maker()() as session:
        result = await AdminAuthService(session).validate_session(session_hash)
    if result is None:
        return RedirectResponse(url="/api/v1/auth/admin/login", status_code=307)
    return HTMLResponse(content=_PANEL_HTML, status_code=200)
