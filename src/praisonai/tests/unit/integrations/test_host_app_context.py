"""Tests for project-context loading behaviour in configure_host().

These cover the security-relevant invariants of the host-app context fix:
- an explicit empty ``context_paths=[]`` must NOT trigger walk-up discovery
- ``no_context=True`` (first-class param or via agent_kwargs) disables loading
- discovered context is truncated to ``context_token_budget``
"""
import sys
import types
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_aiui(monkeypatch):
    """Provide minimal praisonaiui + provider stubs so configure_host runs."""
    captured = {}

    aiui = types.ModuleType("praisonaiui")
    aiui.set_datastore = lambda *a, **k: None
    aiui.set_style = lambda *a, **k: None
    aiui.set_branding = lambda *a, **k: None
    aiui.set_pages = lambda *a, **k: None
    aiui.set_dashboard = lambda *a, **k: None
    aiui.set_theme = lambda *a, **k: None

    def _page(*a, **k):
        def _wrap(fn):
            return fn
        return _wrap

    aiui.page = _page

    providers = types.ModuleType("praisonaiui.providers")

    class _Provider:
        def __init__(self, *a, **k):
            captured["kwargs"] = k

    providers.PraisonAIProvider = _Provider

    server = types.ModuleType("praisonaiui.server")
    server._provider = None
    server.set_provider = lambda p: None
    server.create_app = lambda: object()

    datastore_mod = types.ModuleType("praisonai.ui._aiui_datastore")
    datastore_mod.PraisonAISessionDataStore = lambda *a, **k: object()

    monkeypatch.setitem(sys.modules, "praisonaiui", aiui)
    monkeypatch.setitem(sys.modules, "praisonaiui.providers", providers)
    monkeypatch.setitem(sys.modules, "praisonaiui.server", server)
    monkeypatch.setitem(sys.modules, "praisonai.ui._aiui_datastore", datastore_mod)
    # Disable real bridge wiring side-effects in non-legacy provider path.
    monkeypatch.setattr(
        "praisonai.integration.host_app.setup_bridges", lambda: None, raising=True
    )
    return captured


def _reset(host_app):
    host_app.reset_configuration()


def test_empty_context_paths_skips_discovery(fake_aiui):
    """An explicit empty list must not fall back to walk-up discovery."""
    from praisonai.integration import host_app

    _reset(host_app)
    with patch(
        "praisonai.integration.context_files.load_context_files"
    ) as loader:
        loader.return_value = ""
        host_app.configure_host(context_paths=[])

    # Loader must be invoked with the explicit empty list, never walk_up=True.
    assert loader.call_count == 1
    args, kwargs = loader.call_args
    assert args == ([],)
    assert kwargs.get("walk_up") is not True


def test_no_context_param_disables_loading(fake_aiui):
    """First-class no_context=True must prevent any context loading."""
    from praisonai.integration import host_app

    _reset(host_app)
    with patch(
        "praisonai.integration.context_files.load_context_files"
    ) as loader:
        host_app.configure_host(no_context=True)
    loader.assert_not_called()


def test_no_context_via_agent_kwargs(fake_aiui):
    """no_context threaded through agent_kwargs is still honoured."""
    from praisonai.integration import host_app

    _reset(host_app)
    with patch(
        "praisonai.integration.context_files.load_context_files"
    ) as loader:
        host_app.configure_host(agent_kwargs={"no_context": True})
    loader.assert_not_called()


def test_context_truncated_to_budget(fake_aiui):
    """Discovered context is truncated to the configured budget."""
    from praisonai.integration import host_app

    _reset(host_app)
    with patch(
        "praisonai.integration.context_files.load_context_files",
        return_value="x" * 5000,
    ):
        host_app.configure_host(context_token_budget=100)

    instructions = fake_aiui["kwargs"].get("instructions", "")
    assert "[project context truncated]" in instructions
    assert len(instructions) < 5000
