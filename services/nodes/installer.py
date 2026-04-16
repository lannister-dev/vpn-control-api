"""Render the k3s-agent installer bash script served by GET /agent/install.sh."""
from pathlib import Path

from services.config import get_settings
from services.nodes.models import VpnNode

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "install_agent.sh.tmpl"

# Characters allowed inside values we splat into the shell template. The
# template wraps each variable in double quotes, but we still refuse any value
# containing a quote, backslash, or newline because those would let a
# misconfigured node name break out of the string context.
_UNSAFE_CHARS = set("\"'\\\n\r`$")


def _ensure_safe(name: str, value: str) -> str:
    if any(c in _UNSAFE_CHARS for c in value):
        raise ValueError(f"unsafe character in {name} for installer template")
    return value


def render_install_script(*, node: VpnNode, raw_bootstrap_token: str) -> str:
    """Produce a ready-to-execute bash script for `node` using `raw_bootstrap_token`."""
    settings = get_settings()
    k3s = settings.k3s
    if not k3s.server_url or not k3s.node_token:
        raise RuntimeError("K3S_URL / K3S_NODE_TOKEN are not configured on control-api")
    if not k3s.public_base_url:
        raise RuntimeError("CONTROL_API_PUBLIC_URL is not configured on control-api")
    if k3s.channel not in ("dev", "prod"):
        raise RuntimeError("CHANNEL must be set to 'dev' or 'prod' on control-api")

    substitutions = {
        "NODE_ID": _ensure_safe("NODE_ID", str(node.id)),
        "NODE_NAME": _ensure_safe("NODE_NAME", node.name),
        "NODE_ROLE": _ensure_safe("NODE_ROLE", node.role),
        "NODE_REGION": _ensure_safe("NODE_REGION", node.region or "unknown"),
        "CHANNEL": _ensure_safe("CHANNEL", k3s.channel),
        "K3S_URL": _ensure_safe("K3S_URL", k3s.server_url),
        "K3S_TOKEN": _ensure_safe("K3S_TOKEN", k3s.node_token),
        "K3S_VERSION": _ensure_safe("K3S_VERSION", k3s.version or ""),
        "CONTROL_API_URL": _ensure_safe("CONTROL_API_URL", k3s.public_base_url),
        "BOOTSTRAP_TOKEN": _ensure_safe("BOOTSTRAP_TOKEN", raw_bootstrap_token),
    }

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered
