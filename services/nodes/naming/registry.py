from __future__ import annotations

from services.nodes.naming.catalog import CITIES, CityInfo
from services.nodes.naming.display import flag_emoji
from services.nodes.naming.name import (
    MAX_ROUTE_NAME_LEN,
    NAME_RE,
    ParsedNodeName,
)
from services.nodes.naming.roles import SHORT_TO_ROLE
from services.nodes.naming.transport import transport_short_code


class NamingRegistry:
    def __init__(self, cities: tuple[CityInfo, ...] = CITIES):
        self._by_iata: dict[str, CityInfo] = {c.iata: c for c in cities}

    def city_by_iata(self, iata: str | None) -> CityInfo | None:
        if not iata:
            return None
        return self._by_iata.get(iata.strip().lower())

    def parse_node_name(self, name: str | None) -> ParsedNodeName | None:
        if not isinstance(name, str):
            return None
        match = NAME_RE.match(name.strip().lower())
        if not match:
            return None
        iata, role_short, idx = match.group(1), match.group(2), match.group(3)
        city = self.city_by_iata(iata)
        role = SHORT_TO_ROLE.get(role_short)
        if city is None or role is None:
            return None
        return ParsedNodeName(city=city, role=role, index=int(idx))

    def canonical_route_name(
        self,
        *,
        entry_name: str | None,
        backend_name: str,
        transport_profile_name: str,
    ) -> str:
        short = transport_short_code(transport_profile_name)
        if entry_name:
            base = f"{entry_name}→{backend_name}·{short}"
        else:
            base = f"{backend_name}·{short}"
        return base[:MAX_ROUTE_NAME_LEN]

    def happ_display_for_name(self, name: str | None) -> str | None:
        parsed = self.parse_node_name(name)
        if parsed is None:
            return None
        return f"{flag_emoji(parsed.city.country)} {parsed.city.country_name}"


registry = NamingRegistry()
