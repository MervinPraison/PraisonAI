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

    class _FakePopen:
        def __init__(self, cmd, **kw):
            calls.append(cmd)

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
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


def test_sigterm_to_the_launcher_stops_the_server(tmp_path):
    """SIGTERM to `praisonai dashboard` must not leave the aiui server running."""
    import os
    import signal
    import time

    pid_file = tmp_path / "server.pid"
    server = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    launcher = subprocess.Popen([
        sys.executable, "-c",
        "import sys; from praisonai_bot.cli.commands.claw import _run_server\n"
        "try:\n"
        f"    _run_server([sys.executable, '-c', {server!r}])\n"
        "except KeyboardInterrupt:\n"
        "    pass\n",
    ])
    try:
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text():
                break
            time.sleep(0.05)
        server_pid = int(pid_file.read_text())
        launcher.send_signal(signal.SIGTERM)
        launcher.wait(timeout=15)
        for _ in range(100):
            try:
                os.kill(server_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            os.kill(server_pid, signal.SIGKILL)
            raise AssertionError("aiui server outlived the launcher")
    finally:
        if launcher.poll() is None:
            launcher.kill()
