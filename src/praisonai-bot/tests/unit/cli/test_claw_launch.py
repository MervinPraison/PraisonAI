"""`praisonai claw` / `praisonai dashboard` start aiui with the running interpreter."""

import importlib.util
import subprocess
import sys

import pytest
import typer

from praisonai_bot.cli.commands import claw as claw_mod


@pytest.fixture
def launched(monkeypatch, tmp_path):
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: object() if name == "praisonaiui" else real_find_spec(name, *a, **k),
    )
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    app = tmp_path / "app.py"
    app.write_text("")
    ctx = typer.Context(typer.main.get_command(claw_mod.app))
    claw_mod.claw(ctx, port=9001, host="127.0.0.1", app_file=str(app), reload=True)
    return calls, app


def test_runs_aiui_from_the_current_interpreter(launched):
    calls, app = launched
    # A bare "aiui" resolves through PATH, which can be another install
    # (an old global copy or a venv without praisonai_bot).
    assert calls == [[sys.executable, "-m", "praisonaiui.cli", "run", str(app),
                      "--port", "9001", "--host", "127.0.0.1", "--reload"]]


def test_install_hint_names_the_dashboard_extra(monkeypatch, capsys):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    ctx = typer.Context(typer.main.get_command(claw_mod.app))
    with pytest.raises(SystemExit):
        claw_mod.claw(ctx, port=8082, host="127.0.0.1", app_file=None, reload=False)
    assert 'pip install "praisonai[dashboard]"' in capsys.readouterr().out
