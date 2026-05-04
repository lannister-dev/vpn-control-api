class EntryRoutingError(Exception):
    pass


class UnknownBackendTagError(EntryRoutingError):
    def __init__(self, tag: str, available: list[str]) -> None:
        super().__init__(
            f"backend_tag={tag!r} is not in the active pool; "
            f"available={available}"
        )
        self.tag = tag
        self.available = available
