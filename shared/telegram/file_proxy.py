"""Generic Telegram Bot API file proxy.

Resolves a Telegram file_id to a public CDN path via getFile, then streams
the underlying file bytes from api.telegram.org. Reusable across modules that
need to surface user-uploaded media in admin UI (support, abuse reports, etc).
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status

from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("tg-file-proxy"))

_TELEGRAM_API = "https://api.telegram.org"


_MIME_BY_EXT = {
    "oga": "audio/ogg; codecs=opus",
    "ogg": "audio/ogg; codecs=opus",
    "opus": "audio/ogg; codecs=opus",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "webm": "video/webm",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


def _mime_by_path(file_path: str) -> str | None:
    if "." not in file_path:
        return None
    ext = file_path.rsplit(".", 1)[-1].lower()
    return _MIME_BY_EXT.get(ext)


async def resolve_file_path(*, bot_token: str, file_id: str, timeout_sec: float) -> tuple[str, str | None]:
    """Call Telegram getFile, return (file_path, mime_type_guess).

    Raises HTTPException on failure.
    """
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Support bot token not configured")
    url = f"{_TELEGRAM_API}/bot{bot_token}/getFile"
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        try:
            resp = await client.get(url, params={"file_id": file_id})
        except httpx.HTTPError as exc:
            logger.warning("tg_getfile_failed", error=str(exc))
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Telegram unreachable") from exc
    data = resp.json() if resp.content else {}
    if not data.get("ok") or "result" not in data:
        logger.warning("tg_getfile_rejected", body=str(data)[:200])
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in Telegram")
    file_path = data["result"].get("file_path")
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram returned no file_path")
    mime = data["result"].get("mime_type") or _mime_by_path(file_path)
    return file_path, mime


def stream_url(*, bot_token: str, file_path: str) -> str:
    return f"{_TELEGRAM_API}/file/bot{bot_token}/{file_path}"


async def stream_file(*, bot_token: str, file_path: str, timeout_sec: float):
    """Yield bytes chunks from Telegram CDN. Caller wraps into StreamingResponse."""
    url = stream_url(bot_token=bot_token, file_path=file_path)
    async with httpx.AsyncClient(timeout=timeout_sec) as client, client.stream("GET", url) as resp:
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Telegram file fetch failed")
        async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
            yield chunk
