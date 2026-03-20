import hashlib
import secrets


class SubscriptionUtils:
    @staticmethod
    def generate() -> str:
        return secrets.token_urlsafe(32).replace("-", "_")

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()