"""Gateway Telegram channel parity with the standalone adapter (Issue #6032).

The gateway wires Telegram through ``WebSocketGateway._start_telegram_bot_polling``
rather than ``TelegramBot.start()``. These tests check that it registers the
adapter's ``CallbackQueryHandler`` (so pairing / tool-approval taps resolve
without a second ``getUpdates`` poller), auto-wires the durable approval
backend, and passes ``chat_id``/``message_id``/``account`` to the session.

``python-telegram-bot`` is faked via ``sys.modules`` — no network.
"""

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonaiagents.bots import BotConfig
from praisonai_bot.bots.telegram import TelegramBot
from praisonai_bot.bots._presentation_approval_backend import (
    PresentationApprovalBackend,
)
from praisonai_bot.gateway.server import WebSocketGateway


class _Filter:
    def __and__(self, other):
        return _Filter()

    __or__ = __and__

    def __invert__(self):
        return _Filter()


class _Handler:
    def __init__(self, *args, block=True):
        self.args = args
        self.callback = args[-1]
        self.block = block


class CommandHandler(_Handler):
    pass


class MessageHandler(_Handler):
    pass


class CallbackQueryHandler(_Handler):
    pass


class _FakeApp:
    def __init__(self):
        self.handlers = []
        self.bot = SimpleNamespace(
            get_me=AsyncMock(
                return_value=SimpleNamespace(id=1, username="demo_bot", first_name="Demo")
            )
        )
        self.updater = SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock())
        self.initialize = AsyncMock()
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.shutdown = AsyncMock()

    def add_handler(self, handler, *args, **kwargs):
        self.handlers.append(handler)


@pytest.fixture
def fake_ptb(monkeypatch):
    app = _FakeApp()
    builder = SimpleNamespace()
    builder.token = lambda _t: builder
    builder.build = lambda: app

    tg = types.ModuleType("telegram")
    tg.Update = object
    ext = types.ModuleType("telegram.ext")
    ext.Application = SimpleNamespace(builder=lambda: builder)
    ext.CommandHandler = CommandHandler
    ext.MessageHandler = MessageHandler
    ext.CallbackQueryHandler = CallbackQueryHandler
    ext.filters = SimpleNamespace(
        TEXT=_Filter(), COMMAND=_Filter(), VOICE=_Filter(), AUDIO=_Filter()
    )
    tg.ext = ext
    monkeypatch.setitem(sys.modules, "telegram", tg)
    monkeypatch.setitem(sys.modules, "telegram.ext", ext)
    return app


def _gateway():
    return SimpleNamespace(
        _determine_routing_context=lambda *a, **k: {},
        _build_route_facts=lambda *a, **k: {},
        _resolve_agent_for_message=lambda *a, **k: None,
        _resolve_tool_policy_for_message=lambda *a, **k: None,
        _resolve_profile_for_message=lambda *a, **k: None,
    )


async def _start(bot, gateway=None):
    task = asyncio.create_task(
        WebSocketGateway._start_telegram_bot_polling(gateway or _gateway(), "telegram", bot)
    )
    for _ in range(50):
        await asyncio.sleep(0.01)
        if bot._is_running:
            break
    return task


