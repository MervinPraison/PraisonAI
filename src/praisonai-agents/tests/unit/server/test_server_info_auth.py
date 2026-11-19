"""AgentServer ``/info`` requires the token when one is set; ``/health`` stays open."""

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient

from praisonaiagents.server.server import AgentServer, ServerConfig

TOKEN = "s3cret-token"


def _client(token=None):
    return TestClient(AgentServer(config=ServerConfig(auth_token=token))._create_app())


def test_info_requires_token_when_set():
    client = _client(TOKEN)
    assert client.get("/info").status_code == 401
    assert client.get("/info", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/info", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200
    assert ok.json()["name"] == "PraisonAI Agent Server"
    assert client.get("/info", headers={"X-Auth-Token": TOKEN}).status_code == 200


def test_health_is_open_but_status_only_without_token():
    client = _client(TOKEN)
    anon = client.get("/health")
    assert anon.status_code == 200
    assert anon.json() == {"status": "ok"}
    authed = client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert authed["status"] == "ok" and "clients" in authed and "timestamp" in authed


def test_no_token_keeps_local_dev_open():
    client = _client()
    assert client.get("/info").status_code == 200
    body = client.get("/health").json()
    assert body["status"] == "ok" and "clients" in body
