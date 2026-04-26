import json
import logging
from typing import Any

from shared.utils.request_context import get_request_id


class StructuredLogger:
    def __init__(self, logger: logging.Logger):
        self._log = logger

    def _format(self, msg: str, fields: dict[str, Any]) -> str:
        rid = get_request_id()
        if rid and "request_id" not in fields:
            fields = {"request_id": rid, **fields}
        if not fields:
            return msg
        return f"{msg} | {json.dumps(fields, ensure_ascii=False, default=str)}"

    def debug(self, msg: str, **fields: Any) -> None:
        self._log.debug(self._format(msg, fields))

    def info(self, msg: str, **fields: Any) -> None:
        self._log.info(self._format(msg, fields))

    def warning(self, msg: str, **fields: Any) -> None:
        self._log.warning(self._format(msg, fields))

    def error(self, msg: str, **fields: Any) -> None:
        self._log.error(self._format(msg, fields))

    def exception(self, msg: str, **fields: Any) -> None:
        self._log.exception(self._format(msg, fields))