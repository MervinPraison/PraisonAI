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


def test_realtime_ui_turns_on_the_composer_microphone():
    """aiui >= 0.3.172 ships the manager in praisonaiui.features.realtime.

    The app imported ``praisonaiui.realtime``, which never existed, so the
    ImportError left realtime_manager as None and the microphone stayed off.
    """
    src = (Path(praisonai.__file__).parent / "ui_realtime" / "default_app.py").read_text(encoding="utf-8")
    assert "from praisonaiui.features.realtime import OpenAIRealtimeManager" in src
    assert "from praisonaiui.realtime import" not in src


def test_claw_lists_the_connect_page():
    from praisonai_bot.integration.host_app import DASHBOARD_PAGES

    src = (Path(praisonai_bot.__file__).parent / "claw" / "default_app.py").read_text(encoding="utf-8")
    assert "pages=DASHBOARD_PAGES" in src
    assert "connect" in DASHBOARD_PAGES


def test_ui_chat_shows_the_dashboard_pages():
    """`praisonai ui` and `praisonai dashboard` show the same sidebar pages."""
    tree = ast.parse((WRAPPER / "ui_chat" / "default_app.py").read_text(encoding="utf-8"))
    preset = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "UIPreset")
    kwargs = {kw.arg: ast.unparse(kw.value) for kw in preset.keywords}
    assert kwargs["pages"] == "DASHBOARD_PAGES"
    assert "sidebar" not in kwargs and "page_header" not in kwargs  # UIPreset defaults: shown
