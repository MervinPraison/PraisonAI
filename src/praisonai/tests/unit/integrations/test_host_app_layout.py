"""configure_host() opens the React app shell; the bundled UIs ask for Chat + Canvas."""
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


def test_default_is_app_shell_and_leaves_layout_to_aiui(fake_aiui):
    # aiui picks the layout (create_app: chat-canvas, ``aiui run``: chat); not
    # calling set_layout keeps the YAML ``layout:`` key in effect.
    assert _run(fake_aiui) == {"style": "app"}


def test_other_layout(fake_aiui):
    assert _run(fake_aiui, layout="workbench") == {"style": "app", "layout": "workbench"}


def test_dashboard_style_sets_no_layout(fake_aiui):
    assert _run(fake_aiui, style="dashboard") == {"style": "dashboard"}


def _build(fake_aiui, **preset_kwargs):
    """build_ui_app(UIPreset(...)) -> the layout it hands to configure_host."""
    import sys
    from praisonai.integration import host_app

    aiui = sys.modules["praisonaiui"]
    aiui.welcome = lambda fn: fn
    aiui.starters = lambda fn: fn
    seen = {}
    with patch.object(host_app, "configure_host", lambda **kw: seen.update(kw)), \
            patch.object(host_app, "create_host_app", lambda: "app"):
        assert host_app.build_ui_app(host_app.UIPreset(**preset_kwargs)) == "app"
    return seen["layout"]


def test_bundled_uis_ask_for_chat_canvas(fake_aiui):
    # `aiui run` (aiui >= 0.3.169) opens the plain Chat layout unless the app
    # picks one; the bundled UIs (praisonai ui / ui agents / ui bot / ...)
    # keep Chat + Canvas.
    assert _build(fake_aiui) == "chat-canvas"


def test_preset_layout_none_leaves_it_to_aiui(fake_aiui):
    assert _build(fake_aiui, layout=None) is None
    assert _build(fake_aiui, layout="workbench") == "workbench"
