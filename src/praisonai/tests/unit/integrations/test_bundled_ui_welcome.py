"""Every bundled UI greets the user in the new-chat hero.

aiui >= 0.3.170 shows the ``@aiui.welcome`` text in every layout, so each app
must set one, and the text must not promise a control the app shell lacks.
"""
import ast
from pathlib import Path

import pytest

import praisonai
import praisonai_bot

WRAPPER = Path(praisonai.__file__).parent
PRESET_APPS = ["ui_chat", "ui_agents", "ui_bot", "ui_realtime", "ui_dashboard", "ui_replay"]


def _preset_welcome(app_dir: str) -> str:
    tree = ast.parse((WRAPPER / app_dir / "default_app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "UIPreset":
            for kw in node.keywords:
                if kw.arg == "welcome":
                    return ast.literal_eval(kw.value)
    raise AssertionError(f"{app_dir}/default_app.py: UIPreset(...) sets no welcome")


@pytest.mark.parametrize("app_dir", PRESET_APPS)
def test_preset_apps_set_a_welcome(app_dir):
    text = _preset_welcome(app_dir)
    assert text.strip()
    # The app shell has no microphone button; the greeting must not send
    # people looking for one.
    assert "microphone button" not in text.lower()


def test_claw_app_registers_a_welcome():
    src = Path(praisonai_bot.__file__).parent / "claw" / "default_app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    decorated = [
        ast.unparse(d)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in node.decorator_list
    ]
    assert "aiui.welcome" in decorated
