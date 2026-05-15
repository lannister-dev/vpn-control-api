import base64
from dataclasses import dataclass
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class VlessUri:
    client_id: str
    host: str
    port: int
    query: dict[str, str]
    remark: str = ""
    server_description: str | None = None

    def render(self) -> str:
        query = dict(self.query)
        if self.server_description:
            encoded = base64.b64encode(self.server_description.encode("utf-8")).decode("ascii")
            query["serverDescription"] = encoded
        q = urlencode(query, safe="/")
        fragment = f"#{quote(self.remark, safe='')}" if self.remark else ""
        return f"vless://{self.client_id}@{self.host}:{self.port}?{q}{fragment}"
