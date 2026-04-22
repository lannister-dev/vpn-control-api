from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.auth.admin.constants import SESSION_COOKIE_NAME
from services.auth.admin.crypto import hash_session_id
from services.auth.admin.service import AdminAuthService
from shared.database.session import AsyncDatabase

router = APIRouter(tags=["Admin UI v2"])

STATIC_V2_DIR = Path(__file__).parent / "static" / "v2"
_INDEX_PATH = STATIC_V2_DIR / "index.html"


async def _authorized(request: Request) -> bool:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return False
    session_hash = hash_session_id(session_id)
    async with AsyncDatabase.get_session_maker()() as session:
        result = await AdminAuthService(session).validate_session(session_hash)
    return result is not None


@router.get("/admin/v2", response_class=HTMLResponse, include_in_schema=False)
@router.get("/admin/v2/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def admin_v2(request: Request, full_path: str = ""):
    if not await _authorized(request):
        return RedirectResponse(url="/api/v1/auth/admin/login", status_code=307)
    if not _INDEX_PATH.exists():
        return HTMLResponse(
            "<h1>Admin v2 not built</h1>"
            "<p>Run <code>cd services/admin_ui/frontend && npm install && npm run build</code> "
            "then copy dist to static/v2/.</p>",
            status_code=503,
        )
    return HTMLResponse(_INDEX_PATH.read_text(encoding="utf-8"))
