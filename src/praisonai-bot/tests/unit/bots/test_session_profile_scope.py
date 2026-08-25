"""Issue #4341 — Per-tenant profile scope namespaces memory/session state.

A route (or channel) can name a ``profile``; the gateway stages it on the
session via ``set_profile_namespace`` so every ``_storage_key`` for the turn is
prefixed with the tenant scope. Two routes multiplexed on one process must never
share a transcript, and a route with no profile must stay unscoped (fail-closed)
rather than borrow another tenant's namespace.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots._session import BotSessionManager


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


class TestProfileStorageKey:
    def test_unscoped_by_default(self):
        mgr = BotSessionManager(platform="discord")
        assert mgr._storage_key("u1") == "u1"

    def test_profile_prefixes_storage_key(self):
        mgr = BotSessionManager(platform="discord")
        mgr.set_profile_namespace("acme")
        assert mgr._storage_key("u1") == "profile:acme:u1"

    def test_distinct_profiles_isolate_same_user(self):
        mgr = BotSessionManager(platform="discord")
        mgr.set_profile_namespace("acme")
        acme_key = mgr._storage_key("u1")
        mgr.set_profile_namespace("globex")
        globex_key = mgr._storage_key("u1")
        assert acme_key != globex_key
        assert acme_key == "profile:acme:u1"
        assert globex_key == "profile:globex:u1"

    def test_clear_fails_closed_to_unscoped(self):
        mgr = BotSessionManager(platform="discord")
        mgr.set_profile_namespace("acme")
        mgr.set_profile_namespace(None)
        assert mgr._storage_key("u1") == "u1"

    def test_blank_profile_is_unscoped(self):
        mgr = BotSessionManager(platform="discord")
        mgr.set_profile_namespace("   ")
        assert mgr._storage_key("u1") == "u1"

    def test_profile_applies_to_per_chat_scope(self):
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")
        mgr.set_profile_namespace("acme")
        key = mgr._storage_key("alice", chat_id="-100123", chat_type="group")
        assert key.startswith("profile:acme:")
        assert ":chat:-100123:" in key


class TestProfileMemoryIsolation:
    @pytest.mark.asyncio
    async def test_two_tenants_do_not_share_history(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="discord")

        mgr.set_profile_namespace("acme")
        await mgr.chat(agent, "u1", "acme secret")

        mgr.set_profile_namespace("globex")
        await mgr.chat(agent, "u1", "globex secret")

        keys = list(mgr._histories)
        assert "profile:acme:u1" in keys
        assert "profile:globex:u1" in keys
        # Same raw user id, but the two tenants never collapse into one key.
        assert "u1" not in keys
