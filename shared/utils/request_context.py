from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_CTX: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _REQUEST_ID_CTX.get()


def set_request_id(value: str | None):
    return _REQUEST_ID_CTX.set(value)


def reset_request_id(token) -> None:
    _REQUEST_ID_CTX.reset(token)


def new_request_id() -> str:
    return uuid4().hex
