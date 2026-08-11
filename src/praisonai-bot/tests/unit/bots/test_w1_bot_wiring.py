"""W1 — Bot/BotOS wiring of identity_resolver + SessionContext.

These tests verify the user-facing surface (``Bot(identity_resolver=...)``,
``BotOS(identity_resolver=...)``) wires correctly through to the
underlying ``BotSessionManager``.
"""

from __future__ import annotations

import builtins

import pytest

from praisonai_bot.bots import Bot, BotOS
from praisonai_bot.bots._session import BotSessionManager
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


class TestSharedTurnLock:
    """Issue #3232 — turns serialise on the RESOLVED session id across adapters.

    Two adapters that resolve the same human to one unified session must share
    a single per-turn lock, so concurrent cross-platform turns run serially and
    never interleave the persisted transcript.
    """

    @pytest.mark.asyncio
    async def test_shared_lockmap_yields_same_lock_for_unified_id(self):
        """With a shared LockMap, two managers on different platforms resolving
        to one unified id return the *same* asyncio.Lock object."""
        from praisonai_bot._lockmap import LockMap

        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "tg-1", "alice-global")
        resolver.link("discord", "dc-9", "alice-global")

        shared = LockMap()
        tg = BotSessionManager(
            platform="telegram", identity_resolver=resolver, turn_lock_map=shared
        )
        dc = BotSessionManager(
            platform="discord", identity_resolver=resolver, turn_lock_map=shared
        )
        lock_tg = tg._get_lock("tg-1")
        lock_dc = dc._get_lock("dc-9")
        assert lock_tg is lock_dc

    @pytest.mark.asyncio
    async def test_separate_lockmaps_yield_distinct_locks(self):
        """Without sharing (today's default) the two managers hold distinct
        locks even for the same unified id — the bug this issue describes."""
        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "tg-1", "alice-global")
        resolver.link("discord", "dc-9", "alice-global")

        tg = BotSessionManager(platform="telegram", identity_resolver=resolver)
        dc = BotSessionManager(platform="discord", identity_resolver=resolver)
        assert tg._get_lock("tg-1") is not dc._get_lock("dc-9")


class TestBotOSTurnLockWiring:
    """Issue #3232 — BotOS shares one turn LockMap across managed bots."""

    def _fake_bot(self, platform, resolver=None):
        class _FakeSession:
            def __init__(self):
                from praisonai_bot._lockmap import LockMap

                self._locks = LockMap()

        class _FakeBot:
            def __init__(self):
                self.platform = platform
                self._identity_resolver = resolver
                self._turn_lock_map = None
                self._session = _FakeSession()

        return _FakeBot()

    def test_wire_shares_single_map_when_resolver_present(self):
        resolver = InMemoryIdentityResolver()
        os = BotOS(identity_resolver=resolver)
        bot_a = self._fake_bot("telegram")
        bot_b = self._fake_bot("discord")
        os._bots = {"telegram": bot_a, "discord": bot_b}

        os._wire_turn_locks()

        assert bot_a._turn_lock_map is os._turn_lock_map
        assert bot_b._turn_lock_map is os._turn_lock_map
        # Already-built sessions are wired in place too.
        assert bot_a._session._locks is os._turn_lock_map
        assert bot_b._session._locks is os._turn_lock_map

    def test_wire_is_noop_without_resolver(self):
        os = BotOS()
        bot = self._fake_bot("telegram")
        os._bots = {"telegram": bot}

        os._wire_turn_locks()

        assert bot._turn_lock_map is None
        assert bot._session._locks is not os._turn_lock_map

    def test_wire_detects_per_bot_resolver(self):
        """A resolver set on a bot (not BotOS-level) still triggers sharing."""
        resolver = InMemoryIdentityResolver()
        os = BotOS()
        bot = self._fake_bot("telegram", resolver=resolver)
        os._bots = {"telegram": bot}

        os._wire_turn_locks()

        assert bot._turn_lock_map is os._turn_lock_map


class _SpliceSession:
    """A BotSessionManager-shaped session exposing only the private seam attrs.

    Deliberately does NOT implement ``attach_gateway_runtime`` so it models a
    session from a ``praisonaiagents`` release predating the typed contract.
    """

    def __init__(self):
        self._identity_resolver = None
        self._delivery_router = None
        self._admission_gate = None
        self._locks = object()


class _SpliceAdapter:
    def __init__(self):
        self._session = _SpliceSession()


class TestGatewayRuntimeCompatFallback:
    """The typed contract lives in core; the wrapper allows a version range.

    On a core release predating ``GatewayRuntimeSeams`` the import fails, so
    ``_attach_gateway_runtime`` must fall back to the legacy duck-typed splices
    rather than raising ``ImportError`` on every ``start()``/``probe()``/
    ``health()`` (Greptile P1).
    """

    def test_no_seams_is_noop_without_touching_core(self, monkeypatch):
        """With nothing to inject the method returns before any core import."""
        real_import = builtins.__import__

        def _boom(name, *args, **kwargs):
            if name == "praisonaiagents.bots":
                raise AssertionError("must not import core when there are no seams")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _boom)

        bot = Bot("telegram")
        adapter = _SpliceAdapter()
        bot._attach_gateway_runtime(adapter)  # no seams set -> pure no-op

    def test_falls_back_to_legacy_splices_when_contract_missing(self, monkeypatch):
        """An ImportError on the core contract wires seams the legacy way."""
        real_import = builtins.__import__

        def _no_contract(name, *args, **kwargs):
            if name == "praisonaiagents.bots":
                raise ImportError("older core without gateway contract")
            return real_import(name, *args, **kwargs)

        resolver = InMemoryIdentityResolver()
        router = object()
        gate = object()
        lockmap = object()

        bot = Bot("telegram", identity_resolver=resolver)
        # The remaining seams are wired post-construction (as BotOS does).
        bot._delivery_router = router
        bot._admission_gate = gate
        bot._turn_lock_map = lockmap
        adapter = _SpliceAdapter()

        monkeypatch.setattr(builtins, "__import__", _no_contract)
        bot._attach_gateway_runtime(adapter)

        assert adapter._session._identity_resolver is resolver
        assert adapter._session._delivery_router is router
        assert adapter._session._admission_gate is gate
        assert adapter._session._locks is lockmap
