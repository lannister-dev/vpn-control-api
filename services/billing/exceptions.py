class OrderNotFound(Exception):
    """Payment order not found."""


class OrderAlreadyProcessed(Exception):
    """Payment order has already been processed (idempotency guard)."""


class InsufficientBalance(Exception):
    """User balance is not enough for the operation."""


class PlanNotPurchasable(Exception):
    """Plan cannot be purchased (inactive or zero price)."""


class ProviderError(Exception):
    """Payment provider returned an error or is unavailable."""


class WebhookVerificationFailed(Exception):
    """Webhook signature verification failed."""


class OrderExpired(Exception):
    """Payment order has expired."""
