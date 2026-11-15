"""configure_host() opens the React app shell in Chat + Canvas by default."""
from unittest.mock import patch

from .test_host_app_context import _reset, fake_aiui  # noqa: F401  (fixture)


def _run(fake_aiui, **kwargs):
    import sys
    from praisonai.integration import host_app

    aiui = sys.modules["praisonaiui"]
    calls = {}
    aiui.set_style = lambda s: calls.__setitem__("style", s)
    aiui.set_layout = lambda name: calls.__setitem__("layout", name)
    _reset(host_app)
    with patch("praisonai.integration.context_files.load_context_files", return_value=""):
        host_app.configure_host(**kwargs)
    return calls


def test_default_is_app_shell_with_chat_canvas(fake_aiui):
    assert _run(fake_aiui) == {"style": "app", "layout": "chat-canvas"}


def test_other_layout(fake_aiui):
    assert _run(fake_aiui, layout="workbench") == {"style": "app", "layout": "workbench"}


def test_dashboard_style_sets_no_layout(fake_aiui):
    assert _run(fake_aiui, style="dashboard") == {"style": "dashboard"}
