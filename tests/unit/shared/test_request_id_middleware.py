from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from shared.middlewares.request_id import add_request_id_middleware
from shared.utils.logger import StructuredLogger
from shared.utils.request_context import REQUEST_ID_HEADER, get_request_id


@pytest.fixture
def app():
    app = FastAPI()
    add_request_id_middleware(app)

    @app.get("/echo")
    def echo():
        return {"rid": get_request_id()}

    return app


def test_middleware_mints_request_id_when_absent(app):
    with TestClient(app) as client:
        resp = client.get("/echo")
    assert resp.status_code == 200
    rid = resp.headers.get(REQUEST_ID_HEADER)
    assert rid
    assert len(rid) >= 16
    assert resp.json()["rid"] == rid


def test_middleware_preserves_inbound_request_id(app):
    with TestClient(app) as client:
        resp = client.get("/echo", headers={REQUEST_ID_HEADER: "client-trace-1"})
    assert resp.headers.get(REQUEST_ID_HEADER) == "client-trace-1"
    assert resp.json()["rid"] == "client-trace-1"


def test_structured_logger_includes_request_id(caplog, app):
    log = StructuredLogger(logging.getLogger("test-rid"))
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="test-rid"):
        from shared.utils.request_context import set_request_id
        set_request_id("rid-abc")
        try:
            log.info("test_event", foo="bar")
        finally:
            set_request_id(None)
    msg = caplog.records[-1].getMessage()
    assert '"request_id": "rid-abc"' in msg
    assert '"foo": "bar"' in msg


def test_request_id_resets_between_requests(app):
    with TestClient(app) as client:
        r1 = client.get("/echo", headers={REQUEST_ID_HEADER: "rid-1"})
        r2 = client.get("/echo", headers={REQUEST_ID_HEADER: "rid-2"})
        r3 = client.get("/echo")
    assert r1.json()["rid"] == "rid-1"
    assert r2.json()["rid"] == "rid-2"
    assert r3.json()["rid"] != "rid-1"
    assert r3.json()["rid"] != "rid-2"
