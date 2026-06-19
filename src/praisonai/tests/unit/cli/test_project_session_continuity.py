"""Tests for praison run project-scoped session continuity."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_build_cli_memory_config_enables_history():
    from praisonai.cli.state.project_sessions import build_cli_memory_config

    cfg = build_cli_memory_config("sess-1", "sess-1")
    assert cfg is not None
    assert cfg.session_id == "sess-1"
    assert cfg.auto_save == "sess-1"
    assert cfg.history is True


def test_apply_cli_session_continuity_restores_history(tmp_path, monkeypatch):
    from praisonai.cli.state.project_sessions import (
        apply_cli_session_continuity,
        get_project_session_store,
    )
    from praisonai.cli.utils.project import get_project_sessions_dir

    monkeypatch.chdir(tmp_path)
    store = get_project_session_store()
    store.add_user_message("sess-abc", "hello")
    store.add_assistant_message("sess-abc", "hi there")

    agent = MagicMock()
    agent.chat_history = []
    agent.auto_save = None
    agent._session_store = None
    agent._session_id = None
    agent._history_enabled = False
    agent._history_session_id = None
    agent._session_store_initialized = False
    agent._auto_save_last_index = 0

    apply_cli_session_continuity(agent, "sess-abc")

    assert agent._session_id == "sess-abc"
    assert agent._history_enabled is True
    assert len(agent.chat_history) == 2
    assert agent._auto_save_last_index == 2
    assert agent._session_store.get_chat_history("sess-abc")[0]["content"] == "hello"


def test_chat_with_run_control_attaches_interrupt_controller():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from praisonai.bots._run_control import RunDecision, SessionRunControl
    from praisonai.bots._session import BotSessionManager

    agent = MagicMock()
    agent.chat_history = []
    agent.interrupt_controller = None
    seen = {}

    async def _capture_chat(*args, **kwargs):
        seen["interrupt_controller"] = agent.interrupt_controller
        return "done"

    run_control = SessionRunControl(busy_mode="queue")
    session = BotSessionManager(run_control=run_control)

    async def _run():
        with patch.object(session, "chat", side_effect=_capture_chat):
            with patch.object(
                run_control,
                "submit",
                new_callable=AsyncMock,
                return_value=RunDecision.RUN_NOW,
            ):
                controller = MagicMock(is_set=lambda: False)
                with patch.object(
                    run_control,
                    "get_interrupt_controller",
                    return_value=controller,
                ):
                    with patch.object(
                        run_control,
                        "get_run_status",
                        return_value={"run_generation": 1},
                    ):
                        with patch.object(
                            run_control,
                            "next_pending",
                            return_value=None,
                        ):
                            with patch.object(
                                run_control,
                                "finish_run",
                                new_callable=AsyncMock,
                            ):
                                await session.chat_with_run_control(
                                    agent, "user-1", "hello"
                                )

        assert seen["interrupt_controller"] is controller

    asyncio.run(_run())
