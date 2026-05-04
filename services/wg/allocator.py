from __future__ import annotations

from ipaddress import IPv4Network

from services.wg.exceptions import WgMeshAddressPoolExhaustedError


def allocate_next_ip(*, cidr: str, used: set[str], reserved: int = 1) -> str:
    network = IPv4Network(cidr, strict=False)
    used_set = {addr.strip() for addr in used if addr}
    hosts = list(network.hosts())
    for idx, host in enumerate(hosts):
        if idx < reserved:
            continue
        ip = str(host)
        if ip not in used_set:
            return ip
    raise WgMeshAddressPoolExhaustedError(
        f"no free addresses left in {cidr} (used {len(used_set)} of {len(hosts)})"
    )
