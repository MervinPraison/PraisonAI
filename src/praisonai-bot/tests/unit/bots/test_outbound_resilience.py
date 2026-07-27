"""Tests for the shared OutboundResilienceMixin used by all bot adapters.

Verifies that every adapter wrapping its raw send in ``deliver_outbound`` gets
the same durable behaviour Telegram has always had: transient failures are
retried with backoff and permanent failures are parked in the outbound DLQ
instead of silently dropping the agent's reply.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praisonai_bot.bots._outbound_resilience import OutboundResilienceMixin
from praisonai_bot.bots._resilience import BackoffPolicy


@pytest.fixture(autouse=True)
def _isolate_praisonai_home(monkeypatch, tmp_path):
    """Keep the default outbound DLQ (#3446) off the real ``~/.praisonai``."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))


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
    from praisonai_bot.bots._dlq import OutboundDLQ

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
    from praisonai_bot.bots._dlq import OutboundDLQ

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
async def test_no_config_still_retries(monkeypatch, tmp_path):
    """Without resilience config, sends still retry with the default DLQ on."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
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


@pytest.mark.asyncio
async def test_default_dlq_on_without_config(monkeypatch, tmp_path):
    """Safe by default (#3446): a permanent failure parks even with no config.

    Mirrors the durable inbound journal — the outbound reply is a durable
    delivery obligation by default, so a permanently-failed send is parked at
    the canonical per-platform store path rather than silently dropped.
    """
    from praisonai_bot.bots._dlq import OutboundDLQ

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    adapter = _FakeAdapter()

    async def always_fails():
        raise ValueError("invalid channel")

    with pytest.raises(ValueError):
        await adapter.deliver_outbound(
            always_fails, channel_id="c1", reply_text="paid-for reply"
        )

    assert adapter._outbound_dlq is not None
    dlq_path = tmp_path / "state" / "slack" / "outbound_dlq.sqlite"
    assert dlq_path.exists()
    entries = OutboundDLQ(path=dlq_path).list()
    assert len(entries) == 1
    assert entries[0].reply_text == "paid-for reply"


@pytest.mark.asyncio
async def test_enabled_false_disables_default_dlq(monkeypatch, tmp_path):
    """Escape hatch: ``enabled=false`` turns the durable park off entirely."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    disabled = SimpleNamespace(outbound_resilience=SimpleNamespace(enabled=False))
    adapter = _FakeAdapter(config=disabled)

    async def fails_once():
        if not getattr(fails_once, "called", False):
            fails_once.called = True
            raise ValueError("invalid channel")
        return "ok"

    with pytest.raises(ValueError):
        await adapter.deliver_outbound(
            fails_once, channel_id="c1", reply_text="hi"
        )
    assert adapter._outbound_dlq is None


@pytest.mark.asyncio
async def test_transient_dlq_init_failure_recovers(monkeypatch, tmp_path):
    """A transient DLQ-init failure must not permanently disable parking (#3446).

    Regression: the first send fails to build the default DLQ (storage briefly
    unavailable) and degrades to retry-only, but the resilience state must NOT
    latch as ``ready``. Once storage recovers, a later send re-attempts init,
    parks the permanent failure, and the reply is durable again.
    """
    import praisonai_bot.bots._dlq as dlq_mod
    from praisonai_bot.bots._dlq import OutboundDLQ

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    adapter = _FakeAdapter()

    calls = {"n": 0}
    real_cls = dlq_mod.OutboundDLQ

    def flaky_dlq(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("storage temporarily unavailable")
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(dlq_mod, "OutboundDLQ", flaky_dlq)

    async def always_fails():
        raise ValueError("invalid channel")

    # First send: DLQ init fails -> retry-only, reply lost this turn, but state
    # must stay un-latched so it can recover.
    with pytest.raises(ValueError):
        await adapter.deliver_outbound(always_fails, channel_id="c1", reply_text="first")
    assert adapter._outbound_dlq is None
    assert getattr(adapter, "_outbound_resilience_ready", False) is False

    # Second send: storage recovered -> DLQ init succeeds and reply is parked.
    with pytest.raises(ValueError):
        await adapter.deliver_outbound(always_fails, channel_id="c1", reply_text="second")
    assert adapter._outbound_dlq is not None

    dlq_path = tmp_path / "state" / "slack" / "outbound_dlq.sqlite"
    entries = OutboundDLQ(path=dlq_path).list()
    assert [e.reply_text for e in entries] == ["second"]


@pytest.mark.asyncio
async def test_whatsapp_send_propagates_durable_failure():
    """WhatsApp must not swallow an exhausted/permanent durable failure.

    Regression for the partial-delivery bug: when ``deliver_outbound`` re-raises
    after parking/exhausting retries, ``send_message`` must propagate it rather
    than returning a success-looking ``BotMessage`` (parity with the other
    adapters). We bind the unbound ``send_message`` to a minimal stub so no
    network/aiohttp setup is required.
    """
    pytest.importorskip("aiohttp")
    from praisonai_bot.bots.whatsapp import WhatsAppBot

    class _RateLimiter:
        async def acquire(self, _to):
            return None

    class _Stub:
        config = SimpleNamespace(max_message_length=4096)
        _phone_number_id = "pid"
        _token = "tok"
        _http_session = None
        _bot_user = None
        _rate_limiter = _RateLimiter()

        async def deliver_outbound(self, *args, **kwargs):
            raise ConnectionError("connection reset by peer")

    stub = _Stub()
    with pytest.raises(ConnectionError):
        await WhatsAppBot.send_message(stub, to="c1", content="hello")


def test_all_shipped_adapters_use_the_mixin():
    """Regression guard: every channel adapter mixes in durable delivery."""
    from praisonai_bot.bots.slack import SlackBot
    from praisonai_bot.bots.discord import DiscordBot
    from praisonai_bot.bots.whatsapp import WhatsAppBot
    from praisonai_bot.bots.email import EmailBot
    from praisonai_bot.bots.linear import LinearBot
    from praisonai_bot.bots.agentmail import AgentMailBot

    for bot_cls in (SlackBot, DiscordBot, WhatsAppBot, EmailBot, LinearBot, AgentMailBot):
        assert issubclass(bot_cls, OutboundResilienceMixin), bot_cls.__name__
        assert getattr(bot_cls, "_outbound_platform", "")
