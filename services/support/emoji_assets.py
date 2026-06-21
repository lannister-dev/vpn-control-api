from __future__ import annotations

import html
import json
import logging
from uuid import uuid4

import httpx

from services.config import S3Config, SupportConfig
from shared.s3.client import S3Client
from shared.telegram.file_proxy import resolve_file_path, stream_file
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("support-emoji-assets"))

_TELEGRAM_API = "https://api.telegram.org"


def custom_emoji_entities_to_html(text: str, entities) -> str:
    ce = sorted(
        [
            e
            for e in (entities or [])
            if getattr(e, "type", None) == "custom_emoji" and getattr(e, "custom_emoji_id", None)
        ],
        key=lambda e: e.offset,
    )
    raw = text or ""
    if not ce:
        return html.escape(raw, quote=False)
    u16 = raw.encode("utf-16-le")
    total = len(u16) // 2
    out: list[str] = []
    cursor = 0
    for e in ce:
        if e.offset < cursor or e.offset > total:
            continue
        if e.offset > cursor:
            out.append(html.escape(u16[cursor * 2:e.offset * 2].decode("utf-16-le"), quote=False))
        fallback = u16[e.offset * 2:(e.offset + e.length) * 2].decode("utf-16-le")
        out.append(
            f'<tg-emoji emoji-id="{e.custom_emoji_id}">{html.escape(fallback, quote=False)}</tg-emoji>'
        )
        cursor = e.offset + e.length
    if cursor < total:
        out.append(html.escape(u16[cursor * 2:].decode("utf-16-le"), quote=False))
    return "".join(out)


class TelegramMediaResolver:
    def __init__(self, *, support: SupportConfig, s3: S3Config) -> None:
        self._support = support
        self._s3 = s3

    async def resolve(self, tg_file_id: str | None) -> str | None:
        if not tg_file_id or not self._support.bot_token or not self._s3.enabled:
            return None
        timeout = float(self._support.media_proxy_timeout_sec)
        try:
            file_path, mime = await resolve_file_path(
                bot_token=self._support.bot_token, file_id=tg_file_id, timeout_sec=timeout
            )
            chunks: list[bytes] = []
            async for chunk in stream_file(
                bot_token=self._support.bot_token, file_path=file_path, timeout_sec=timeout
            ):
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                return None
            ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "bin"
            result = await S3Client(self._s3).upload_bytes(
                key=f"support/broadcasts/{uuid4().hex}.{ext}",
                data=data,
                content_type=mime or "application/octet-stream",
                cache_control="public, max-age=2592000",
            )
            return result.public_url
        except Exception:
            logger.warning("broadcast_media_resolve_failed")
            return None


class CustomEmojiResolver:
    def __init__(self, *, support: SupportConfig, s3: S3Config) -> None:
        self._support = support
        self._s3 = s3

    async def resolve(self, custom_emoji_ids: list[str]) -> dict[str, str]:
        ids = [eid for eid in dict.fromkeys(custom_emoji_ids) if eid]
        if not ids or not self._support.bot_token or not self._s3.enabled:
            return {}
        try:
            stickers = await self._get_custom_emoji_stickers(ids)
        except Exception:
            logger.warning("emoji_get_stickers_failed")
            return {}
        client = S3Client(self._s3)
        out: dict[str, str] = {}
        for sticker in stickers:
            custom_emoji_id = sticker.get("custom_emoji_id")
            file_id = self._thumb_file_id(sticker)
            if not custom_emoji_id or not file_id:
                continue
            try:
                url = await self._download_and_upload(client, custom_emoji_id, file_id)
            except Exception:
                logger.warning("emoji_asset_resolve_failed", custom_emoji_id=custom_emoji_id)
                continue
            if url:
                out[custom_emoji_id] = url
        return out

    async def _get_custom_emoji_stickers(self, ids: list[str]) -> list[dict]:
        url = f"{_TELEGRAM_API}/bot{self._support.bot_token}/getCustomEmojiStickers"
        timeout = float(self._support.media_proxy_timeout_sec)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params={"custom_emoji_ids": json.dumps(ids)})
        data = resp.json() if resp.content else {}
        if not data.get("ok"):
            return []
        return list(data.get("result") or [])

    @staticmethod
    def _thumb_file_id(sticker: dict) -> str | None:
        thumbnail = sticker.get("thumbnail") or {}
        return thumbnail.get("file_id") or sticker.get("file_id")

    async def _download_and_upload(
        self, client: S3Client, custom_emoji_id: str, file_id: str
    ) -> str | None:
        timeout = float(self._support.media_proxy_timeout_sec)
        file_path, mime = await resolve_file_path(
            bot_token=self._support.bot_token, file_id=file_id, timeout_sec=timeout
        )
        chunks: list[bytes] = []
        async for chunk in stream_file(
            bot_token=self._support.bot_token, file_path=file_path, timeout_sec=timeout
        ):
            chunks.append(chunk)
        data = b"".join(chunks)
        if not data:
            return None
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "webp"
        result = await client.upload_bytes(
            key=f"support/emoji/{custom_emoji_id}.{ext}",
            data=data,
            content_type=mime or "image/webp",
            cache_control="public, max-age=2592000",
        )
        return result.public_url
