class SubscriptionError(Exception):
    """Base subscription error."""


class SubscriptionNotFound(SubscriptionError):
    """Subscription not found by token or ID."""


class SubscriptionExpired(SubscriptionError):
    """Rate limit exceeded for subscription access."""
    pass

class SubscriptionRateLimited(SubscriptionError):
    pass

class SubscriptionInactive(SubscriptionError):
    pass


class SubscriptionBuild(SubscriptionError):
    """Failed to build subscription config."""
    pass


class SubscriptionBuildUnavailable(SubscriptionBuild):
    pass


class SubscriptionHwidRequired(SubscriptionError):
    """Subscription requires x-hwid header (device identification)."""


class SubscriptionDeviceLimitReached(SubscriptionError):
    """Subscription device limit reached."""
