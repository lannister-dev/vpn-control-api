from ipaddress import ip_address
from urllib.parse import urlencode, quote

from shared.profiles.exceptions import ProfileBuildError, ProfileRegionMismatchError
from shared.profiles.types import (
    NodePublic,
    ProfileType,
    RealityTcpProfile,
    WsTlsProfile,
)


class VlessUriBuilder:
    @staticmethod
    def build(
        *,
        client_id: str,
        node: NodePublic,
        profile: WsTlsProfile | RealityTcpProfile,
    ) -> str:
        if profile.metadata.region_support and node.region:
            if node.region not in profile.metadata.region_support:
                raise ProfileRegionMismatchError(
                    f"Profile {profile.metadata.display_name} "
                    f"not supported in region {node.region}"
                )

        if profile.type == ProfileType.ws_tls:
            return VlessUriBuilder._build_ws_tls(
                client_id=client_id,
                node=node,
                profile=profile,
            )

        if profile.type == ProfileType.reality_tcp:
            return VlessUriBuilder._build_reality_tcp(
                client_id=client_id,
                node=node,
                profile=profile,
            )

        raise ProfileBuildError(f"Unsupported profile type: {profile.type}")

    @staticmethod
    def _build_ws_tls(
        *,
        client_id: str,
        node: NodePublic,
        profile: WsTlsProfile,
    ) -> str:
        client = profile.client
        query = {
            "type": "ws",
            "security": "tls",
            "encryption": "none",
            "sni": client.sni,
            "host": client.host,
            "path": client.path,
        }
        q = urlencode(query, safe="/")
        host = VlessUriBuilder._format_host(node.domain)
        remark = node.remark or profile.metadata.display_name
        fragment = VlessUriBuilder._format_fragment(remark)
        return (
            f"vless://{client_id}@{host}:{node.port}"
            f"?{q}{fragment}"
        )

    @staticmethod
    def _build_reality_tcp(
        *,
        client_id: str,
        node: NodePublic,
        profile: RealityTcpProfile,
    ) -> str:
        client = profile.client
        query = {
            "type": "tcp",
            "security": "reality",
            "encryption": "none",
            "sni": client.sni,
            "fp": client.fingerprint,
            "pbk": client.public_key,
            "sid": client.short_id,
        }
        flow = client.resolve_flow()
        if flow:
            query["flow"] = flow
        if client.spider_x:
            query["spx"] = client.spider_x

        q = urlencode(query)
        host = VlessUriBuilder._format_host(node.domain)
        remark = node.remark or profile.metadata.display_name
        fragment = VlessUriBuilder._format_fragment(remark)
        return (
            f"vless://{client_id}@{host}:{node.port}"
            f"?{q}{fragment}"
        )

    @staticmethod
    def _format_host(host: str) -> str:
        if host.startswith("[") and host.endswith("]"):
            return host
        try:
            if ip_address(host).version == 6:
                return f"[{host}]"
        except ValueError:
            return host
        return host

    @staticmethod
    def _format_fragment(remark: str) -> str:
        if not remark:
            return ""
        return f"#{quote(remark, safe='')}"
