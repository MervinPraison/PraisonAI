"""
Unit tests for the out-of-process ("standalone") scheduled delivery sender.

When ``ScheduledAgentExecutor`` runs with no live ``delivery_handler`` (a plain
OS-cron / CI / serverless ``praisonai schedule tick``), a job's ``deliver:``
target must still be delivered via a stateless, token-authenticated HTTP call.
These tests cover:

- resolver: known platform → sender, unknown/empty → ``None``
- executor fallback: no live handler → standalone sender is used
- home-channel env: a bare-platform target resolves its chat id from env
- missing token / no target → ``delivery_error`` recorded, not silently dropped
- live handler still wins when present (unchanged path)
"""

import asyncio
from typing import List

import pytest

from praisonaiagents.scheduler.models import (
    ScheduleJob,
    Schedule,
    DeliveryTarget,
)
from praisonai_bot.scheduler.executor import ScheduledAgentExecutor
from praisonai_bot.scheduler import _standalone_sender as ss


class FakeRunner:
    def __init__(self):
        self.runs: List[dict] = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


def _run(coro):
    return asyncio.run(coro)


def _job(message="hello", deliver="telegram:123"):
    return ScheduleJob(
        name="j",
        schedule=Schedule(kind="every", every_seconds=1),
        message=message,
        delivery=DeliveryTarget.parse(deliver),
    )


def _agent_executor(**kwargs):
    return ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: _EchoAgent(),
        **kwargs,
    )


class _EchoAgent:
    def chat(self, message, **kwargs):
        return f"echo:{message}"


# ── resolver ─────────────────────────────────────────────────────────


def test_resolver_known_and_unknown():
    assert ss.resolve_standalone_sender("telegram") is not None
    assert ss.resolve_standalone_sender("Slack") is not None
    assert ss.resolve_standalone_sender("discord") is not None
    # Platforms with a live adapter now also have a standalone sender (#4050).
    assert ss.resolve_standalone_sender("whatsapp") is not None
    assert ss.resolve_standalone_sender("Signal") is not None
    assert ss.resolve_standalone_sender("irc") is None
    assert ss.resolve_standalone_sender("") is None
    assert ss.resolve_standalone_sender(None) is None  # type: ignore[arg-type]


# ── executor fallback ────────────────────────────────────────────────


def test_fallback_used_when_no_live_handler(monkeypatch):
    sent: list = []

    async def fake_telegram(target, text):
        sent.append((target.channel_id, text))

    monkeypatch.setitem(ss._STANDALONE_SENDERS, "telegram", fake_telegram)

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job()))

    assert result.status == "succeeded"
    assert result.delivered is True
    assert result.delivery_error is None
    assert sent == [("123", "echo:hello")]


def test_home_channel_env_resolves_bare_platform(monkeypatch):
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append((url, payload))

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0KEN")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-100555")

    ex = _agent_executor(delivery_handler=None)
    # Bare-platform target: channel set, channel_id empty → env home channel.
    result = _run(ex._execute_one(_job(deliver="telegram")))

    assert result.delivered is True
    assert captured, "expected an HTTP send"
    url, payload = captured[0]
    assert "botT0KEN/sendMessage" in url
    assert payload["chat_id"] == "-100555"
    assert payload["text"] == "echo:hello"


def test_missing_token_records_delivery_error(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="telegram:123")))

    # Job still ran and succeeded; only delivery failed and is auditable.
    assert result.status == "succeeded"
    assert result.delivered is False
    assert result.delivery_error is not None
    assert "TELEGRAM_BOT_TOKEN" in result.delivery_error


def test_unsupported_platform_records_delivery_error():
    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="irc:chan")))

    # The run itself is intact, but an unsupported target must never be silently
    # dropped: with no live handler and no standalone sender, delivery raises and
    # the error is recorded so a misconfigured target is auditable.
    assert result.status == "succeeded"
    assert result.delivered is False
    assert result.delivery_error is not None
    assert "irc" in result.delivery_error


def test_long_message_is_chunked(monkeypatch):
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append(payload)

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0KEN")

    long_agent = "x" * 9000

    class _BigAgent:
        def chat(self, message, **kwargs):
            return long_agent

    ex = ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: _BigAgent(),
        delivery_handler=None,
    )
    result = _run(ex._execute_one(_job(deliver="telegram:123")))

    assert result.delivered is True
    # 9000 chars over the 4096 Telegram limit → more than one send.
    assert len(captured) > 1
    assert all(len(p["text"]) <= 4096 for p in captured)
    assert "".join(p["text"] for p in captured) == long_agent


