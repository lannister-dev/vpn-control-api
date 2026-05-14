from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aioboto3
from botocore.config import Config as BotoConfig

from services.config import S3Config
from shared.utils.logger import StructuredLogger

logger = StructuredLogger(logging.getLogger("s3-client"))


@dataclass(slots=True, frozen=True)
class S3UploadResult:
    key: str
    public_url: str
    content_type: str
    size: int


class S3Client:
    def __init__(self, config: S3Config) -> None:
        if not config.enabled:
            raise RuntimeError("S3 not configured (missing bucket/access_key/secret_key)")
        self._config = config
        self._session = aioboto3.Session()
        self._boto_config = BotoConfig(
            region_name=config.region or None,
            s3={"addressing_style": config.addressing_style},
            retries={"max_attempts": 3, "mode": "standard"},
        )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator:
        async with self._session.client(
            "s3",
            endpoint_url=self._config.endpoint_url or None,
            aws_access_key_id=self._config.access_key,
            aws_secret_access_key=self._config.secret_key,
            region_name=self._config.region or None,
            config=self._boto_config,
        ) as client:
            yield client

    async def upload_bytes(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        cache_control: str | None = None,
    ) -> S3UploadResult:
        extra = {"ContentType": content_type}
        if cache_control:
            extra["CacheControl"] = cache_control
        async with self._client() as client:
            await client.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=data,
                **extra,
            )
        return S3UploadResult(
            key=key,
            public_url=self.public_url(key),
            content_type=content_type,
            size=len(data),
        )

    async def presigned_get_url(self, key: str, *, ttl_sec: int | None = None) -> str:
        ttl = ttl_sec or self._config.presigned_ttl_sec
        async with self._client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket, "Key": key},
                ExpiresIn=ttl,
            )

    async def delete(self, key: str) -> None:
        async with self._client() as client:
            await client.delete_object(Bucket=self._config.bucket, Key=key)

    def public_url(self, key: str) -> str:
        base = (self._config.public_base_url or "").rstrip("/")
        if base:
            return f"{base}/{key.lstrip('/')}"
        endpoint = (self._config.endpoint_url or "").rstrip("/")
        if endpoint:
            if self._config.addressing_style == "path":
                return f"{endpoint}/{self._config.bucket}/{key.lstrip('/')}"
            return f"{endpoint}/{key.lstrip('/')}"
        return f"s3://{self._config.bucket}/{key.lstrip('/')}"
