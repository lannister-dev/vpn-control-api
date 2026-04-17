from enum import Enum


class RouteNodeRole(str, Enum):
    backend = "backend"
    entry = "entry"
    whitelist_entry = "whitelist_entry"

# Roles allowed as entry_node_id on a Route.
ENTRY_NODE_ROLES: frozenset[RouteNodeRole] = frozenset(
    {RouteNodeRole.entry, RouteNodeRole.whitelist_entry}
)
