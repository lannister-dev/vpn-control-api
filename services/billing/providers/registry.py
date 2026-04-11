from __future__ import annotations

from services.billing.providers.base import PaymentProvider
from services.billing.providers.crypto import CryptoProvider
from services.billing.providers.freekassa import FreeKassaProvider
from services.billing.providers.platega import PlategaProvider


PROVIDERS: dict[str, type[PaymentProvider]] = {
    "crypto": CryptoProvider,
    "freekassa": FreeKassaProvider,
    "platega": PlategaProvider,
}
