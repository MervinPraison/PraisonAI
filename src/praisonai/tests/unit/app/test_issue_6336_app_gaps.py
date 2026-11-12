"""Regression tests for #6336: AgentOS auth fail-closed, YAML config, log rotation."""
import os
from unittest.mock import patch

import pytest


def test_serve_refuses_public_bind_without_api_key(monkeypatch):
    pytest.importorskip("uvicorn")
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


def test_default_host_is_loopback():
    from praisonaiagents import AgentOSConfig
    assert AgentOSConfig().host == "127.0.0.1"


def test_cli_yaml_feeds_server_config_and_agent_fields(tmp_path):
    from click.testing import CliRunner
    from praisonai.cli.commands.app import app_command

    cfg = tmp_path / "app.yaml"
    cfg.write_text(
        "host: 0.0.0.0\napi_key: s3cret\ncors_origins: ['https://my.app']\n"
        "agents:\n  - name: assistant\n    goal: Be helpful\n    llm: gpt-4o-mini\n"
        "    backstory: expert\n"
    )
    captured = {}

    def fake_init(self, name=None, agents=None, config=None, **kw):
        captured.update(config=config, agents=agents)

    with patch("praisonai.app.agentos.AgentOS.__init__", fake_init), \
         patch("praisonai.app.agentos.AgentOS.serve", lambda self: None):
        result = CliRunner().invoke(app_command, ["--config", str(cfg), "--port", "9001"])
    assert result.exit_code == 0, result.output
    config = captured["config"]
    assert config.api_key == "s3cret"
    assert config.cors_origins == ["https://my.app"]
    assert config.host == "0.0.0.0"  # YAML beats CLI default
    assert config.port == 9001  # explicit CLI flag beats YAML/default
    agent = captured["agents"][0]
    assert agent.instructions == "Be helpful"
    assert agent.backstory == "expert"


def test_rotate_log_truncates_in_place_for_open_fd(tmp_path):
    from praisonai.scheduler.daemon_manager import DaemonManager

    mgr = DaemonManager(log_dir=tmp_path, max_log_size_mb=0.0001)
    log_file = tmp_path / "d.log"
    with open(log_file, "a") as fh:  # simulates the daemon's inherited fd
        fh.write("x" * 500)
        fh.flush()
        assert mgr.rotate_log("d") is True
        fh.write("after")
        fh.flush()
    assert log_file.read_text() == "after"
    rotated = [p for p in tmp_path.iterdir() if p.name.startswith("d.log.")]
    assert len(rotated) == 1 and rotated[0].stat().st_size == 500
