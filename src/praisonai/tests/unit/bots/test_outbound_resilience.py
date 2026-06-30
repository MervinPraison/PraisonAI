"""Tests for the shared OutboundResilienceMixin used by all bot adapters.

Verifies that every adapter wrapping its raw send in ``deliver_outbound`` gets
the same durable behaviour Telegram has always had: transient failures are
retried with backoff and permanent failures are parked in the outbound DLQ
instead of silently dropping the agent's reply.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praisonai.bots._outbound_resilience import OutboundResilienceMixin
from praisonai.bots._resilience import BackoffPolicy


class _FakeAdapter(OutboundResilienceMixin):
    _outbound_platform = "slack"

    def __init__(self, config=None):
        self.config = config


def _resilience_config(dlq_path):
    """Duck-typed config enabling the outbound DLQ with fast backoff."""
    outbound = SimpleNamespace(
        enabled=True,
        initial_ms=1,
        max_ms=2,
        factor=1.0,
        max_attempts=3,
        jitter=0.0,
        dlq_path=str(dlq_path),
    )
    return SimpleNamespace(outbound_resilience=outbound)


@pytest.mark.asyncio
async def test_success_passes_through():
    adapter = _FakeAdapter()

    async def send():
        return "ok"

    result = await adapter.deliver_outbound(
        send, channel_id="c1", reply_text="hi"
    )
    assert result == "ok"


@pytest.mark.asyncio
async def test_transient_error_is_retried():
    """A transient error succeeds on a later attempt without raising."""
    adapter = _FakeAdapter()
    # Tight backoff so the test is fast.
    adapter._outbound_resilience_ready = True
    adapter._outbound_backoff = BackoffPolicy(initial_ms=1, max_ms=2, factor=1.0, max_attempts=3)
    adapter._outbound_dlq = None

    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("connection reset by peer")
        return "delivered"

    result = await adapter.deliver_outbound(
        flaky, channel_id="c1", reply_text="hi"
    )
    assert result == "delivered"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_permanent_failure_parked_in_dlq(tmp_path):
    """A permanent failure parks the reply in the DLQ and re-raises."""
    from praisonai.bots._dlq import OutboundDLQ

    dlq_path = tmp_path / "outbound_dlq.sqlite"
    adapter = _FakeAdapter(config=_resilience_config(dlq_path))

    async def always_fails():
        # ValueError is not in the recoverable patterns -> permanent.
        raise ValueError("invalid channel")

    with pytest.raises(ValueError):
        await adapter.deliver_outbound(
            always_fails, channel_id="c1", reply_text="hello world", thread_id="t1"
        )

    dlq = OutboundDLQ(path=dlq_path)
    entries = dlq.list()
    assert len(entries) == 1
    assert entries[0].platform == "slack"
    assert entries[0].channel_id == "c1"
    assert entries[0].reply_text == "hello world"
    assert entries[0].thread_id == "t1"


@pytest.mark.asyncio
async def test_exhausted_retries_parked_in_dlq(tmp_path):
    """Transient errors that never recover are parked after max attempts."""
    from praisonai.bots._dlq import OutboundDLQ

    dlq_path = tmp_path / "outbound_dlq.sqlite"
    adapter = _FakeAdapter(config=_resilience_config(dlq_path))

    async def always_transient():
        raise ConnectionError("connection reset by peer")

    with pytest.raises(ConnectionError):
        await adapter.deliver_outbound(
            always_transient, channel_id="c2", reply_text="retry me"
        )

    dlq = OutboundDLQ(path=dlq_path)
    entries = dlq.list()
    assert len(entries) == 1
    assert entries[0].channel_id == "c2"
    assert entries[0].reply_text == "retry me"


@pytest.mark.asyncio
async def test_no_config_still_retries_without_dlq():
    """Without resilience config, sends still retry (just no DLQ park)."""
    adapter = _FakeAdapter()

    async def fails_once():
        if not getattr(fails_once, "called", False):
            fails_once.called = True
            raise TimeoutError("timed out")
        return "ok"

    result = await adapter.deliver_outbound(
        fails_once, channel_id="c1", reply_text="hi"
    )
    assert result == "ok"
    assert adapter._outbound_dlq is None


def test_all_shipped_adapters_use_the_mixin():
    """Regression guard: every channel adapter mixes in durable delivery."""
    from praisonai.bots.slack import SlackBot
    from praisonai.bots.discord import DiscordBot
    from praisonai.bots.whatsapp import WhatsAppBot
    from praisonai.bots.email import EmailBot
    from praisonai.bots.linear import LinearBot
    from praisonai.bots.agentmail import AgentMailBot

    for bot_cls in (SlackBot, DiscordBot, WhatsAppBot, EmailBot, LinearBot, AgentMailBot):
        assert issubclass(bot_cls, OutboundResilienceMixin), bot_cls.__name__
        assert getattr(bot_cls, "_outbound_platform", "")
