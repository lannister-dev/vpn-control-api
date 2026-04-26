from __future__ import annotations

from ipaddress import ip_address

from shared.profiles.exceptions import ProfileBuildError, ProfileRegionMismatchError
from shared.profiles.schemas import (
    NodePublic,
    ProfileType,
    RealityTcpProfile,
    RealityTcpQuery,
    WsTlsProfile,
    WsTlsQuery,
)
from shared.profiles.transport import VlessUri


class VlessUriBuilder:
    @staticmethod
    def build(
        *,
        client_id: str,
        node: NodePublic,
        profile: WsTlsProfile | RealityTcpProfile,
    ) -> str:
        if (
            profile.metadata.region_support
            and node.region
            and node.region not in profile.metadata.region_support
        ):
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

        query = WsTlsQuery(
                type="ws",
                security="tls",
                encryption="none",
                sni=client.sni,
                host=client.host,
                path=client.path,
        )
        host = VlessUriBuilder._format_host(node.domain)
        remark = node.remark or profile.metadata.display_name

        return VlessUri(
            client_id=client_id,
            host=host,
            port=node.port,
            query=query.to_query(),
            remark=remark,
            server_description=node.server_description,
        ).render()


    @staticmethod
    def _build_reality_tcp(
        *,
        client_id: str,
        node: NodePublic,
        profile: RealityTcpProfile,
    ) -> str:
        client = profile.client
        query = RealityTcpQuery(
                type="tcp",
                security="reality",
                encryption="none",
                sni=client.sni,
                fp=client.fingerprint,
                pbk=client.public_key,
                sid=client.short_id,
        )
        flow = client.resolve_flow()
        if flow:
            query.flow = flow
        if client.spider_x:
            query.spx = client.spider_x

        host = VlessUriBuilder._format_host(node.domain)
        remark = node.remark or profile.metadata.display_name

        return VlessUri(
             client_id=client_id,
             host=host,
             port=node.port,
             query=query.to_query(),
             remark=remark,
             server_description=node.server_description,
        ).render()

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