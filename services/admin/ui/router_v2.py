from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["Admin UI"])

STATIC_V2_DIR = Path(__file__).parent / "static" / "v2"
_INDEX_PATH = STATIC_V2_DIR / "index.html"

_RESERVED_PREFIXES = ("api/", "static/", "healthz", "metrics", "monitoring", "admin/")


@router.get("/admin/v2", include_in_schema=False)
@router.get("/admin/v2/{full_path:path}", include_in_schema=False)
async def legacy_v2_redirect(full_path: str = ""):
    """Permanent redirect from old SPA location /admin/v2* → /."""
    return RedirectResponse(url="/", status_code=308)


@router.get("/admin", include_in_schema=False)
async def legacy_admin_redirect():
    return RedirectResponse(url="/", status_code=308)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def admin_spa(request: Request, full_path: str = ""):
    """Serves the React SPA as the root admin panel.

    Auth is handled client-side via /api/v1/auth/admin/session — LoginPage
    renders when unauthenticated. No server-side redirect.
    """
    if full_path.startswith(_RESERVED_PREFIXES):
        raise HTTPException(status_code=404)

    if not _INDEX_PATH.exists():
        return HTMLResponse(
            "<h1>Admin panel not built</h1>"
            "<p>Run <code>cd services/admin/ui/frontend && npm install && npm run build</code> "
            "then copy dist to services/admin/ui/static/v2/.</p>",
            status_code=503,
        )
    return HTMLResponse(_INDEX_PATH.read_text(encoding="utf-8"))
