import base64
from dataclasses import dataclass
from urllib.parse import quote, urlencode


# Happ enforces a 30-char limit on serverDescription (decoded UTF-8).
# Longer values are dropped silently by the client.
SERVER_DESCRIPTION_MAX_CHARS = 30


@dataclass(frozen=True)
class VlessUri:
    client_id: str
    host: str
    port: int
    query: dict[str, str]
    remark: str = ""
    server_description: str | None = None

    def render(self) -> str:
        q = urlencode(self.query, safe="/")
        remark_part = quote(self.remark, safe="") if self.remark else ""
        fragment = ""
        if remark_part or self.server_description:
            fragment = f"#{remark_part}"
            desc = (self.server_description or "")[:SERVER_DESCRIPTION_MAX_CHARS]
            if desc:
                encoded = base64.b64encode(desc.encode("utf-8")).decode("ascii")
                fragment = f"{fragment}?serverDescription={encoded}"
        return f"vless://{self.client_id}@{self.host}:{self.port}?{q}{fragment}"
