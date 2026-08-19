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
