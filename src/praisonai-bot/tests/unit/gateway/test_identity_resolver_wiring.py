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


class _FakeSession:
    def __init__(self):
        self._identity_resolver = None


class _FakeBot:
    def __init__(self):
        self._session = _FakeSession()


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
    assert bot._session._identity_resolver is resolver


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

    assert created["telegram"]._session._identity_resolver is resolver


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

    assert created["telegram"]._session._identity_resolver is resolver


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


if __name__ == "__main__":
    pytest.main([__file__])
