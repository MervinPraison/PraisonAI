"""
Tests for Issue #3020: wire a cross-platform identity resolver through the
flagship ``WebSocketGateway`` runtime so a paired/linked user keeps one
continuous session + memory across every channel served by one gateway process.

Before this fix ``WebSocketGateway`` never injected an ``identity_resolver``
into the channel bots it created, so every channel defaulted to a per-platform
session key (``bot_{platform}_{user_id}``) and continuity silently broke.
"""

import pytest
from unittest.mock import patch

from praisonaiagents import Agent
from praisonai_bot.gateway.server import WebSocketGateway


from praisonai_bot._lockmap import LockMap


class _FakeSession:
    def __init__(self):
        self._identity_resolver = None
        # Mirror BotSessionManager: each session owns its own per-turn LockMap
        # unless a shared one is injected (Issue #3232).
        self._locks = LockMap()


class _FakeBot:
    def __init__(self):
        self._session = _FakeSession()
        self._turn_lock_map = None


class _StubResolver:
    def resolve(self, platform, platform_user_id):
        return "user:alice"

    def link(self, *a, **k):
        pass

    def unlink(self, *a, **k):
        pass

    def links_for(self, *a, **k):
        return []


def _gateway_with_agent() -> WebSocketGateway:
    gateway = WebSocketGateway(host="127.0.0.1", port=8901)
    gateway._agents["default"] = Agent(name="test_agent", instructions="Test")
    return gateway


# ── _stamp_identity_resolver ────────────────────────────────────────


def test_stamp_is_noop_without_resolver():
    """No configured resolver leaves the bot session untouched (per-platform)."""
    gateway = _gateway_with_agent()
    bot = _FakeBot()
    gateway._stamp_identity_resolver(bot)
    assert bot._session._identity_resolver is None


def test_stamp_shares_resolver_with_session():
    """A configured resolver is stamped onto the bot's session manager."""
    resolver = _StubResolver()
    gateway = WebSocketGateway(host="127.0.0.1", port=8902, identity_resolver=resolver)
    bot = _FakeBot()
    gateway._stamp_identity_resolver(bot)
    # Wrapped in the owner-aware view (Issue #6362) over the same resolver.
    assert bot._session._identity_resolver._inner is resolver
    assert bot._session._identity_resolver.resolve("telegram", "1") == "user:alice"


# ── owner_user_id unification (Issue #6362) ─────────────────────────


class _OwnerBot:
    def __init__(self, platform, owner):
        from types import SimpleNamespace

        self._session = _FakeSession()
        self._session._platform = platform
        self.config = SimpleNamespace(owner_user_id=owner)


def _resolve(bot, platform, uid):
    return bot._session._identity_resolver.resolve(platform, uid)


def test_owner_handles_unify_across_channels():
    """Each channel's declared owner resolves to one canonical owner id."""
    from praisonaiagents.session.identity import InMemoryIdentityResolver

    resolver = InMemoryIdentityResolver()
    gateway = WebSocketGateway(host="127.0.0.1", port=8903, identity_resolver=resolver)
    tg, sl = _OwnerBot("telegram", "12345"), _OwnerBot("slack", "U0999")
    gateway._stamp_identity_resolver(tg, "telegram")
    gateway._stamp_identity_resolver(sl, "slack")
    assert _resolve(tg, "telegram", "12345") == _resolve(sl, "slack", "U0999")
    assert _resolve(tg, "telegram", "12345").startswith("owner")
    # Non-owner users keep the safe per-platform default.
    assert _resolve(tg, "telegram", "999") == "telegram:999"
    # Nothing is persisted into the shared resolver.
    assert resolver.resolve("telegram", "12345") == "telegram:12345"


def test_owner_link_never_overwrites_explicit_link():
    from praisonaiagents.session.identity import InMemoryIdentityResolver

    resolver = InMemoryIdentityResolver()
    resolver.link("telegram", "12345", "alice")
    gateway = WebSocketGateway(host="127.0.0.1", port=8904, identity_resolver=resolver)
    bot = _OwnerBot("telegram", "12345")
    gateway._stamp_identity_resolver(bot, "telegram")
    assert _resolve(bot, "telegram", "12345") == "alice"


