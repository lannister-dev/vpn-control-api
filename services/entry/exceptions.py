class EntryNotFoundError(LookupError):
    pass


class BackendNotFoundError(LookupError):
    pass


class EntryRoleError(ValueError):
    pass


class EntryZoneMismatchError(ValueError):
    pass