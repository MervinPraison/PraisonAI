"""
Issue #3578: the gateway launch path (``WebSocketGateway._create_bot``) must
route through the shared platform registry seam so *any* channel the registry
can resolve — built-in, ``register_platform()``, or a ``praisonai.channels``
entry point — is instantiated and started, instead of hardcoding the seven
built-ins and silently returning ``None`` for everything else.
"""

import pytest

from praisonaiagents import Agent
from praisonaiagents.bots import BotConfig
from praisonai_bot.gateway.server import WebSocketGateway
from praisonai_bot.bots._registry import register_platform


def _gateway_with_agent() -> WebSocketGateway:
    gateway = WebSocketGateway(host="127.0.0.1", port=8899)
    gateway._agents["default"] = Agent(name="t", instructions="t")
    return gateway


class _FakeChannelBot:
    """Minimal adapter exercising the generic construction kwargs."""

    def __init__(self, token="", agent=None, config=None, **kwargs):
        self.token = token
        self.agent = agent
        self.config = config
        self.kwargs = kwargs


def test_registered_plugin_channel_is_launched_generically():
    """A ``register_platform``-registered channel is constructed by _create_bot."""
    register_platform("irc_test_3578", _FakeChannelBot)

    gateway = _gateway_with_agent()
    agent = gateway._agents["default"]
    ch_cfg = {"platform": "irc_test_3578", "server": "irc.libera.chat", "nick": "praison"}

    bot = gateway._create_bot(
        "irc_test_3578", "tok", agent, BotConfig(), ch_cfg
    )

    assert isinstance(bot, _FakeChannelBot)
    assert bot.token == "tok"
    # ch_cfg keys (minus platform/token) flow through as adapter kwargs.
    assert bot.kwargs["server"] == "irc.libera.chat"
    assert bot.kwargs["nick"] == "praison"


def test_unresolved_platform_records_degraded_and_returns_none():
    """An unresolvable platform is a visible degraded outcome, not a silent skip."""
    gateway = _gateway_with_agent()
    agent = gateway._agents["default"]

    marked = {}

    def _capture(kind, owner_id, reason, **kw):
        marked["value"] = (kind, owner_id, reason)

    gateway._mark_degraded_owner = _capture  # type: ignore[assignment]

    bot = gateway._create_bot(
        "definitely_not_a_platform_3578", "", agent, BotConfig(), {}
    )

    assert bot is None
    assert marked["value"][0] == "channel"
    assert marked["value"][1] == "definitely_not_a_platform_3578"
    assert marked["value"][2] == "unresolved_platform"


def test_construction_failure_records_degraded_and_returns_none():
    """A registered-but-unconstructable channel degrades instead of crashing start."""

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("cannot build")

    register_platform("boom_test_3578", _Boom)

    gateway = _gateway_with_agent()
    agent = gateway._agents["default"]

    marked = {}
    gateway._mark_degraded_owner = (  # type: ignore[assignment]
        lambda kind, owner_id, reason, **kw: marked.setdefault(
            "value", (kind, owner_id, reason)
        )
    )

    bot = gateway._create_bot("boom_test_3578", "tok", agent, BotConfig(), {})

    assert bot is None
    assert marked["value"] == (
        "channel",
        "boom_test_3578",
        "adapter_construction_failed",
    )
