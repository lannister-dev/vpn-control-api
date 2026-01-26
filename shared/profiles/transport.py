from dataclasses import dataclass
from urllib.parse import urlencode, quote


@dataclass(frozen=True)
class VlessUri:
    client_id: str
    host: str
    port: int
    query: dict[str, str]
    remark: str = ""

    def render(self) -> str:
        q = urlencode(self.query, safe="/")
        fragment = f"#{quote(self.remark, safe='')}" if self.remark else ""
        return f"vless://{self.client_id}@{self.host}:{self.port}?{q}{fragment}"
