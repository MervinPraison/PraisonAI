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


class TestConcurrentUsersOnSharedAgent:
    """Regression: agent_lock must hold across the full LLM call, not
    only the history swap. Otherwise concurrent users on a shared
    Agent instance see each other's chat_history.
    """

    @pytest.mark.asyncio
    async def test_no_history_leak_between_concurrent_users(self):
        import asyncio

        class SlowFakeAgent:
            def __init__(self):
                self.chat_history = []

            def chat(self, prompt):
                # Capture what history was visible at call time
                seen_history = list(self.chat_history)
                # Append response
                self.chat_history.append(
                    {"role": "user", "content": prompt}
                )
                self.chat_history.append(
                    {"role": "assistant", "content": f"reply: saw {len(seen_history)} prior msgs"}
                )
                # Yield control so a concurrent task can interfere
                # if locking is wrong
                import time
                time.sleep(0.05)
                return f"saw_{len(seen_history)}"

        agent = SlowFakeAgent()
        mgr = BotSessionManager(platform="telegram")

        # Pre-seed alice's history with 4 messages
        for i in range(2):
            await mgr.chat(agent, "alice", f"msg {i}")
        # Bob has no history yet.
        # Now concurrent: alice should see her 4 msgs, bob should see 0.
        results = await asyncio.gather(
            mgr.chat(agent, "alice", "alice question"),
            mgr.chat(agent, "bob", "bob question"),
        )
        # Alice has 2 prior turns × 2 (user+assistant) = 4 msgs visible.
        # Bob has 0 prior msgs.
        # Note ordering by user_lock means each user's previous turn is
        # reflected. Key invariant: bob never sees alice's content and
        # vice versa.
        history_alice = mgr._histories.get("alice", [])
        history_bob = mgr._histories.get("bob", [])
        assert any("alice question" in str(m.get("content", "")) for m in history_alice)
        assert any("bob question" in str(m.get("content", "")) for m in history_bob)
        # Cross-leak check: bob's history must NOT contain alice's content.
        for m in history_bob:
            assert "alice" not in str(m.get("content", "")).lower()
        for m in history_alice:
            assert "bob" not in str(m.get("content", "")).lower()


class TestSessionKeyDerivation:
    def test_resolver_changes_session_key(self):
        from praisonaiagents.session.identity import InMemoryIdentityResolver

        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "12345", "alice-global")

        mgr = BotSessionManager(platform="telegram", identity_resolver=resolver)
        key = mgr._session_key("12345")
        assert "alice-global" in key
        assert "telegram" not in key  # unified, not platform-prefixed