def test_discord_thread_id_sets_message_reference(monkeypatch):
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append((url, payload))

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "D0KEN")

    ex = _agent_executor(delivery_handler=None)
    # discord:<channel>:<thread/message id> → message_reference reply.
    result = _run(ex._execute_one(_job(deliver="discord:999:777")))

    assert result.delivered is True
    assert captured, "expected a discord send"
    url, payload = captured[0]
    assert "/channels/999/messages" in url
    assert payload["content"] == "echo:hello"
    ref = payload.get("message_reference")
    assert ref is not None
    assert ref["message_id"] == "777"
    assert ref["channel_id"] == "999"


def test_home_channel_registry_fallback(monkeypatch, tmp_path):
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append(payload)

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0KEN")
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)

    # Simulate a home channel registered via the live gateway (no env var).
    import json as _json

    state_dir = tmp_path / ".praisonai" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "home_channels.json").write_text(
        _json.dumps({"telegram": {"chat_id": "-100999", "thread_id": None}})
    )
    monkeypatch.setattr(ss.Path, "home", classmethod(lambda cls: tmp_path))

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="telegram")))

    assert result.delivered is True
    assert captured and captured[0]["chat_id"] == "-100999"


def test_live_handler_still_wins(monkeypatch):
    live: list = []

    async def deliver(target, text):
        live.append((target.channel_id, text))

    def _boom(url, payload, headers=None):
        raise AssertionError("standalone sender must not be used with a live handler")

    monkeypatch.setattr(ss, "_post_json", _boom)

    ex = _agent_executor(delivery_handler=deliver)
    result = _run(ex._execute_one(_job()))

    assert result.delivered is True
    assert live == [("123", "echo:hello")]


def test_a_failed_delivery_is_not_recorded_as_delivered():
    """Issue #4193: a live handler that returns ``False`` (a non-raising
    delivery failure, e.g. the router could not resolve the target) must not be
    recorded as ``delivered``. 'The handler returned' is not 'the message
    arrived' — recording it as delivered makes the run history wrong and
    suppresses failure alerting.
    """

    async def deliver(target, text):
        # Mirrors the gateway's ``_deliver_scheduled_result`` returning False
        # when routing fails, instead of raising.
        return False

    ex = _agent_executor(delivery_handler=deliver)
    result = _run(ex._execute_one(_job(deliver="telegram:42")))

    assert result.status == "succeeded"
    assert result.delivered is False
    assert "telegram:42" in (result.delivery_error or "")


def test_handler_returning_none_is_treated_as_delivered():
    """A live handler that returns ``None`` still counts as delivered, so
    adapters that report success by simply not raising keep working (backward
    compatible with the pre-#4193 contract).
    """

    async def deliver(target, text):
        return None

    ex = _agent_executor(delivery_handler=deliver)
    result = _run(ex._execute_one(_job(deliver="telegram:42")))

    assert result.delivered is True
    assert result.delivery_error is None


class _OkScan:
    ok = True
    reason = None


class _DeliverOnFailurePolicy:
    """Minimal duck-typed run policy that enables fail-closed delivery."""

    deliver_on_failure = True
    audit_dir = None

    def scan_prompt(self, _text):
        return _OkScan()

    def filter_tools(self, tools):
        return tools


class _BoomAgent:
    def chat(self, message, **kwargs):
        raise RuntimeError("agent blew up")


def test_delivered_failure_summary_is_recorded_as_delivered():
    """When a job fails and its failure summary is delivered successfully,
    the run must be recorded as ``delivered`` — the payload reached the
    channel. Leaving ``delivered`` False makes monitoring report a delivered
    notification as undelivered (Greptile #4198).
    """
    sent: list = []

    async def deliver(target, text):
        sent.append((target.channel_id, text))

    ex = ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: _BoomAgent(),
        delivery_handler=deliver,
        run_policy=_DeliverOnFailurePolicy(),
    )
    result = _run(ex._execute_one(_job(deliver="telegram:42")))

    assert result.status == "failed"
    assert result.delivered is True
    assert result.delivery_error is None
    assert sent and sent[0][0] == "42"


