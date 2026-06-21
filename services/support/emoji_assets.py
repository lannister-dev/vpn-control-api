from __future__ import annotations

import json
import logging

import httpx

from services.config import S3Config, SupportConfig
from shared.s3.client import S3Client
from shared.telegram.file_proxy import resolve_file_path, stream_file
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("support-emoji-assets"))

_TELEGRAM_API = "https://api.telegram.org"


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