def test_replaced_owner_loses_owner_identity():
    from praisonaiagents.session.identity import InMemoryIdentityResolver

    resolver = InMemoryIdentityResolver()
    gateway = WebSocketGateway(host="127.0.0.1", port=8905, identity_resolver=resolver)
    gateway._stamp_identity_resolver(_OwnerBot("telegram", "A"), "telegram")
    bot = _OwnerBot("telegram", "B")
    gateway._stamp_identity_resolver(bot, "telegram")  # hot-reload: owner A -> B
    assert _resolve(bot, "telegram", "A") == "telegram:A"
    assert _resolve(bot, "telegram", "B").startswith("owner")


def test_owner_id_scoped_to_identity_store(tmp_path):
    from praisonaiagents.session.identity import FileIdentityResolver

    ids = []
    for i, port in enumerate((8906, 8907)):
        r = FileIdentityResolver(path=tmp_path / f"id{i}.json")
        gw = WebSocketGateway(host="127.0.0.1", port=port, identity_resolver=r)
        bot = _OwnerBot("telegram", "12345")
        gw._stamp_identity_resolver(bot, "telegram")
        ids.append(_resolve(bot, "telegram", "12345"))
    assert ids[0] != ids[1]
    assert not (tmp_path / "id0.json").exists()  # owner mapping never persisted


def test_channel_without_owner_still_resolves_declared_owner():
    """A channel that admits the owner without declaring them keeps continuity."""
    from praisonaiagents.session.identity import InMemoryIdentityResolver

    resolver = InMemoryIdentityResolver()
    gateway = WebSocketGateway(host="127.0.0.1", port=8908, identity_resolver=resolver)
    owned, plain = _OwnerBot("telegram", "12345"), _OwnerBot("telegram", None)
    gateway._stamp_identity_resolver(owned, "tg_main")
    gateway._stamp_identity_resolver(plain, "tg_support")
    assert _resolve(plain, "telegram", "12345") == _resolve(owned, "telegram", "12345")
    assert _resolve(plain, "telegram", "12345").startswith("owner")
    assert _resolve(plain, "telegram", "999") == "telegram:999"


def test_owner_link_noop_without_resolver():
    gateway = _gateway_with_agent()
    bot = _OwnerBot("telegram", "12345")
    gateway._stamp_identity_resolver(bot)
    assert bot._session._identity_resolver is None


# ── start_channels / hot-reload wiring ──────────────────────────────


@pytest.mark.asyncio
async def test_start_channels_stamps_resolver_onto_created_bot():
    """The startup path stamps the resolver onto each created channel bot."""
    resolver = _StubResolver()
    gateway = _gateway_with_agent()
    gateway._identity_resolver = resolver
    created = {}

    def mock_create_bot(channel_type, token, agent, config, ch_cfg):
        bot = _FakeBot()
        created[channel_type] = bot
        return bot

    with patch.object(gateway, "_create_bot", side_effect=mock_create_bot):
        with patch.object(gateway, "_run_bot_safe", side_effect=lambda *a, **k: None):
            await gateway.start_channels({"telegram": {"token": "t"}})

    assert created["telegram"]._session._identity_resolver._inner is resolver


@pytest.mark.asyncio
async def test_hot_reload_stamps_resolver():
    """The hot-reload path stamps the resolver the same as startup."""
    resolver = _StubResolver()
    gateway = _gateway_with_agent()
    gateway._identity_resolver = resolver
    created = {}

    def mock_create_bot(channel_type, token, agent, config, ch_cfg):
        bot = _FakeBot()
        created[channel_type] = bot
        return bot

    with patch.object(gateway, "_create_bot", side_effect=mock_create_bot):
        with patch.object(gateway, "_run_bot_safe", side_effect=lambda *a, **k: None):
            await gateway._start_single_channel("telegram", {"token": "t"})

    assert created["telegram"]._session._identity_resolver._inner is resolver


# ── _build_identity_resolver (declarative identity: block) ──────────


def test_build_returns_none_when_block_missing():
    assert WebSocketGateway._build_identity_resolver(None) is None
    assert WebSocketGateway._build_identity_resolver({}) is None


