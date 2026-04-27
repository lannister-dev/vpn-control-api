from __future__ import annotations

import re
from dataclasses import dataclass

from services.nodes.naming.catalog import CityInfo

NAME_RE = re.compile(r"^([a-z]{3})-([a-z]{1,10})-(\d{2,3})$")
MAX_ROUTE_NAME_LEN = 100


@dataclass(frozen=True)
class ParsedNodeName:
    city: CityInfo
    role: str
    index: int
