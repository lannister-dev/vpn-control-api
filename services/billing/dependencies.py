from fastapi import HTTPException
from starlette import status
from starlette.responses import RedirectResponse


def _required_redirect(url: str, *, setting_name: str) -> RedirectResponse:
    target = url.strip()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{setting_name} is not configured",
        )
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

