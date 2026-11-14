"""Regression tests for #6336: AgentOS auth fail-closed on public bind."""
from unittest.mock import patch

import pytest


def test_serve_refuses_public_bind_without_api_key(monkeypatch):
    pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from praisonai import AgentOS
    from praisonaiagents import AgentOSConfig

    monkeypatch.delenv("PRAISONAI_AGENTOS_API_KEY", raising=False)
    app = AgentOS(agents=[], config=AgentOSConfig(host="0.0.0.0"))
    with patch("uvicorn.run") as run, pytest.raises(RuntimeError, match="API key"):
        app.serve()
    run.assert_not_called()


@pytest.mark.parametrize("cfg", [{"host": "127.0.0.1"}, {"host": "0.0.0.0", "api_key": "k"}])
def test_serve_allows_loopback_or_authenticated(monkeypatch, cfg):
    pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from praisonai import AgentOS
    from praisonaiagents import AgentOSConfig

    monkeypatch.delenv("PRAISONAI_AGENTOS_API_KEY", raising=False)
    app = AgentOS(agents=[], config=AgentOSConfig(**cfg))
    with patch("uvicorn.run") as run:
        app.serve()
    assert run.call_args.kwargs["host"] == cfg["host"]


def test_serve_logs_bound_host(monkeypatch, caplog):
    pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from praisonai import AgentOS
    from praisonaiagents import AgentOSConfig

    monkeypatch.delenv("PRAISONAI_AGENTOS_API_KEY", raising=False)
    app = AgentOS(agents=[], config=AgentOSConfig())
    with patch("uvicorn.run"), caplog.at_level("WARNING"):
        app.serve()
    assert "binding to 127.0.0.1:8000" in caplog.text
    assert "0.0.0.0" in caplog.text  # tells Docker users how to expose


def test_cli_default_host_is_loopback():
    from praisonai.cli.commands.app import app_command
    host = next(p for p in app_command.params if p.name == "host")
    assert host.default == "127.0.0.1"


def test_serve_checks_key_of_cached_app(monkeypatch):
    pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    from praisonai import AgentOS
    from praisonaiagents import AgentOSConfig

    monkeypatch.delenv("PRAISONAI_AGENTOS_API_KEY", raising=False)
    app = AgentOS(agents=[], config=AgentOSConfig(host="0.0.0.0"))
    app.get_app()  # built without auth
    app.config.api_key = "late"
    with patch("uvicorn.run") as run, pytest.raises(RuntimeError, match="API key"):
        app.serve()
    run.assert_not_called()


def test_default_host_is_loopback():
    from praisonaiagents import AgentOSConfig
    assert AgentOSConfig().host == "127.0.0.1"