def test_failed_failure_summary_is_not_recorded_as_delivered():
    """A failure summary whose delivery itself fails (handler returns False)
    must stay ``delivered=False`` and record a ``delivery_error``.
    """

    async def deliver(target, text):
        return False

    ex = ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: _BoomAgent(),
        delivery_handler=deliver,
        run_policy=_DeliverOnFailurePolicy(),
    )
    result = _run(ex._execute_one(_job(deliver="telegram:42")))

    assert result.status == "failed"
    assert result.delivered is False
    assert "telegram:42" in (result.delivery_error or "")


# ── new-platform standalone senders (#4050) ──────────────────────────


def test_whatsapp_standalone_send(monkeypatch):
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append((url, payload, headers))

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "WATOKEN")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "PN123")

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="whatsapp:15551234")))

    assert result.delivered is True
    assert captured, "expected a whatsapp send"
    url, payload, headers = captured[0]
    assert "/PN123/messages" in url
    assert payload["to"] == "15551234"
    assert payload["text"]["body"] == "echo:hello"
    assert headers["Authorization"] == "Bearer WATOKEN"


def test_whatsapp_thread_id_omits_reply_context(monkeypatch):
    # A scheduler thread_id is NOT a WhatsApp message id, so it must never be
    # mapped to context.message_id (which the Cloud API would reject as invalid).
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append(payload)

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "WATOKEN")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "PN123")

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="whatsapp:15551234:threadABC")))

    assert result.delivered is True
    assert captured, "expected a whatsapp send"
    assert "context" not in captured[0]


def test_whatsapp_missing_token_records_delivery_error(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="whatsapp:15551234")))

    assert result.status == "succeeded"
    assert result.delivered is False
    assert result.delivery_error is not None
    assert "WHATSAPP_ACCESS_TOKEN" in result.delivery_error


def test_signal_standalone_send(monkeypatch):
    captured: list = []

    def fake_post(url, payload, headers=None):
        captured.append((url, payload))

    monkeypatch.setattr(ss, "_post_json", fake_post)
    monkeypatch.setenv("SIGNAL_ACCOUNT", "+15550000")
    monkeypatch.setenv("SIGNAL_BRIDGE_URL", "http://bridge:9090")

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="signal:+15551234")))

    assert result.delivered is True
    assert captured, "expected a signal send"
    url, payload = captured[0]
    assert url == "http://bridge:9090/v2/send"
    assert payload["number"] == "+15550000"
    assert payload["recipients"] == ["+15551234"]
    assert payload["message"] == "echo:hello"


# ── bounded retry (#4050) ────────────────────────────────────────────


async def _no_sleep(*_a, **_k):
    # Zero-delay stand-in so the retry loop does not actually wait in tests.
    return None


def test_transient_failure_is_retried_then_succeeds(monkeypatch):
    calls: list = []

    def flaky_post(url, payload, headers=None):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("HTTP 503: service unavailable")

    monkeypatch.setattr(ss, "_post_json", flaky_post)
    monkeypatch.setattr(ss.asyncio, "sleep", _no_sleep)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0KEN")

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="telegram:123")))

    assert result.delivered is True
    assert result.delivery_error is None
    assert len(calls) == 2  # first attempt failed, retry succeeded


def test_http_date_retry_after_is_honoured():
    # A 429 with an HTTP-date Retry-After must not be discarded: the shared
    # server_retry_after helper parses the date form off the error's headers.
    from email.utils import format_datetime
    from datetime import datetime, timezone, timedelta

    from praisonai_bot.bots._resilience import server_retry_after

    future = datetime.now(timezone.utc) + timedelta(seconds=45)
    err = ss._HttpSendError(429, "too many requests", format_datetime(future))

    wait = server_retry_after(err)
    assert wait is not None
    # Allow scheduling slack; the mandated wait is ~45s, never zero/None.
    assert 30.0 <= wait <= 45.0


def test_integer_retry_after_is_honoured():
    from praisonai_bot.bots._resilience import server_retry_after

    err = ss._HttpSendError(429, "slow down", "30")
    assert server_retry_after(err) == 30.0


def test_permanent_failure_is_not_retried(monkeypatch):
    calls: list = []

    def bad_post(url, payload, headers=None):
        calls.append(payload)
        raise RuntimeError("HTTP 403: forbidden")

    slept: list = []

    async def _record_sleep(*_a, **_k):
        slept.append(True)

    monkeypatch.setattr(ss, "_post_json", bad_post)
    monkeypatch.setattr(ss.asyncio, "sleep", _record_sleep)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0KEN")

    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="telegram:123")))

    assert result.delivered is False
    assert result.delivery_error is not None
    assert len(calls) == 1  # permanent 403 not retried
    assert not slept
