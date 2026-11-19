"""Tests for dashboard (unified) CLI command flags and aiui behavior."""

import sys
import inspect
from unittest.mock import MagicMock, patch

from rich.console import Console

from praisonai.cli.commands.dashboard import _run_aiui_dashboard, unified


def test_unified_command_has_new_flags():
    """unified command should expose auto_start and aiui flags."""
    params = inspect.signature(unified).parameters
    assert "auto_start" in params
    assert "aiui" in params


def test_run_aiui_dashboard_returns_false_when_aiui_missing():
    """Should fail gracefully when aiui integration dependencies are missing."""
    console = Console()
    with patch.dict(sys.modules, {"uvicorn": None}):
        assert _run_aiui_dashboard(3000, "127.0.0.1", console) is False


def test_run_aiui_dashboard_returns_false_on_subprocess_failure():
    """Should fail gracefully when in-process host startup fails."""
    console = Console()
    mock_app = MagicMock()
    with patch("uvicorn.run", side_effect=RuntimeError("host failed")):
        with patch("praisonai.integration.host_app.build_host_app", return_value=mock_app):
            assert _run_aiui_dashboard(3000, "127.0.0.1", console) is False


# `praisonai dashboard` is the same app as `praisonai claw`; --unified keeps the older launcher.
def _run(args, monkeypatch):
    from typer.testing import CliRunner

    from praisonai.cli.commands import dashboard as dash

    calls = {"claw": [], "auto_start": []}
    monkeypatch.setattr(
        "praisonai_bot.cli.commands.claw.claw",
        lambda ctx, **kw: calls["claw"].append(kw),
    )
    monkeypatch.setattr(dash, "_auto_start_services", lambda *a, **k: calls["auto_start"].append(a) or True)
    monkeypatch.setattr(dash, "_run_aiui_dashboard", lambda *a, **k: True)
    monkeypatch.setattr(dash.uvicorn if hasattr(dash, "uvicorn") else dash, "run", lambda *a, **k: None, raising=False)
    result = CliRunner().invoke(dash.app, args)
    return result, calls


def test_dashboard_defaults_to_claw(monkeypatch):
    result, calls = _run([], monkeypatch)
    assert result.exit_code == 0, result.output
    assert calls["claw"] == [{"port": 8082, "host": "127.0.0.1", "app_file": None, "reload": False}]
    assert calls["auto_start"] == []


def test_dashboard_passes_claw_flags(monkeypatch):
    result, calls = _run(["--port", "9000", "--app", "my.py", "--reload"], monkeypatch)
    assert result.exit_code == 0, result.output
    assert calls["claw"] == [{"port": 9000, "host": "127.0.0.1", "app_file": "my.py", "reload": True}]


def test_unified_flag_keeps_the_older_launcher(monkeypatch):
    result, calls = _run(["--unified", "--aiui"], monkeypatch)
    assert calls["claw"] == []
    assert len(calls["auto_start"]) == 1


def test_old_flags_still_select_the_unified_launcher(monkeypatch):
    _, calls = _run(["--aiui", "--no-auto-start"], monkeypatch)
    assert calls["claw"] == [] and calls["auto_start"] == []
