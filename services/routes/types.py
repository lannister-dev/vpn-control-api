from enum import Enum


class RouteNodeRole(str, Enum):
    backend = "backend"
    whitelist_entry = "whitelist_entry"
