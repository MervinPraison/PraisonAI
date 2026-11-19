"""rag serve, AgentOS and the call server bind through the shared guard."""

from unittest.mock import patch

import pytest

from praisonaiagents.agent import launch_security


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("PRAISONAI_SERVE_API_KEY", "PRAISONAI_AGENTOS_API_KEY", "CALL_SERVER_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def _rag(*args):
    pytest.importorskip("fastapi")
    from typer.testing import CliRunner

    from praisonai.cli.commands.rag import app as rag_app

    with patch("uvicorn.run") as run, patch("praisonaiagents.rag.RAG"), \
            patch("praisonaiagents.knowledge.Knowledge"):
        res = CliRunner().invoke(rag_app, ["serve", *args])
    return res, run


def test_rag_serve_public_bind_without_key_refuses():
    res, run = _rag("--host", "0.0.0.0")
    run.assert_not_called()
    assert "refuses to bind non-loopback" in res.output


def test_rag_serve_public_bind_with_key_requires_it():
    from fastapi.testclient import TestClient

    res, run = _rag("--host", "0.0.0.0", "--api-key", "k-1")
    app = run.call_args.args[0]
    client = TestClient(app)
    assert client.post("/rag/query", json={"question": "q"}).status_code == 401
    assert client.get("/health").status_code == 200


def test_rag_serve_loopback_refuses_rebound_host():
    from fastapi.testclient import TestClient

    res, run = _rag()
    app = run.call_args.args[0]
    assert TestClient(app, base_url="http://foreign.example").get("/health").status_code == 403


def test_agentos_uses_shared_guard_and_keeps_runtime_error():
    pytest.importorskip("fastapi")
    from praisonai.app.agentos import AgentOS

    os_ = AgentOS(agents=[])
    with patch("uvicorn.run") as run, patch.object(
        launch_security, "require_bind_token", wraps=launch_security.require_bind_token
    ) as guard:
        with pytest.raises(RuntimeError, match="refuses to bind non-loopback"):
            os_.serve(host="0.0.0.0")
    guard.assert_called_once()
    run.assert_not_called()


def test_call_server_public_bind_needs_call_server_token(monkeypatch):
    from praisonai.api import call

    monkeypatch.setattr(call, "OPENAI_API_KEY", "sk-test", raising=False)
    with patch("uvicorn.run") as run:
        with pytest.raises(ValueError, match="CALL_SERVER_TOKEN"):
            call.run_server(port=1, host="0.0.0.0")
    run.assert_not_called()
