"""Tests for single-``Bot`` inbound connection supervision (Issue #2869).

Verifies that ``Bot.start()``/``run()`` wraps the adapter's inbound run loop
with the shared ``ChannelSupervisor`` by default — so every channel (not just
Telegram) auto-reconnects with capped backoff — and that this can be disabled
via ``enable_supervision=False`` or an adapter's ``supervised_inbound = False``.
"""

from __future__ import annotations

import asyncio

import pytest

from praisonai_bot.bots.bot import Bot


class _FlakyAdapter:
    """Adapter whose inbound loop drops (recoverable) a few times then holds."""

    platform = "slack"

    def __init__(self, fail_times: int):
        self._fail_times = fail_times
        self.start_calls = 0
        self.stop_calls = 0
        self._hold = asyncio.Event()

    async def start(self) -> None:
        self.start_calls += 1
        if self.start_calls <= self._fail_times:
            raise ConnectionError("connection reset by peer")
        # Stable now: block until stopped.
        await self._hold.wait()

    async def stop(self) -> None:
        self.stop_calls += 1
        self._hold.set()

    async def health(self):  # pragma: no cover - health path not exercised
        from praisonaiagents.bots.protocols import HealthResult

        return HealthResult(ok=True, platform=self.platform, is_running=True)


class _RawAdapter:
    """Adapter that records whether it was started once, no reconnect."""

    platform = "slack"
    supervised_inbound = False

    def __init__(self):
        self.start_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        pass


class _NonBlockingAdapter:
    """Adapter whose ``start()`` spawns a background loop and returns.

    Mirrors Email/Linear/WhatsApp/AgentMail: ``start()`` sets ``is_running`` and
    returns immediately rather than blocking for the connection's lifetime. The
    supervised run must stay alive until the adapter stops (Issue #2869 —
    "returned starts lose supervision").
    """

    platform = "email"

    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self) -> None:
        self.start_calls += 1
        self._is_running = True  # spawns background loop, returns immediately

    async def stop(self) -> None:
        self.stop_calls += 1
        self._is_running = False


def _make_bot(adapter, **kwargs) -> Bot:
    bot = Bot("slack", **kwargs)
    bot._build_adapter = lambda: adapter  # type: ignore[method-assign]
    # Fast backoff so the test doesn't wait real seconds.
    return bot


@pytest.mark.asyncio
async def test_supervised_bot_reconnects_flaky_adapter(monkeypatch):
    # Patch backoff to near-zero so retries are fast.
    from praisonai_bot.bots import _resilience

    monkeypatch.setattr(_resilience, "compute_backoff", lambda policy, attempt: 0.0)

    adapter = _FlakyAdapter(fail_times=2)
    bot = _make_bot(adapter)

    task = asyncio.ensure_future(bot.start())
    # Give the supervisor time to burn through the two failures and settle.
    for _ in range(200):
        if adapter.start_calls >= 3:
            break
        await asyncio.sleep(0.01)

    assert adapter.start_calls >= 3, "supervisor should have reconnected after drops"

    await bot.stop()
    try:
        await asyncio.wait_for(task, timeout=2)
    except asyncio.TimeoutError:  # pragma: no cover
        task.cancel()
        raise


@pytest.mark.asyncio
async def test_disable_supervision_runs_raw_adapter():
    adapter = _FlakyAdapter(fail_times=1)
    bot = _make_bot(adapter, enable_supervision=False)

    # Without supervision the first ConnectionError propagates out unretried.
    with pytest.raises(ConnectionError):
        await bot.start()
    assert adapter.start_calls == 1


@pytest.mark.asyncio
async def test_adapter_opt_out_via_supervised_inbound_flag():
    adapter = _RawAdapter()
    bot = _make_bot(adapter)  # supervision enabled at Bot level...

    # ...but the adapter opts out, so start() calls the raw adapter directly.
    await bot.start()
    assert adapter.start_calls == 1
    assert bot._supervisor is None


@pytest.mark.asyncio
async def test_non_blocking_start_stays_supervised_until_stopped():
    # An adapter whose start() returns immediately (Email/Linear/etc.) must not
    # end supervision the instant it comes up: the supervised run stays alive
    # until the adapter stops, so a drop would be reconnected (Issue #2869).
    adapter = _NonBlockingAdapter()
    bot = _make_bot(adapter)

    task = asyncio.ensure_future(bot.start())
    for _ in range(200):
        if adapter.start_calls >= 1 and adapter.is_running:
            break
        await asyncio.sleep(0.01)

    assert adapter.start_calls == 1
    assert adapter.is_running
    # Supervision is still active — the run has NOT returned yet.
    assert not task.done(), "supervised run must stay alive after non-blocking start"

    await bot.stop()
    await asyncio.wait_for(task, timeout=2)
    assert adapter.stop_calls >= 1
