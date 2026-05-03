"""W1 — Bot/BotOS wiring of identity_resolver + SessionContext.

These tests verify the user-facing surface (``Bot(identity_resolver=...)``,
``BotOS(identity_resolver=...)``) wires correctly through to the
underlying ``BotSessionManager``.
"""

from __future__ import annotations

import pytest

from praisonai.bots import Bot, BotOS
from praisonai.bots._session import BotSessionManager
from praisonaiagents.session import (
    InMemoryIdentityResolver,
    SessionContext,
    get_session_context,
    set_session_context,
    clear_session_context,
)


class TestBotConstructorAcceptsResolver:
    def test_bot_accepts_identity_resolver_kwarg(self):
        resolver = InMemoryIdentityResolver()
        bot = Bot("telegram", identity_resolver=resolver)
        assert bot._identity_resolver is resolver


class TestBotOSPropagation:
    def test_botos_sets_resolver_on_added_bots_via_shortcut(self):
        from unittest.mock import MagicMock

        agent = MagicMock(name="agent")
        agent.name = "Test"
        agent.chat_history = []

        resolver = InMemoryIdentityResolver()
        os = BotOS(
            agent=agent,
            platforms=["telegram", "discord"],
            identity_resolver=resolver,
        )
        for plat in ("telegram", "discord"):
            bot = os.get_bot(plat)
            assert bot is not None
            assert bot._identity_resolver is resolver

    def test_botos_propagates_to_manually_added_bot(self):
        resolver = InMemoryIdentityResolver()
        os = BotOS(identity_resolver=resolver)
        bot = Bot("telegram")
        assert bot._identity_resolver is None
        os.add_bot(bot)
        assert bot._identity_resolver is resolver

    def test_botos_does_not_overwrite_explicit_resolver(self):
        r1 = InMemoryIdentityResolver()
        r2 = InMemoryIdentityResolver()
        bot = Bot("telegram", identity_resolver=r1)
        os = BotOS(identity_resolver=r2)
        os.add_bot(bot)
        assert bot._identity_resolver is r1  # explicit wins


class FakeAgent:
    def __init__(self):
        self.chat_history = []
        self.observed_context = None

    def chat(self, prompt):
        # Capture context as seen from inside the "agent call"
        self.observed_context = get_session_context()
        self.chat_history.append({"role": "user", "content": prompt})
        return "ok"


class TestSessionContextPropagation:
    @pytest.mark.asyncio
    async def test_chat_sets_session_context_for_agent(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram")
        await mgr.chat(
            agent, user_id="12345", prompt="hi",
            chat_id="100", user_name="Alice",
        )
        ctx = agent.observed_context
        assert isinstance(ctx, SessionContext)
        assert ctx.platform == "telegram"
        assert ctx.chat_id == "100"
        assert ctx.user_id == "12345"
        assert ctx.user_name == "Alice"

    @pytest.mark.asyncio
    async def test_context_is_cleared_after_chat(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram")
        await mgr.chat(agent, user_id="12345", prompt="hi", chat_id="100")
        # After chat returns, caller's context is restored to default.
        assert get_session_context().platform == ""

    @pytest.mark.asyncio
    async def test_unified_user_id_in_context(self):
        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "12345", "alice-global")

        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", identity_resolver=resolver)
        await mgr.chat(agent, user_id="12345", prompt="hi")
        ctx = agent.observed_context
        assert ctx.unified_user_id == "alice-global"
