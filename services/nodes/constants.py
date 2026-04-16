"""Public constants for the nodes service (roles, default ports, etc.)."""

ROLE_BACKEND = "backend"
ROLE_ENTRY = "entry"
ROLE_WHITELIST_ENTRY = "whitelist_entry"

# Roles an agent may claim during /agent/initial bootstrap (X-Node-Role header).
# Must stay in sync with the allowed-roles list used by POST /admin/nodes.
ALLOWED_NODE_ROLES: frozenset[str] = frozenset(
    {ROLE_BACKEND, ROLE_ENTRY, ROLE_WHITELIST_ENTRY}
)
DEFAULT_NODE_ROLE = ROLE_BACKEND

# Default ports used when rendering installer / node-agent env.
DEFAULT_XRAY_API_PORT = 10085
DEFAULT_AGENT_PORT = 9000

HEARTBEAT_DETAILS_KEY = "heartbeat"
DRAIN_REASON_UNHEALTHY_HEARTBEAT = "unhealthy_heartbeat"
