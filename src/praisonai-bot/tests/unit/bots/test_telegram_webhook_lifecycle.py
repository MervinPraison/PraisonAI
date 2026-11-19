"""Telegram webhook lifecycle without network access."""
import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

pytest.importorskip("telegram")
from telegram.ext import Application
from praisonaiagents.bots.config import BotConfig
from praisonai_bot.bots.telegram import TelegramBot


@pytest.fixture
def webhook(monkeypatch, tmp_path):
    from praisonai_bot.bots import telegram as module
    from praisonai_bot.gateway.pairing import PairingStore
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setattr(module, "PairingStore", lambda: PairingStore(
        store_dir=str(tmp_path / "pairing"), secret="synthetic-test-secret"))
    state = SimpleNamespace(ready=asyncio.Event(), app=None, failure=None)

    class App:
        def __init__(self):
            self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
                id=1, username="synthetic", first_name="Synthetic")), set_my_commands=AsyncMock())
            self.initialize = AsyncMock()
            self.start = AsyncMock()
            self.stop = AsyncMock()
            self.shutdown = AsyncMock()
            self.updater = SimpleNamespace(start_webhook=AsyncMock(side_effect=self.ready), stop=AsyncMock())
            state.app = self

        def add_handler(self, *args, **kwargs):
            pass

        def run_webhook(self, **kwargs):
            return None

        async def ready(self, **kwargs):
            if state.failure:
                raise state.failure
            state.ready.set()

    monkeypatch.setattr(Application, "builder", lambda: SimpleNamespace(
        token=lambda token: SimpleNamespace(build=App)))
    return state


@pytest.mark.asyncio
async def test_webhook_respects_port_and_stops(webhook):
    config = BotConfig(token="synthetic", webhook_url="https://example.invalid", webhook_path="/hook", webhook_port=9087)
    bot = TelegramBot(token="synthetic", config=config)
    task = asyncio.create_task(bot.start())
    try:
        await asyncio.wait_for(webhook.ready.wait(), 1)
        assert bot.is_running
        webhook.app.updater.start_webhook.assert_awaited_once_with(
            listen="0.0.0.0", port=9087, url_path="/hook", webhook_url="https://example.invalid/hook",
            secret_token=ANY)
        await bot.stop()
        await asyncio.wait_for(task, 1)
        assert not bot.is_running
        webhook.app.updater.stop.assert_awaited_once()
        webhook.app.stop.assert_awaited_once()
        webhook.app.shutdown.assert_awaited_once()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_webhook_start_failure_cleans_partial_application(webhook):
    config = BotConfig(token="synthetic", webhook_url="https://example.invalid")
    bot = TelegramBot(token="synthetic", config=config)
    webhook.failure = ValueError("synthetic start failure")
    with pytest.raises(ValueError, match="synthetic start failure"):
        await bot.start()
    assert not bot.is_running
    webhook.app.updater.stop.assert_awaited_once()
    webhook.app.stop.assert_awaited_once()
    webhook.app.shutdown.assert_awaited_once()
