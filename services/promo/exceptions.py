class PromoError(Exception):
    pass


class PromoNotFound(PromoError):
    pass


class PromoCodeExists(PromoError):
    pass


class PromoInvalid(PromoError):
    """Code inactive, outside its window, or below min amount."""


class PromoExhausted(PromoError):
    """Total or per-user activation limit reached."""


class PromoNotEligible(PromoError):
    """User/plan/order-type does not match the code's targeting."""