def test_build_returns_none_when_disabled():
    assert WebSocketGateway._build_identity_resolver({"enabled": False}) is None
    assert WebSocketGateway._build_identity_resolver({"enabled": "no"}) is None


def test_build_creates_resolver_when_enabled(tmp_path):
    store = tmp_path / "identity.json"
    resolver = WebSocketGateway._build_identity_resolver(
        {"enabled": True, "store": str(store)}
    )
    assert resolver is not None
    # It must satisfy the resolver contract used by BotSessionManager.
    assert callable(getattr(resolver, "resolve", None))
    # Unlinked users fall back to the safe per-platform id.
    assert resolver.resolve("telegram", "123") == "telegram:123"
    # Linking merges two platforms onto one canonical id.
    resolver.link("telegram", "123", "user:alice")
    resolver.link("discord", "456", "user:alice")
    assert resolver.resolve("telegram", "123") == "user:alice"
    assert resolver.resolve("discord", "456") == "user:alice"


# ── _reconcile_identity_resolver (hot-reload of the identity: block) ─


def test_reconcile_enables_resolver_on_reload(tmp_path):
    """Enabling ``identity:`` on reload installs a resolver (was a no-op)."""
    store = tmp_path / "identity.json"
    gateway = _gateway_with_agent()
    assert gateway._identity_resolver is None
    gateway._reconcile_identity_resolver({"enabled": True, "store": str(store)})
    assert gateway._identity_resolver is not None
    assert callable(getattr(gateway._identity_resolver, "resolve", None))


def test_reconcile_disables_resolver_on_reload(tmp_path):
    """Disabling ``identity:`` on reload clears the stale resolver."""
    store = tmp_path / "identity.json"
    gateway = _gateway_with_agent()
    gateway._reconcile_identity_resolver({"enabled": True, "store": str(store)})
    assert gateway._identity_resolver is not None
    gateway._reconcile_identity_resolver({"enabled": False})
    assert gateway._identity_resolver is None


def test_reconcile_preserves_resolver_when_block_unchanged(tmp_path):
    """An unchanged block keeps the same live resolver (link cache survives)."""
    store = tmp_path / "identity.json"
    cfg = {"enabled": True, "store": str(store)}
    gateway = _gateway_with_agent()
    gateway._reconcile_identity_resolver(cfg)
    first = gateway._identity_resolver
    first.link("telegram", "123", "user:alice")
    gateway._reconcile_identity_resolver(dict(cfg))
    assert gateway._identity_resolver is first
    assert gateway._identity_resolver.resolve("telegram", "123") == "user:alice"


def test_reconcile_repoints_resolver_when_store_changes(tmp_path):
    """Re-pointing the store rebuilds the resolver."""
    gateway = _gateway_with_agent()
    gateway._reconcile_identity_resolver(
        {"enabled": True, "store": str(tmp_path / "a.json")}
    )
    first = gateway._identity_resolver
    gateway._reconcile_identity_resolver(
        {"enabled": True, "store": str(tmp_path / "b.json")}
    )
    assert gateway._identity_resolver is not first


def test_reconcile_never_clobbers_explicit_resolver(tmp_path):
    """A constructor/CLI resolver always wins over the YAML block on reload."""
    resolver = _StubResolver()
    gateway = WebSocketGateway(
        host="127.0.0.1", port=8903, identity_resolver=resolver
    )
    assert gateway._identity_resolver_explicit is True
    gateway._reconcile_identity_resolver({"enabled": True, "store": str(tmp_path)})
    assert gateway._identity_resolver is resolver
    gateway._reconcile_identity_resolver({"enabled": False})
    assert gateway._identity_resolver is resolver


# ── _stamp_turn_lock_map (Issue #3232: shared per-turn lock) ────────


def test_turn_lock_stamp_is_noop_without_resolver():
    """Without a resolver each channel keeps its own LockMap (today's behaviour)."""
    gateway = _gateway_with_agent()
    assert gateway._identity_resolver is None
    bot = _FakeBot()
    original = bot._session._locks
    gateway._stamp_turn_lock_map(bot)
    # The session's own map is untouched — no cross-channel unification exists.
    assert bot._session._locks is original
    assert getattr(gateway, "_turn_lock_map", None) is None


