"""Offline polling lifecycle regressions for #6031; no Telegram requests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# python-telegram-bot is an optional platform SDK (same as discord in
# test_outbound_media.py); skip when it is not installed.
pytest.importorskip("telegram")

from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, MessageHandler

from praisonai_bot.bots.telegram import TelegramBot
from praisonai_bot.bots import _resilience as resilience


@pytest.fixture
def polling(monkeypatch, tmp_path):
    """Build real handlers on fake applications with deterministic startup failures."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from praisonai_bot.bots import telegram as module
    from praisonai_bot.gateway.pairing import PairingStore
    # The module-level default directory was resolved before this fixture;
    # changing HOME alone must not send a test through an operator's store.
    monkeypatch.setattr(module, "PairingStore", lambda: PairingStore(
        store_dir=str(tmp_path / "pairing"), secret="synthetic-test-secret"))
    state = SimpleNamespace(apps=[], errors=[], ready=asyncio.Event(), attempts=0)

    class App:
        def __init__(self):
            self.handlers = []
            self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
                id=1, username="synthetic", first_name="Synthetic")))
            self.bot.set_my_commands = AsyncMock()
            self.updater = SimpleNamespace(start_polling=self.poll, stop=AsyncMock())
            self.initialize = AsyncMock()
            self.start = AsyncMock()
            self.stop = AsyncMock()
            self.shutdown = AsyncMock()
            state.apps.append(self)

        def add_handler(self, handler, *args, **kwargs):
            self.handlers.append(handler)

        async def poll(self, **kwargs):
            state.attempts += 1
            if state.errors:
                raise state.errors.pop(0)
            state.ready.set()

    monkeypatch.setattr(Application, "builder", lambda: SimpleNamespace(
        token=lambda token: SimpleNamespace(build=App)))
    async def no_backoff(delay, signal):
        return not signal.is_set()
    monkeypatch.setattr(resilience, "sleep_with_abort", no_backoff)
    return state


@pytest.mark.asyncio
async def test_retry_keeps_handlers_and_stop_works(polling, monkeypatch):
    """A successful reconnect dispatches text and remains cleanly stoppable."""
    from praisonai_bot.bots import telegram as module

    polling.errors = [TimedOut("Timed out")]
    bot = TelegramBot(token="123:synthetic")
    received = []
    bot._message_handlers.append(received.append)
    message = SimpleNamespace(is_command=False)
    monkeypatch.setattr(module, "process_inbound_telegram_message", AsyncMock(return_value=message))
    task = asyncio.create_task(bot.start())
    try:
        await asyncio.wait_for(polling.ready.wait(), 2)
        assert bot.is_running
        assert bot._application.handlers
        handler = next(h for h in bot._application.handlers
                       if isinstance(h, MessageHandler) and h.callback.__name__ == "handle_message")
        await handler.callback(object(), None)
        assert received == [message]
        await bot.stop()
        await asyncio.wait_for(task, 1)
        assert bot._stop_event.is_set()
        assert not bot.is_running
        assert polling.attempts == 2
        assert all(app.shutdown.await_count for app in polling.apps)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_give_up_raises_instead_of_clean_return(polling):
    """A fatal startup failure must reach the existing supervisor contract."""
    polling.errors = [ValueError("synthetic fatal startup")]
    bot = TelegramBot(token="123:synthetic")
    with pytest.raises(ValueError, match="synthetic fatal startup"):
        await bot.start()
    assert not bot.is_running


@pytest.mark.asyncio
async def test_fatal_adapter_is_failed_under_supervision(polling):
    """Giving up must not be registered as an intentional clean stop."""
    from praisonai_bot.gateway.supervisor import ChannelSupervisor, ChannelState

    polling.errors = [ValueError("synthetic fatal startup")]
    bot = TelegramBot(token="123:synthetic")
    supervisor = ChannelSupervisor()
    await supervisor.run("telegram", bot, lambda name, adapter: adapter.start())
    status = supervisor.get_status("telegram")
    assert status.state == ChannelState.FAILED
    assert "synthetic fatal startup" in status.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize("uptime,expected", [(0, [1, 2, 3]), (10, [1, 1, 1])])
async def test_supervisor_only_resets_backoff_after_stable_run(monkeypatch, uptime, expected):
    """Long healthy runs reset backoff, while a rapid crash loop still escalates."""
    import time
    from praisonai_bot.gateway import supervisor as module

    clock = [0]
    monkeypatch.setattr(module, "time", SimpleNamespace(time=time.time, monotonic=lambda: clock[0]))
    attempts = []
    record = resilience.ConnectionMonitor.record_error
    def record_error(monitor, error):
        record(monitor, error)
        attempts.append(monitor.attempt)
        return 0
    monkeypatch.setattr(resilience.ConnectionMonitor, "record_error", record_error)
    supervisor = module.ChannelSupervisor(policy=resilience.BackoffPolicy(initial_ms=1, max_ms=1000, jitter=0))
    runs = []
    async def start(name, bot):
        runs.append(name)
        clock[0] += uptime
        if len(runs) <= 3:
            raise ConnectionError("synthetic outage")
    await supervisor.run("synthetic", SimpleNamespace(platform="synthetic"), start)
    assert attempts == expected


def test_wrapped_telegram_network_error_is_recoverable():
    """PTB's NetworkError is transient even when its message has no known substring."""
    assert resilience.is_recoverable_error(NetworkError("opaque transport failure"), "telegram")
