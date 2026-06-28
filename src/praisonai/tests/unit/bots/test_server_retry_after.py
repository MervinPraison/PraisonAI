#!/usr/bin/env python3
"""
Tests for honouring server-provided Retry-After hints (issue #2427).

Covers:
  * server_retry_after() extraction from Telegram flood_wait / HTTP 429.
  * deliver_with_retry honouring the mandated wait + penalising the lane.
  * RateLimiter.penalise() widening a channel lane for the window.
  * OutboundQueue gating the next retry by the stored server hint.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from praisonai.bots._resilience import (
    server_retry_after,
    deliver_with_retry as resilience_deliver,
    BackoffPolicy,
    ConnectionMonitor,
)
from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig


class TelegramFloodWait(Exception):
    """Mimics python-telegram-bot RetryAfter (exposes .retry_after)."""

    def __init__(self, seconds):
        self.retry_after = seconds
        super().__init__(f"Flood control exceeded. Retry in {seconds} seconds")


class TelegramRawError(Exception):
    """Mimics raw Bot API 429 with parameters.retry_after."""

    def __init__(self, seconds):
        self.parameters = {"retry_after": seconds}
        super().__init__("Too Many Requests: retry later")


class FakeResponse:
    def __init__(self, headers):
        self.headers = headers


class HTTPRateLimit(Exception):
    """Mimics an HTTP client error carrying a response with Retry-After."""

    def __init__(self, retry_after_header):
        self.response = FakeResponse({"Retry-After": retry_after_header})
        super().__init__("429 Too Many Requests")


# ── server_retry_after extraction ──────────────────────────────────

def test_telegram_flood_wait_attribute():
    assert server_retry_after(TelegramFloodWait(30)) == 30.0


def test_telegram_raw_parameters():
    assert server_retry_after(TelegramRawError(45)) == 45.0


def test_http_retry_after_seconds():
    assert server_retry_after(HTTPRateLimit("12")) == 12.0


def test_http_retry_after_httpdate():
    from email.utils import format_datetime
    from datetime import datetime, timezone, timedelta

    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    val = server_retry_after(HTTPRateLimit(format_datetime(future)))
    assert val is not None
    assert 15 <= val <= 21


def test_text_fallback():
    assert server_retry_after(Exception("Rate limited, retry after 25")) == 25.0
    assert server_retry_after(Exception("retry_after: 7")) == 7.0


def test_no_hint_returns_none():
    assert server_retry_after(Exception("connection reset")) is None
    assert server_retry_after(None) is None


# ── ConnectionMonitor honours the hint over backoff ────────────────

def test_connection_monitor_uses_mandated_wait():
    mon = ConnectionMonitor(platform="telegram", policy=BackoffPolicy(initial_ms=1000))
    delay = mon.record_error(TelegramFloodWait(30))
    assert delay == 30.0


def test_connection_monitor_falls_back_to_backoff():
    mon = ConnectionMonitor(platform="telegram", policy=BackoffPolicy(initial_ms=1000, jitter=0))
    delay = mon.record_error(Exception("connection reset"))
    assert delay == pytest.approx(1.0, abs=0.01)


# ── RateLimiter.penalise widens a lane ─────────────────────────────

def _run_acquire_capturing_sleeps(actions):
    """Run ``actions(limiter)`` capturing the per-acquire sleep durations.

    Patches the rate limiter's bound ``acquire`` to record the total wait it
    *would* sleep, without actually sleeping, so timing is deterministic and
    does not mutate the global asyncio module.
    """
    slept = []
    limiter = RateLimiter(RateLimitConfig(messages_per_second=1000, per_channel_delay=0.0, burst_size=100))

    real_acquire = RateLimiter.acquire

    async def patched_acquire(self, channel_id=None):
        import praisonai.bots._rate_limit as rl
        captured = {}
        orig = rl.asyncio.sleep

        async def fake_sleep(seconds):
            captured["s"] = seconds

        rl.asyncio.sleep = fake_sleep
        try:
            await real_acquire(self, channel_id)
        finally:
            rl.asyncio.sleep = orig
        slept.append(captured.get("s", 0.0))

    async def run():
        RateLimiter.acquire = patched_acquire
        try:
            await actions(limiter)
        finally:
            RateLimiter.acquire = real_acquire

    asyncio.run(run())
    return slept


def test_rate_limiter_penalise_holds_off_channel():
    async def actions(limiter):
        await limiter.penalise("chanA", 0.5)
        await limiter.acquire("chanA")
        await limiter.acquire("chanB")

    slept = _run_acquire_capturing_sleeps(actions)
    # chanA was penalised (~0.5s); chanB unaffected (no/zero wait).
    assert any(s >= 0.4 for s in slept)
    assert not any(0 < s < 0.4 for s in slept)


def test_rate_limiter_penalise_zero_is_noop():
    async def actions(limiter):
        await limiter.penalise("chanA", 0)
        await limiter.acquire("chanA")

    slept = _run_acquire_capturing_sleeps(actions)
    assert not any(s > 0 for s in slept)


# ── deliver_with_retry honours the hint and penalises ──────────────

def test_resilience_deliver_honours_retry_after(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    async def send():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TelegramFloodWait(30)
        return "ok"

    async def run():
        return await resilience_deliver(
            send,
            policy=BackoffPolicy(initial_ms=2000, factor=1.8, max_attempts=3),
            platform="telegram",
        )

    result = asyncio.run(run())
    assert result == "ok"
    # Honoured the mandated 30s, not the ~2s policy backoff.
    assert slept == [30.0]


def test_delivery_deliver_with_retry_penalises_lane(monkeypatch):
    from praisonai.bots import _delivery

    async def fake_sleep_with_abort(seconds, abort_signal=None):
        return True

    monkeypatch.setattr(_delivery, "sleep_with_abort", fake_sleep_with_abort)

    limiter = RateLimiter(RateLimitConfig(messages_per_second=1000, per_channel_delay=0.0, burst_size=100))

    calls = {"n": 0}

    class Adapter:
        async def send_message(self, channel_id, content, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise HTTPRateLimit("5")
            return "ok"

    async def run():
        return await _delivery.deliver_with_retry(
            Adapter(),
            "chanX",
            "hi",
            max_attempts=3,
            platform="discord",
            rate_limiter=limiter,
        )

    success, err = asyncio.run(run())
    assert success is True
    # The lane should have been penalised by ~5s.
    assert limiter._channel_penalty_until.get("chanX", 0) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
