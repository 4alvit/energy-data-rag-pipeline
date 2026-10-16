"""Exercise HTTP session cleanup through the actual production MCP application."""

import time

from starlette.testclient import TestClient

from energy_rag.mcp_server import create_mcp_server

HEADERS = {"Accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "session-regression", "version": "1"},
    },
}


def test_full_session_pool_recovers_after_delete():
    app = create_mcp_server().streamable_http_app(
        json_response=True, max_sessions=1, session_idle_timeout=30
    )
    with TestClient(app, base_url="http://127.0.0.1:8000", headers=HEADERS) as client:
        first = client.post("/mcp", json=INITIALIZE)
        assert first.status_code == 200
        session = first.headers["mcp-session-id"]
        assert client.post("/mcp", json=INITIALIZE).status_code == 503
        assert client.delete("/mcp", headers={"mcp-session-id": session}).status_code == 200
        replacement = client.post("/mcp", json=INITIALIZE)
        assert replacement.status_code == 200
        assert replacement.headers["mcp-session-id"] != session


def test_expired_session_is_removed_and_releases_capacity():
    app = create_mcp_server().streamable_http_app(
        json_response=True, max_sessions=1, session_idle_timeout=0.05
    )
    with TestClient(app, base_url="http://127.0.0.1:8000", headers=HEADERS) as client:
        first = client.post("/mcp", json=INITIALIZE)
        assert first.status_code == 200
        session = first.headers["mcp-session-id"]
        time.sleep(0.2)
        expired = client.post(
            "/mcp",
            headers={"mcp-session-id": session},
            json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
        )
        assert expired.status_code == 404
        assert client.post("/mcp", json=INITIALIZE).status_code == 200


def test_rejected_opening_request_releases_capacity():
    app = create_mcp_server().streamable_http_app(
        json_response=True, max_sessions=1, session_idle_timeout=30
    )
    with TestClient(app, base_url="http://127.0.0.1:8000", headers=HEADERS) as client:
        rejected = client.post("/mcp", json=INITIALIZE, headers={"Accept": "text/plain"})
        assert rejected.status_code == 406
        assert client.post("/mcp", json=INITIALIZE).status_code == 200
