"""Tests for CLI session continuity wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from praisonai.cli.utils.project import build_cli_memory_config, apply_cli_session_continuity


def test_build_cli_memory_config_enables_history():
    cfg = build_cli_memory_config(session_id="sess-1", auto_save="sess-1")
    assert cfg is not None
    assert cfg.history is True
    assert cfg.session_id == "sess-1"
    assert cfg.auto_save == "sess-1"


@pytest.mark.no_session_isolation
def test_apply_cli_session_continuity_uses_project_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    agent = MagicMock()
    agent.chat_history = []

    apply_cli_session_continuity(agent, "cli-session-abc")

    assert agent._session_id == "cli-session-abc"
    assert agent._history_enabled is True
    assert agent._session_store_initialized is True
    assert "projects/" in agent._session_store.session_dir
