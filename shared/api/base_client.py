from __future__ import annotations

from typing import Any

import httpx


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class BaseApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        timeout_s: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.close()
            self._client = None

    async def get(
        self,
        path: str,
        *,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        client = await self._get_client()
        r = await client.get(
            f"{self._base_url}{path}", params=params, headers=headers,
        )
        if r.status_code >= 400:
            raise HttpError(r.status_code, r.text)
        return r.json()

    async def post(
        self,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        client = await self._get_client()
        r = await client.post(
            f"{self._base_url}{path}", json=json, params=params, headers=headers,
        )
        if r.status_code >= 400:
            raise HttpError(r.status_code, r.text)
        if not r.text:
            return None
        return r.json()
