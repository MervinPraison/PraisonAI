"""Issue #3296 — Gateway surfaces *why* a turn ended (opt-in).

Verifies BotSessionManager appends a concise, user-safe completion note to
the reply when a turn stops early (max_steps / cancelled / error) *and*
``surface_completion_reason=True``. Off by default so clean completions and
existing deployments are byte-for-byte unchanged.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots._session import BotSessionManager


class _StoppedAgent:
    """FakeAgent whose last turn stopped early with ``reason``."""

    def __init__(self, reason: str, reply: str = "partial answer"):
        self.chat_history = []
        self._reason = reason
        self._reply = reply

    @property
    def last_stop_reason(self) -> str:
        return self._reason

    def chat(self, prompt):
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": self._reply})
        return self._reply


class TestCompletionNoteDisabledByDefault:
    @pytest.mark.asyncio
    async def test_no_note_when_flag_off(self):
        agent = _StoppedAgent("max_steps")
        mgr = BotSessionManager(platform="telegram")  # default: off

        out = await mgr.chat(agent, "u1", "do a big task")

        assert out == "partial answer"

    @pytest.mark.asyncio
    async def test_completed_never_annotated(self):
        agent = _StoppedAgent("completed")
        mgr = BotSessionManager(
            platform="telegram", surface_completion_reason=True
        )

        out = await mgr.chat(agent, "u1", "hi")

        assert out == "partial answer"


class TestCompletionNoteEnabled:
    @pytest.mark.asyncio
    async def test_max_steps_note_appended(self):
        agent = _StoppedAgent("max_steps")
        mgr = BotSessionManager(
            platform="telegram", surface_completion_reason=True
        )

        out = await mgr.chat(agent, "u1", "do a big task")

        assert out.startswith("partial answer")
        assert "step limit" in out

    @pytest.mark.asyncio
    async def test_error_note_appended(self):
        agent = _StoppedAgent("error")
        mgr = BotSessionManager(
            platform="telegram", surface_completion_reason=True
        )

        out = await mgr.chat(agent, "u1", "do a task")

        assert out.startswith("partial answer")
        assert "error" in out.lower()

    @pytest.mark.asyncio
    async def test_note_stands_alone_when_reply_empty(self):
        agent = _StoppedAgent("max_steps", reply="")
        mgr = BotSessionManager(
            platform="telegram", surface_completion_reason=True
        )

        out = await mgr.chat(agent, "u1", "do a big task")

        assert "step limit" in out
