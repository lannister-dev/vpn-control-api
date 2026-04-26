from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.utils.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    reset_request_id,
    set_request_id,
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = (request.headers.get(REQUEST_ID_HEADER) or "").strip() or new_request_id()
        token = set_request_id(rid)
        try:
            response = await call_next(request)
        finally:
            try:
                reset_request_id(token)
            except (LookupError, ValueError):
                set_request_id(None)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


def add_request_id_middleware(app) -> None:
    app.add_middleware(RequestIdMiddleware)
