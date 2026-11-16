"""Isolated aiui host state for the PraisonAIUI integration tests."""

from __future__ import annotations

import pytest

pytest.importorskip("praisonaiui")


@pytest.fixture
def isolated_host(monkeypatch, tmp_path):
    """Fresh aiui server state, callback-only host (no LLM provider), tmp dirs."""
    import praisonaiui.server as srv

    from praisonai_bot.integration import host_app

    monkeypatch.setenv("PRAISONAI_HOST_LEGACY", "1")
    monkeypatch.setenv("AIUI_DATA_DIR", str(tmp_path / "aiui"))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praisonai"))
    monkeypatch.setenv("AIUI_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.delenv("AIUI_SHELL", raising=False)
    monkeypatch.delenv("AUTH_ENFORCE", raising=False)
    srv.reset_state()
    host_app.reset_configuration()
    yield host_app
    host_app.reset_configuration()
    srv.reset_state()
