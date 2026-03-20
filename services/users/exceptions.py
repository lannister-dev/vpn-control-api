class UserNotFound(Exception):
    """User not found by ID."""


class UserAlreadyExists(Exception):
    """User with this telegram_id already exists."""
