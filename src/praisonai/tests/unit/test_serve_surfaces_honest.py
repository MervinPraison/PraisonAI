"""Regression tests: serve surfaces deliver what they advertise (issue #5973)."""

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from praisonai.cli.features.serve import ServeHandler


@pytest.fixture
def agents_file(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("framework: praisonai\nroles: {}\n")
    return str(path)


@pytest.fixture
def fake_arun(monkeypatch):
    import praisonai

    calls = []

    async def _arun(**kwargs):
        calls.append(kwargs)
        return f"agent says: {kwargs['cli_config']['topic']}"

    monkeypatch.setattr(praisonai, "arun", _arun, raising=False)
    return calls


def _send(client, text):
    return client.post("/a2a", json={
        "jsonrpc": "2.0", "id": 1, "method": "message/send",
        "params": {"message": {"parts": [{"type": "text", "text": text}]}},
    }).json()


def test_a2a_message_send_runs_agent(agents_file, fake_arun):
    app = ServeHandler()._create_a2a_app(
        {"host": "127.0.0.1", "port": 8082, "file": agents_file}
    )
    body = _send(TestClient(app), "summarize this")
    assert body["result"]["message"]["parts"][0]["text"] == "agent says: summarize this"
    assert fake_arun[0]["agent_file"] == agents_file
    assert fake_arun[0]["framework"] == "praisonai"


def test_a2a_requires_api_key_off_localhost(agents_file, monkeypatch):
    monkeypatch.delenv("PRAISONAI_SERVE_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        ServeHandler()._create_a2a_app(
            {"host": "0.0.0.0", "port": 8082, "file": agents_file}
        )


def test_a2a_missing_file_rejected(tmp_path):
    rc = ServeHandler().cmd_a2a(["--file", str(tmp_path / "missing.yaml")])
    assert rc == ServeHandler.EXIT_VALIDATION_ERROR


def _advertised_providers(client):
    doc = client.get("/__praisonai__/discovery").json()
    return {p["type"] for p in doc["providers"]}


def test_unified_mounts_every_advertised_provider(agents_file, fake_arun):
    app = ServeHandler()._create_unified_app(
        {"host": "127.0.0.1", "port": 8765, "file": agents_file}
    )
    client = TestClient(app)
    assert _advertised_providers(client) == {"agents-api", "a2a", "a2u"}
    assert client.post("/agents", json={"query": "hi"}).json() == {"response": "agent says: hi"}
    assert _send(client, "hey")["result"]["message"]["parts"][0]["text"] == "agent says: hey"


def test_unified_without_yaml_only_advertises_a2u(tmp_path):
    app = ServeHandler()._create_unified_app(
        {"host": "127.0.0.1", "port": 8765, "file": str(tmp_path / "missing.yaml")}
    )
    client = TestClient(app)
    assert _advertised_providers(client) == {"a2u"}
    assert client.post("/agents", json={"query": "hi"}).status_code in (404, 405)


def test_discovery_route_serves_document():
    app = ServeHandler()._create_a2u_app({"host": "127.0.0.1", "port": 8083})
    resp = TestClient(app).get("/__praisonai__/discovery")
    assert resp.status_code == 200


def test_http_register_is_not_a_silent_success(monkeypatch):
    from praisonai.api import agent_invoke

    monkeypatch.setenv("CALL_SERVER_TOKEN", "t")
    app = FastAPI()
    app.include_router(agent_invoke.router)
    resp = TestClient(app).post(
        "/api/v1/agents/foo/register", headers={"Authorization": "Bearer t"}
    )
    assert resp.status_code == 501
