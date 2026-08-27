"""Tests for the built-in ``local`` (terminal) channel.

Covers registry registration, capability declaration, the stdin→agent→stdout
turn loop, EOF exit, and ``deliver="local:local"`` routing through the shared
DeliveryRouter — the continuity/delivery infrastructure the local channel joins
just like every remote channel.
"""

import asyncio
import io
import sys

import pytest

from praisonai_bot.bots import _registry as R
from praisonai_bot.bots import LocalBot


class _FakeStdin:
    """Minimal stdin stub: yields queued lines then EOF ("")."""

    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else ""

    def isatty(self):
        return False


class _Agent:
    name = "assistant"


def test_local_is_a_builtin_platform():
    reg = R.BotPlatformRegistry()
    assert "local" in reg.list_names()
    assert reg.resolve("local") is LocalBot


def test_local_capabilities_are_tty_honest():
    caps = LocalBot.default_capabilities()
    assert caps.supports_edit is False
    assert caps.accepts_webhooks is False
    assert caps.needs_rate_limit is False


def test_local_is_token_free_and_not_supervised():
    bot = LocalBot()
    assert bot.platform == "local"
    # No transport to reconnect — the read loop must not be supervised.
    assert bot.supervised_inbound is False
    # Shares the standard session manager seam like every built-in adapter.
    assert hasattr(bot, "_session")


def test_local_turn_loop_and_eof(monkeypatch):
    """A line of input is routed to the agent and the reply hits stdout."""
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", _FakeStdin(["hello\n"]))
    monkeypatch.setattr(sys, "stdout", out)

    bot = LocalBot(prompt="you> ")
    bot.set_agent(_Agent())

    async def _fake_chat(agent, user_id, content, **kwargs):
        return f"echo:{content}"

    bot._session.chat = _fake_chat

    asyncio.run(asyncio.wait_for(bot.start(), timeout=5))

    printed = out.getvalue()
    assert "echo:hello" in printed
    assert "you> " in printed
    # EOF ended the session cleanly.
    assert bot.is_running is False


def test_deliver_local_routes_through_router(monkeypatch):
    """``deliver="local:local"`` resolves and writes to stdout via the router."""
    from praisonai_bot.bots import BotOS

    botos = BotOS(agent=_Agent(), platforms=["local"])
    assert "local" in botos.list_bots()

    bot = botos.get_bot("local")
    bot._adapter = bot._build_adapter()

    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)

    ok = asyncio.run(
        botos._delivery_router.deliver("local:local", "proactive-ping")
    )
    assert ok is True
    assert "proactive-ping" in out.getvalue()
