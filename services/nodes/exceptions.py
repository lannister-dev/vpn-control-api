class NodeBootstrapConflictError(ValueError):
    pass


class AdminNodeCreateError(ValueError):
    pass


class AdminNodeNotFoundError(LookupError):
    pass


class AdminNodeAlreadyBootstrappedError(ValueError):
    pass