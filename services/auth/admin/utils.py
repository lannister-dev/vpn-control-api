from __future__ import annotations

from fastapi import Request, Response

from services.auth.admin.constants import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def set_session_cookie(
    response: Response,
    session_id: str,
    max_age: int,
    *,
    secure: bool,
) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def set_csrf_cookie(response: Response, csrf_token: str, *, secure: bool) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
