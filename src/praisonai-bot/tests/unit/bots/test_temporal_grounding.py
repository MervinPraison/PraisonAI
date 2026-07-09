"""Issue #2834 — Temporal grounding for the always-on gateway agent.

Tests that BotSessionManager can prefix each inbound turn with its real
arrival time so the agent has a clock, applied to both DM (per_user) and
group (per_chat) scopes, de-duplicated on replay, off by default, and
opt-out safe.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from praisonai_bot.bots._session import (
    BotSessionManager,
    strip_leading_timestamps,
)


class FakeAgent:
    def __init__(self):
        self.chat_history = []
        self.calls = []

    def chat(self, prompt):
        self.calls.append((list(self.chat_history), prompt))
        self.chat_history.append({"role": "user", "content": prompt})
        reply = f"reply to {prompt}"
        self.chat_history.append({"role": "assistant", "content": reply})
        return reply


class TestStripLeadingTimestamps:
    def test_strips_single_prefix(self):
        stamped = "[Thu 2026-07-09 14:32 UTC] remind me in 2 hours"
        assert strip_leading_timestamps(stamped) == "remind me in 2 hours"

    def test_strips_accumulated_prefixes(self):
        stamped = "[Thu 2026-07-09 14:32 UTC] [Wed 2026-07-08 09:00 UTC] hi"
        assert strip_leading_timestamps(stamped) == "hi"

    def test_noop_on_unstamped(self):
        assert strip_leading_timestamps("plain text") == "plain text"

    def test_preserves_user_brackets(self):
        # A user's own bracketed text must survive untouched.
        assert strip_leading_timestamps("[TODO] buy milk") == "[TODO] buy milk"

    def test_empty(self):
        assert strip_leading_timestamps("") == ""


class TestTimestampsDisabledByDefault:
    @pytest.mark.asyncio
    async def test_no_prefix_by_default(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram")
        await mgr.chat(agent, "alice", "hello")
        assert agent.calls[0][1] == "hello"


class TestTimestampsInDM:
    @pytest.mark.asyncio
    async def test_dm_turn_stamped(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", timestamps=True)
        received = datetime(2026, 7, 9, 14, 32)
        await mgr.chat(agent, "alice", "remind me in 2 hours", received_at=received)
        forwarded = agent.calls[0][1]
        assert forwarded.startswith("[")
        assert "2026-07-09" in forwarded
        assert forwarded.endswith("remind me in 2 hours")

    @pytest.mark.asyncio
    async def test_falls_back_to_now_without_received_at(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", timestamps=True)
        await mgr.chat(agent, "alice", "what time is it")
        forwarded = agent.calls[0][1]
        assert forwarded.endswith("what time is it")
        assert forwarded != "what time is it"


class TestTimestampsInGroup:
    @pytest.mark.asyncio
    async def test_group_turn_stamped_after_attribution(self):
        agent = FakeAgent()
        mgr = BotSessionManager(
            platform="telegram", session_scope="per_chat", timestamps=True
        )
        received = datetime(2026, 7, 9, 14, 32)
        await mgr.chat(
            agent,
            "alice_id",
            "next friday",
            chat_id="-100123",
            user_name="Alice",
            received_at=received,
        )
        forwarded = agent.calls[0][1]
        # Timestamp outermost, then sender attribution, then content.
        assert forwarded.startswith("[")
        assert "[Alice]" in forwarded
        assert forwarded.endswith("next friday")


class TestNoAccumulationOnReplay:
    @pytest.mark.asyncio
    async def test_prefix_not_duplicated(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", timestamps=True)
        received = datetime(2026, 7, 9, 14, 32)
        # Simulate a message that already carries a stamp (e.g. replayed history).
        already = "[Thu 2026-07-09 14:32 UTC] hello again"
        await mgr.chat(agent, "alice", already, received_at=received)
        forwarded = agent.calls[0][1]
        # Exactly one bracketed timestamp prefix, not two.
        assert forwarded.count("2026-07-09") == 1
        assert forwarded.endswith("hello again")
