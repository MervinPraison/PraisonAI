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


def test_unsupported_platform_not_marked_delivered():
    ex = _agent_executor(delivery_handler=None)
    result = _run(ex._execute_one(_job(deliver="irc:chan")))

    assert result.status == "succeeded"
    assert result.delivered is False
    # No sender and no live handler → nothing sent, but the run is intact.
    assert result.delivery_error is None


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
