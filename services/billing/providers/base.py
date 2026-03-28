from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class ProviderCreateResult:
    external_id: str
    payment_url: str
    provider_meta: str | None = None


@dataclass(frozen=True)
class WebhookResult:
    external_id: str
    amount_rub: float
    provider_meta: str | None = None


class PaymentProvider(ABC):
    @abstractmethod
    async def create_payment(
        self, *, order_id: str, amount_rub: float, description: str
    ) -> ProviderCreateResult:
        ...

    @abstractmethod
    async def verify_webhook(self, request: Request) -> WebhookResult:
        ...
