"""praisonai serve: shared bind guard, cross-site refusal on keyless apps,
Host/Origin guard at run time on loopback binds."""

import json
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from praisonai.cli.features.serve import ServeHandler

YAML = ("framework: praisonai\nroles:\n  r:\n    role: r\n    goal: g\n    backstory: b\n"
        "    tasks:\n      t:\n        description: d\n        expected_output: o\n")


@pytest.fixture
def agents_file(tmp_path, monkeypatch):
    monkeypatch.delenv("PRAISONAI_SERVE_API_KEY", raising=False)
    monkeypatch.delenv("A2U_AUTH_TOKEN", raising=False)
    f = tmp_path / "agents.yaml"
    f.write_text(YAML)
    return str(f)


def _cfg(f, host="127.0.0.1", **kw):
    return {"file": f, "host": host, "port": 8765, "path": "/agents", **kw}


def test_public_bind_without_key_uses_shared_guard(agents_file):
    from praisonaiagents.agent import launch_security

    with patch.object(launch_security, "require_bind_token",
                      wraps=launch_security.require_bind_token) as guard:
        with pytest.raises(SystemExit, match="PRAISONAI_SERVE_API_KEY"):
            ServeHandler()._create_agents_app(_cfg(agents_file, "0.0.0.0"))
    guard.assert_called_once()


def test_keyless_app_refuses_cross_site_simple_post(agents_file):
    ran = []

    async def fake_arun(**kw):
        ran.append(kw)
        return "ran"

    with patch("praisonai.arun", fake_arun, create=True):
        client = TestClient(ServeHandler()._create_agents_app(_cfg(agents_file)))
        hdr = {"Content-Type": "text/plain", "Origin": "http://foreign.example"}
        resp = client.post("/agents/r", content=json.dumps({"query": "x"}), headers=hdr)
    assert resp.status_code == 403
    assert not ran


def test_keyless_app_still_serves_same_origin_requests(agents_file):
    client = TestClient(ServeHandler()._create_agents_app(_cfg(agents_file)))
    assert client.get("/health", headers={"Origin": "http://localhost:8765"}).status_code != 403


def test_run_server_guards_loopback_host_header():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    with patch("uvicorn.run") as run:
        ServeHandler()._run_server(app, "127.0.0.1", 8765, False)
    served = run.call_args.args[0]
    client = TestClient(served, base_url="http://foreign.example:8765")
    assert client.get("/").status_code == 403
    assert TestClient(served, base_url="http://127.0.0.1:8765").get("/").status_code == 200


def test_a2u_public_bind_without_token_is_denied(monkeypatch):
    monkeypatch.delenv("A2U_AUTH_TOKEN", raising=False)
    assert ServeHandler().cmd_a2u(["--host", "0.0.0.0"]) == 4
