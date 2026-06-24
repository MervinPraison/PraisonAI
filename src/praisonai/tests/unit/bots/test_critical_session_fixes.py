"""Tests for critical bot session correctness fixes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_control_wires_interrupt_controller_on_agent():
    """Run control must attach to agent.interrupt_controller, not _interrupt_controller."""
    from praisonai.bots._run_control import SessionRunControl
    from praisonai.bots._session import BotSessionManager
    from praisonaiagents.agent.interrupt import InterruptController

    run_control = SessionRunControl(busy_mode="queue")
    session_mgr = BotSessionManager(run_control=run_control)

    agent = MagicMock()
    agent.interrupt_controller = None
    seen: list = []

    async def fake_chat(*args, **kwargs):
        seen.append(agent.interrupt_controller)
        return "done"

    with patch.object(session_mgr, "chat", new=AsyncMock(side_effect=fake_chat)):
        await session_mgr.chat_with_run_control(agent, "user1", "hello")

    assert len(seen) == 1
    assert isinstance(seen[0], InterruptController)


@pytest.mark.asyncio
async def test_run_control_drains_queued_pending_messages():
    """Queued mid-run messages must be processed, not discarded."""
    from praisonai.bots._run_control import SessionRunControl, RunDecision
    from praisonai.bots._session import BotSessionManager

    run_control = SessionRunControl(busy_mode="queue")
    session_mgr = BotSessionManager(run_control=run_control)

    prompts_seen: list[str] = []

    async def fake_chat(agent, user_id, prompt, *args, **kwargs):
        prompts_seen.append(prompt)
        if len(prompts_seen) == 1:
            await run_control.submit(user_id, "follow-up while busy")
        return f"response:{prompt}"

    agent = MagicMock()
    agent.interrupt_controller = None

    with patch.object(session_mgr, "chat", new=AsyncMock(side_effect=fake_chat)):
        result = await session_mgr.chat_with_run_control(agent, "user1", "first")

    assert prompts_seen == ["first", "follow-up while busy"]
    assert result["response"] == "response:follow-up while busy"
    assert result["metadata"].get("pending_processed")


@pytest.mark.asyncio
async def test_ingress_journal_completed_after_successful_chat(tmp_path):
    from praisonai.bots._ingress import InboundJournal
    from praisonai.bots._session import BotSessionManager

    journal = InboundJournal(path=tmp_path / "ingress.sqlite")
    session_mgr = BotSessionManager(platform="telegram", ingress_journal=journal)

    agent = MagicMock()
    agent.chat_history = []
    agent.chat = MagicMock(return_value="ok")

    async def fake_executor(*args, **kwargs):
        return []

    with patch.object(session_mgr, "_load_history", return_value=[]):
        with patch.object(session_mgr, "_save_history"):
            with patch("asyncio.get_running_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock(side_effect=fake_executor)
                mock_loop.return_value = loop

                with patch.object(agent, "chat", return_value="ok"):
                    await session_mgr.chat(
                        agent,
                        "user1",
                        "hello",
                        message_id="msg-1",
                        chat_id="chat-1",
                    )

    assert journal.pending_count() == 0
    assert journal.size() == 1


@pytest.mark.asyncio
async def test_steer_mode_injects_into_live_agent():
    """STEER mode must route mid-run messages into the agent's steering queue."""
    from praisonai.bots._run_control import SessionRunControl, RunDecision

    run_control = SessionRunControl(busy_mode="steer")

    agent = MagicMock()
    agent.message_steering_enabled = True
    agent.steer = MagicMock(return_value="steer_123")

    # First message starts the run.
    first = await run_control.submit("user1", "do the research")
    assert first == RunDecision.RUN_NOW

    # Gateway registers the live agent.
    run_control.register_agent("user1", agent)

    # Second mid-run message gets steered, not queued.
    second = await run_control.submit("user1", "focus on the API section")
    assert second == RunDecision.STEERED
    agent.steer.assert_called_once_with("focus on the API section", priority=30)

    # No pending message should have been queued.
    assert run_control.next_pending("user1") is None


@pytest.mark.asyncio
async def test_steer_mode_falls_back_to_queue_without_agent():
    """STEER mode must safely fall back to queue when no steering agent is set."""
    from praisonai.bots._run_control import SessionRunControl, RunDecision

    run_control = SessionRunControl(busy_mode="steer")

    first = await run_control.submit("user1", "first task")
    assert first == RunDecision.RUN_NOW

    # No agent registered -> mid-run message is queued, not lost.
    second = await run_control.submit("user1", "second task")
    assert second == RunDecision.QUEUED
    assert run_control.next_pending("user1") == "second task"


@pytest.mark.asyncio
async def test_steer_mode_falls_back_when_steering_disabled():
    """STEER mode must fall back to queue if the agent has steering disabled."""
    from praisonai.bots._run_control import SessionRunControl, RunDecision

    run_control = SessionRunControl(busy_mode="steer")

    agent = MagicMock()
    agent.message_steering_enabled = False
    agent.steer = MagicMock(return_value="")

    await run_control.submit("user1", "first task")
    run_control.register_agent("user1", agent)

    second = await run_control.submit("user1", "second task")
    assert second == RunDecision.QUEUED
    agent.steer.assert_not_called()


@pytest.mark.asyncio
async def test_session_registers_agent_and_returns_steered():
    """chat_with_run_control must register the agent and surface STEERED acks."""
    from praisonai.bots._run_control import SessionRunControl, RunDecision
    from praisonai.bots._session import BotSessionManager

    run_control = SessionRunControl(busy_mode="steer")
    session_mgr = BotSessionManager(run_control=run_control)

    agent = MagicMock()
    agent.interrupt_controller = None
    agent.message_steering_enabled = True
    agent.steer = MagicMock(return_value="steer_1")

    async def fake_chat(agent_, user_id, prompt, *args, **kwargs):
        # While running, a second message arrives mid-run and is steered.
        decision = await run_control.submit(user_id, "focus on X")
        assert decision == RunDecision.STEERED
        return f"response:{prompt}"

    with patch.object(session_mgr, "chat", new=AsyncMock(side_effect=fake_chat)):
        result = await session_mgr.chat_with_run_control(agent, "user1", "first")

    agent.steer.assert_called_once_with("focus on X", priority=30)
    assert result["response"] == "response:first"