async def _stop(task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_gateway_registers_adapter_callback_handler_and_wires_backend(fake_ptb):
    async def run():
        bot = TelegramBot(token="123:abc", config=BotConfig(token="123:abc"))
        backend = PresentationApprovalBackend(allowed_actors={"999"}, target="999")
        bot._agent = SimpleNamespace(_approval_backend=backend)
        task = await _start(bot)
        try:
            return bot, backend
        finally:
            await _stop(task)

    bot, backend = asyncio.run(run())
    callbacks = [h for h in fake_ptb.handlers if isinstance(h, CallbackQueryHandler)]
    assert len(callbacks) == 1
    assert callbacks[0].callback == bot._handle_callback_query
    # Durable backend is wired to this adapter: it renders via the adapter and
    # taps resolve through the adapter's own callback path (no self-polling).
    assert bot._approval_backend is backend
    assert backend._channel_send_func == bot.render_presentation


def test_gateway_tool_approval_tap_resolves_pending_approval(fake_ptb):
    async def run():
        bot = TelegramBot(token="123:abc", config=BotConfig(token="123:abc"))
        backend = MagicMock()
        backend.handle_callback = AsyncMock(return_value=True)
        bot._approval_backend = backend
        task = await _start(bot)
        try:
            handler = next(
                h for h in fake_ptb.handlers if isinstance(h, CallbackQueryHandler)
            )
            query = MagicMock()
            query.data = "cmd:/approve abc123 allow"
            query.from_user.id = 999
            query.message.message_id = 5
            query.message.chat_id = 999
            query.message.text = "Tool Approval Required"
            query.answer = AsyncMock()
            query.edit_message_text = AsyncMock()
            await handler.callback(SimpleNamespace(callback_query=query), None)
        finally:
            await _stop(task)
        return backend

    backend = asyncio.run(run())
    backend.handle_callback.assert_awaited_once_with("abc123", "allow", actor="999")


def test_gateway_session_chat_receives_chat_and_message_ids(fake_ptb, monkeypatch):
    import praisonai_bot.bots.telegram as tg_mod

    inbound = SimpleNamespace(
        sender=SimpleNamespace(user_id="777"), content="hello bot", thread_id=None
    )
    monkeypatch.setattr(
        tg_mod, "process_inbound_telegram_message", AsyncMock(return_value=inbound)
    )

    async def run():
        bot = TelegramBot(
            token="123:abc", config=BotConfig(token="123:abc", typing_indicator=False)
        )
        bot._session = MagicMock()
        bot._session.chat = AsyncMock(return_value="hi")
        bot._ack = SimpleNamespace(enabled=False)
        bot._debouncer = SimpleNamespace(debounce=AsyncMock(side_effect=lambda u, t: t))
        bot._send_response_with_media = AsyncMock()
        bot._agent = object()
        task = await _start(bot)
        try:
            handler = next(
                h
                for h in fake_ptb.handlers
                if isinstance(h, MessageHandler) and h.callback.__name__ == "handle_message"
            )
            message = MagicMock(voice=None, audio=None, chat_id=4242, message_id=7)
            message.chat.type = "private"
            message.chat.id = 4242
            await handler.callback(SimpleNamespace(message=message), None)
        finally:
            await _stop(task)
        return bot

    bot = asyncio.run(run())
    kwargs = bot._session.chat.await_args.kwargs
    assert kwargs["chat_id"] == "4242"
    assert kwargs["message_id"] == "7"
    assert kwargs["account"] == getattr(bot.config, "account", "default")


def test_gateway_message_handlers_do_not_block_approval_taps(fake_ptb):
    """A turn awaiting tool approval must not stall dispatch of the tap."""
    async def run():
        bot = TelegramBot(token="123:abc", config=BotConfig(token="123:abc"))
        task = await _start(bot)
        await _stop(task)

    asyncio.run(run())
    turn_handlers = [
        h for h in fake_ptb.handlers
        if isinstance(h, MessageHandler)
        and h.callback.__name__ in ("handle_message", "handle_voice")
    ]
    assert len(turn_handlers) == 2
    assert all(h.block is False for h in turn_handlers)


def test_gateway_new_resets_per_chat_session(fake_ptb, monkeypatch):
    import praisonai_bot.bots.telegram as tg_mod

    inbound = SimpleNamespace(sender=SimpleNamespace(user_id="777"))
    monkeypatch.setattr(
        tg_mod, "process_inbound_telegram_message", AsyncMock(return_value=inbound)
    )

    async def run():
        bot = TelegramBot(token="123:abc", config=BotConfig(token="123:abc"))
        bot._session = MagicMock()
        task = await _start(bot)
        try:
            handler = next(
                h for h in fake_ptb.handlers
                if isinstance(h, CommandHandler) and h.args[0] == "new"
            )
            message = MagicMock(chat_id=-100555)
            message.reply_text = AsyncMock()
            await handler.callback(SimpleNamespace(message=message), None)
        finally:
            await _stop(task)
        return bot

    bot = asyncio.run(run())
    bot._session.reset.assert_called_once_with(
        "777",
        account=getattr(bot.config, "account", "default"),
        chat_id="-100555",
    )
