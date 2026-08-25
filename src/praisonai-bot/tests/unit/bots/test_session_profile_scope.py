"""Issue #4341 — Per-tenant profile scope namespaces memory/session state.

A route (or channel) can name a ``profile``; the gateway stages it on the
session via ``set_profile_namespace`` so every ``_storage_key`` for the turn is
prefixed with the tenant scope. Two routes multiplexed on one process must never
share a transcript, and a route with no profile must stay unscoped (fail-closed)
rather than borrow another tenant's namespace.
"""

from __future__ import annotations

import asyncio
import threading

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


class GatedAgent:
    """Agent whose sync ``chat`` blocks on a threading gate.

    ``chat`` runs on an executor thread, so a ``threading.Event`` lets a test
    hold one tenant's turn suspended while a second route stages a different
    profile — proving one turn never persists into the other's namespace.
    """

    def __init__(self, gate: "threading.Event"):
        self.chat_history = []
        self._gate = gate

    def chat(self, prompt):
        # Block (on the executor thread) until released so a second turn can
        # stage its own profile while this turn is in-flight.
        self._gate.wait(timeout=5)
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": f"re:{prompt}"})
        return f"re:{prompt}"


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

    @pytest.mark.asyncio
    async def test_overlapping_turns_do_not_cross_namespaces(self):
        """Two concurrent routed turns must keep their own tenant namespace.

        Regression for the shared-mutable-state race (CodeRabbit/Greptile):
        turn A stages ``acme`` and suspends inside ``chat()``; turn B then
        stages ``globex``. The pre-fix code recomputed the storage key from a
        shared field, so A's save could land in ``globex``. With turn-local
        (ContextVar) scoping, A persists to ``acme`` and B to ``globex``.
        """
        gate_a = threading.Event()
        gate_b = threading.Event()
        agent_a = GatedAgent(gate_a)
        agent_b = GatedAgent(gate_b)
        mgr = BotSessionManager(platform="discord")

        async def run(agent, profile):
            # Passing ``agent`` stages the namespace per-agent, so ``chat()``
            # re-binds it turn-locally regardless of the parent context.
            mgr.set_profile_namespace(profile, agent)
            return await mgr.chat(agent, "u1", f"{profile} msg")

        # Start both turns; each blocks on its gate inside chat() (on an
        # executor thread), so they are genuinely overlapped and in-flight.
        task_a = asyncio.create_task(run(agent_a, "acme"))
        await asyncio.sleep(0.05)  # let A stage + enter chat() and block
        task_b = asyncio.create_task(run(agent_b, "globex"))
        await asyncio.sleep(0.05)  # let B stage + enter chat() and block

        # Release B first, then A — the interleaving that would corrupt keys
        # under a shared field (A's save would follow B's "globex").
        gate_b.set()
        gate_a.set()
        await asyncio.gather(task_a, task_b)

        keys = set(mgr._histories)
        assert "profile:acme:u1" in keys
        assert "profile:globex:u1" in keys
        # Neither turn leaked into the other tenant's namespace, and no unscoped
        # key was ever written.
        assert "u1" not in keys
