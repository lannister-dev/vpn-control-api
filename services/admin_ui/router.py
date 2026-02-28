from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["Admin UI"])

_PANEL_PATH = Path(__file__).with_name("panel.html")
_PANEL_HTML = _PANEL_PATH.read_text(encoding="utf-8")


@router.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def admin_control_panel() -> HTMLResponse:
    return HTMLResponse(content=_PANEL_HTML, status_code=200)
