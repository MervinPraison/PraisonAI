"""Telegram webhook mode always registers a secret_token; no Telegram requests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")

from telegram.ext import Application

from praisonai_bot.bots.telegram import TelegramBot
from praisonaiagents.bots import BotConfig

_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


@pytest.fixture
def webhook_app(monkeypatch, tmp_path):
    """Fake Application whose updater.start_webhook records its kwargs."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    from praisonai_bot.bots import telegram as module
    from praisonai_bot.gateway.pairing import PairingStore

    monkeypatch.setattr(module, "PairingStore", lambda: PairingStore(
        store_dir=str(tmp_path / "pairing"), secret="synthetic-test-secret"))
    calls = []

    class App:
        def __init__(self):
            self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(
                id=1, username="synthetic", first_name="Synthetic")))
            self.bot.set_my_commands = AsyncMock()

            self.updater = SimpleNamespace(start_webhook=AsyncMock(side_effect=self._record),
                                           stop=AsyncMock())
            self.initialize = AsyncMock()
            self.start = AsyncMock()
            self.stop = AsyncMock()
            self.shutdown = AsyncMock()

        def add_handler(self, *args, **kwargs):
            pass

        async def _record(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(Application, "builder", lambda: SimpleNamespace(
        token=lambda token: SimpleNamespace(build=App)))
    return calls


def _run(calls, metadata=None):
    config = BotConfig(token="123:synthetic", webhook_url="https://bot.example.com",
                       metadata=metadata or {})

    async def go():
        bot = TelegramBot(token="123:synthetic", config=config)
        seen = len(calls)
        task = asyncio.create_task(bot.start())
        for _ in range(500):
            if len(calls) > seen or task.done():
                break
            await asyncio.sleep(0.01)
        await bot.stop()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(go())


def test_webhook_generates_secret_token_when_unset(webhook_app):
    _run(webhook_app)
    _run(webhook_app)
    first, second = (c["secret_token"] for c in webhook_app)
    assert first and set(first) <= _SAFE and 1 <= len(first) <= 256
    assert first != second  # fresh per run, never a shared constant
    # Existing listen/port/url behaviour is unchanged.
    assert webhook_app[0]["port"] == BotConfig(token="x").webhook_port  # configured port, not a fixed 8443
    assert webhook_app[0]["webhook_url"] == "https://bot.example.com/webhook"


def test_webhook_secret_from_env(webhook_app, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "env-secret_1")
    _run(webhook_app)
    assert webhook_app[0]["secret_token"] == "env-secret_1"


def test_webhook_secret_from_config_metadata_wins(webhook_app, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "env-secret_1")
    _run(webhook_app, {"webhook_secret": "cfg-secret_2"})
    assert webhook_app[0]["secret_token"] == "cfg-secret_2"


def test_webhook_listen_host_from_env(webhook_app, monkeypatch):
    monkeypatch.setenv("PRAISONAI_WEBHOOK_HOST", "127.0.0.1")
    _run(webhook_app)
    assert webhook_app[0]["listen"] == "127.0.0.1"
    monkeypatch.delenv("PRAISONAI_WEBHOOK_HOST")
    _run(webhook_app)
    assert webhook_app[1]["listen"] == "0.0.0.0"  # default unchanged; secret_token set
    assert webhook_app[1]["secret_token"]
