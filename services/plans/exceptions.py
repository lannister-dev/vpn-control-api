class PlanNotFound(Exception):
    """Plan not found by ID."""


class PlanAlreadyExists(Exception):
    """Plan with this name already exists."""
