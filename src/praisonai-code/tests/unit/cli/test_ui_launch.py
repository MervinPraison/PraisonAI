"""`praisonai ui` starts aiui with the running interpreter, not a bare `aiui` from PATH."""

import importlib.util
import subprocess
import sys

from praisonai_code.cli.commands import ui as ui_mod


def test_ui_runs_aiui_from_the_current_interpreter(monkeypatch, tmp_path):
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

    ui_mod._launch_aiui_app("ui", "default_app.py", 9002, "127.0.0.1", str(app), False, "Chat")

    # PATH can hold another install (an old global copy or another venv).
    assert calls == [[sys.executable, "-m", "praisonaiui.cli", "run", str(app),
                      "--port", "9002", "--host", "127.0.0.1"]]
