"""serve openai: shared bind guard and loopback Host/Origin guard."""

import json
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from praisonai_code.cli.commands.serve import app as serve_app


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("PRAISONAI_SERVE_API_KEY", raising=False)


def _serve(*args):
    with patch("uvicorn.run") as run:
        res = CliRunner().invoke(serve_app, ["openai", *args])
    return res, run


def test_public_bind_without_key_refuses():
    res, run = _serve("--host", "0.0.0.0")
    assert res.exit_code != 0
    run.assert_not_called()


def test_public_bind_with_key_starts():
    res, run = _serve("--host", "0.0.0.0", "--api-key", "k")
    assert run.call_args.kwargs["host"] == "0.0.0.0"


def test_loopback_server_refuses_rebound_host_and_cross_site_post():
    res, run = _serve()
    served = run.call_args.args[0]
    rebound = TestClient(served, base_url="http://foreign.example:8765")
    assert rebound.get("/v1/models").status_code == 403
    local = TestClient(served, base_url="http://127.0.0.1:8765")
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    resp = local.post("/v1/chat/completions", content=body,
                      headers={"Content-Type": "text/plain", "Origin": "http://foreign.example"})
    assert resp.status_code == 403


def test_warm_runtime_bind_goes_through_shared_guard(tmp_path):
    from praisonaiagents.agent import launch_security
    from praisonai_code.runtime import server as rt

    with patch.object(launch_security, "require_bind_token", side_effect=ValueError("stop")) as guard:
        with pytest.raises(ValueError, match="stop"):
            rt.serve_runtime(host="127.0.0.1", port=0, project_path=str(tmp_path))
    guard.assert_called_once()
