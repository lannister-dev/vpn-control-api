import base64
from dataclasses import dataclass
from urllib.parse import urlencode, quote


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
            if self.server_description:
                encoded = base64.b64encode(self.server_description.encode("utf-8")).decode("ascii")
                fragment = f"{fragment}?serverDescription={encoded}"
        return f"vless://{self.client_id}@{self.host}:{self.port}?{q}{fragment}"
