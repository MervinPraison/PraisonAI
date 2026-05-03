"""W1 — Unified per-user session across platforms.

Tests that BotSessionManager can use an IdentityResolver so the same
human pinging from Telegram and Discord shares one chat history.
"""

from __future__ import annotations

import pytest

from praisonai.bots._session import BotSessionManager


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


class TestUnifiedSessionWithoutResolver:
    """Default behaviour preserved: no resolver → per-platform keying."""

    @pytest.mark.asyncio
    async def test_per_platform_isolation_is_default(self):
        agent = FakeAgent()
        mgr_t = BotSessionManager(platform="telegram")
        mgr_d = BotSessionManager(platform="discord")

        await mgr_t.chat(agent, "alice", "hi from telegram")
        await mgr_d.chat(agent, "alice", "hi from discord")

        # Each platform's session is independent
        assert len(mgr_t._histories["alice"]) == 2
        assert len(mgr_d._histories["alice"]) == 2


class TestUnifiedSessionWithResolver:
    """When a resolver is supplied, sessions unify across platforms."""

    @pytest.mark.asyncio
    async def test_unified_key_when_resolver_links_user(self, tmp_path):
        from praisonaiagents.session.identity import InMemoryIdentityResolver
        from praisonaiagents.session.store import DefaultSessionStore

        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "12345", "alice-global")
        resolver.link("discord", "snowflake-1", "alice-global")

        # Cross-platform unification requires a shared persistent store.
        store = DefaultSessionStore(session_dir=str(tmp_path))

        agent = FakeAgent()
        mgr_t = BotSessionManager(
            platform="telegram", identity_resolver=resolver, store=store
        )
        mgr_d = BotSessionManager(
            platform="discord", identity_resolver=resolver, store=store
        )

        await mgr_t.chat(agent, "12345", "hi from telegram")
        # Second call from Discord should see the Telegram turn in history
        await mgr_d.chat(agent, "snowflake-1", "what did I say?")

        history_passed_to_second_call = agent.calls[1][0]
        assert any(
            "hi from telegram" in str(m.get("content", ""))
            for m in history_passed_to_second_call
        )

    @pytest.mark.asyncio
    async def test_unlinked_user_falls_back_to_platform_id(self):
        from praisonaiagents.session.identity import InMemoryIdentityResolver

        resolver = InMemoryIdentityResolver()  # no links
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", identity_resolver=resolver)

        await mgr.chat(agent, "12345", "hello")
        # Falls back to platform-prefixed key
        assert "telegram:12345" in mgr._histories or "12345" in mgr._histories


class TestSessionKeyDerivation:
    def test_resolver_changes_session_key(self):
        from praisonaiagents.session.identity import InMemoryIdentityResolver

        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "12345", "alice-global")

        mgr = BotSessionManager(platform="telegram", identity_resolver=resolver)
        key = mgr._session_key("12345")
        assert "alice-global" in key
        assert "telegram" not in key  # unified, not platform-prefixed
