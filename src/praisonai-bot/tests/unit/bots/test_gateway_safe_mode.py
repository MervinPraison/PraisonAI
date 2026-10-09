"""Gateway safe mode (#5747): PRAISONAI_NO_PLUGINS skips inbound YAML hooks."""

from __future__ import annotations

import pytest

pytest.importorskip("praisonai_bot.gateway.server")

from praisonai_bot.gateway.server import WebSocketGateway  # noqa: E402

_HOOKS = {"hooks": [{"path": "deploy", "agent": "a", "message": "hi"}]}


def _bare_server():
    srv = object.__new__(WebSocketGateway)
    srv._hooks = {}
    srv._hook_idem = None
    srv._hook_idempotency_backend = None
    return srv


def test_hooks_registered_by_default(monkeypatch):
    monkeypatch.delenv("PRAISONAI_NO_PLUGINS", raising=False)
    srv = _bare_server()
    srv._apply_hooks_from_config(_HOOKS)
    assert srv.list_hooks() == ["deploy"]


def test_safe_mode_skips_hooks(monkeypatch, caplog):
    monkeypatch.setenv("PRAISONAI_NO_PLUGINS", "1")
    srv = _bare_server()
    srv._hooks = {"stale": object()}
    with caplog.at_level("WARNING"):
        srv._apply_hooks_from_config(_HOOKS)
    assert srv.list_hooks() == []
    assert "SAFE MODE" in caplog.text


def test_cli_flag_sets_env(monkeypatch):
    from typer.testing import CliRunner

    from praisonai_bot.cli.commands import gateway as gw

    monkeypatch.delenv("PRAISONAI_NO_PLUGINS", raising=False)
    seen = {}

    class _Handler:
        def start(self, **kwargs):
            import os

            seen["env"] = os.environ.get("PRAISONAI_NO_PLUGINS")
            seen["safe_mode"] = kwargs.get("safe_mode")
            return 0

    monkeypatch.setattr(
        "praisonai_bot.cli.features.gateway.GatewayHandler", _Handler
    )
    result = CliRunner().invoke(
        gw.app, ["start", "--agents", "agents.yaml", "--safe-mode"]
    )
    assert result.exit_code == 0, result.output
    assert seen["env"] == "1"
    assert seen["safe_mode"] is True


def test_safe_mode_persisted_for_restart(monkeypatch, tmp_path):
    from praisonai_bot.cli.features import gateway as feat

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    feat._persist_start_flags("127.0.0.1", 8765, {"safe_mode": True})
    assert feat.load_start_flags("127.0.0.1", 8765) == {"safe_mode": True}