def test_turn_lock_stamp_wires_redis_backend_without_resolver():
    """Issue #4655: ``turn_lock.backend='redis'`` is wired even with no resolver.

    Previously the gateway built a process-local ``LockMap`` and only stamped it
    when a resolver was configured, so ``backend='redis'`` was silently inert and
    replicas of a single channel ran concurrent turns on one session.
    """
    from praisonaiagents.gateway import TurnLockConfig

    gateway = _gateway_with_agent()
    assert gateway._identity_resolver is None
    # Force a redis backend but with no reachable Redis -> build_turn_lock fails
    # open to a LockMap while recording a degraded entry; the important part is
    # that the map IS stamped onto the session (the wiring path is reached).
    gateway.config.turn_lock = TurnLockConfig(backend="redis")
    bot = _FakeBot()
    gateway._stamp_turn_lock_map(bot)
    assert getattr(gateway, "_turn_lock_map", None) is not None
    assert bot._session._locks is gateway._turn_lock_map


def test_turn_lock_stamp_shares_one_map_with_session():
    """A configured resolver stamps the gateway's shared LockMap onto the session."""
    resolver = _StubResolver()
    gateway = WebSocketGateway(
        host="127.0.0.1", port=8904, identity_resolver=resolver
    )
    bot = _FakeBot()
    gateway._stamp_turn_lock_map(bot)
    assert bot._session._locks is gateway._turn_lock_map


@pytest.mark.asyncio
async def test_turn_lock_shared_across_two_channels_yields_same_lock():
    """Two channels resolving to one unified id acquire the SAME lock (the fix).

    This is the exact bug: two adapters unify to one session but, with separate
    maps, hold two distinct locks so turns run concurrently. Sharing one map
    makes both resolve the same lock for the unified id. ``LockMap.get`` needs a
    running loop, so this test is async.
    """
    resolver = _StubResolver()  # always resolves to "user:alice"
    gateway = WebSocketGateway(
        host="127.0.0.1", port=8905, identity_resolver=resolver
    )
    telegram = _FakeBot()
    discord = _FakeBot()
    gateway._stamp_identity_resolver(telegram)
    gateway._stamp_identity_resolver(discord)
    gateway._stamp_turn_lock_map(telegram)
    gateway._stamp_turn_lock_map(discord)

    # Both sessions share one map -> one lock per resolved id across platforms.
    assert telegram._session._locks is discord._session._locks
    unified = resolver.resolve("telegram", "123")
    assert (
        telegram._session._locks.get(unified)
        is discord._session._locks.get(unified)
    )


@pytest.mark.asyncio
async def test_start_channels_shares_turn_lock_across_bots():
    """The startup path shares one LockMap across every created channel bot."""
    resolver = _StubResolver()
    gateway = _gateway_with_agent()
    gateway._identity_resolver = resolver
    created = {}

    def mock_create_bot(channel_type, token, agent, config, ch_cfg):
        bot = _FakeBot()
        created[channel_type] = bot
        return bot

    with patch.object(gateway, "_create_bot", side_effect=mock_create_bot):
        with patch.object(gateway, "_run_bot_safe", side_effect=lambda *a, **k: None):
            await gateway.start_channels(
                {"telegram": {"token": "t"}, "discord": {"token": "d"}}
            )

    assert (
        created["telegram"]._session._locks
        is created["discord"]._session._locks
    )


@pytest.mark.asyncio
async def test_hot_reload_shares_same_turn_lock():
    """A hot-reloaded channel re-shares the gateway's existing LockMap."""
    resolver = _StubResolver()
    gateway = _gateway_with_agent()
    gateway._identity_resolver = resolver
    created = {}

    def mock_create_bot(channel_type, token, agent, config, ch_cfg):
        bot = _FakeBot()
        created[channel_type] = bot
        return bot

    with patch.object(gateway, "_create_bot", side_effect=mock_create_bot):
        with patch.object(gateway, "_run_bot_safe", side_effect=lambda *a, **k: None):
            await gateway.start_channels({"telegram": {"token": "t"}})
            await gateway._start_single_channel("discord", {"token": "d"})

    assert (
        created["telegram"]._session._locks
        is created["discord"]._session._locks
    )


if __name__ == "__main__":
    pytest.main([__file__])
