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
                if isinstance(h, CommandHandler) and h.args[0] == "new" and h.block is False
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


def _routed_shell(monkeypatch, own, shared):
    import praisonai_bot.bots._defaults as defaults

    monkeypatch.setattr(defaults, "apply_bot_smart_defaults", lambda a, c: a)
    monkeypatch.setattr(defaults, "_sync_approval_registry", lambda a: None)

    def _enable(clone, *a, **k):
        clone._approval_backend = own
        return clone

    monkeypatch.setattr(defaults, "enable_shell_tools", _enable)
    gw = SimpleNamespace(
        _channel_shell_cfg={"telegram": (object(), {"platform": "telegram"})},
        _shell_routed_agents={},
        _resolve_gateway_bind_host=lambda: "127.0.0.1",
        _channel_bots={"telegram": SimpleNamespace(_approval_backend=shared)},
    )
    return WebSocketGateway._apply_channel_shell(gw, "telegram", SimpleNamespace())


def test_routed_shell_reuses_channel_backend_when_approvers_match(monkeypatch):
    own = PresentationApprovalBackend(allowed_actors={"999"}, target="42")
    shared = PresentationApprovalBackend(allowed_actors={"999"}, target="42")
    assert _routed_shell(monkeypatch, own, shared)._approval_backend is shared


@pytest.mark.parametrize(
    "shared",
    [
        # Broader approver set than the route asks for.
        PresentationApprovalBackend(allowed_actors={"999", "111"}, target="42"),
        # Any actor, while the route restricts approvers.
        PresentationApprovalBackend(allowed_actors=None, target="42"),
        # Different approval chat.
        PresentationApprovalBackend(allowed_actors={"999"}, target="7"),
        # Not a durable presentation backend.
        SimpleNamespace(handle_callback=AsyncMock()),
    ],
)
def test_routed_shell_keeps_own_backend_when_channel_backend_is_looser(
    monkeypatch, shared
):
    own = PresentationApprovalBackend(allowed_actors={"999"}, target="42")
    assert _routed_shell(monkeypatch, own, shared)._approval_backend is own


def test_gateway_concurrent_turns_run_one_at_a_time_while_taps_dispatch(
    fake_ptb, monkeypatch
):
    """block=False turns must not interleave (profile, debounce, reset)."""
    import praisonai_bot.bots.telegram as tg_mod

    inbound = SimpleNamespace(
        sender=SimpleNamespace(user_id="777"), content="hi", thread_id=None
    )
    monkeypatch.setattr(
        tg_mod, "process_inbound_telegram_message", AsyncMock(return_value=inbound)
    )
    events = []
    approved = asyncio.Event()
    profiles = {"1": "tenant-a", "2": "tenant-b"}

    async def run():
        bot = TelegramBot(
            token="123:abc", config=BotConfig(token="123:abc", typing_indicator=False)
        )
        session = MagicMock()
        staged = {}
        session.set_profile_namespace = lambda ns, agent: staged.update(ns=ns)

        async def chat(agent, user_id, text, **kw):
            events.append(("start", kw["chat_id"], staged["ns"]))
            if kw["chat_id"] == "1":
                await approved.wait()  # turn waits on a tool approval
            events.append(("end", kw["chat_id"], staged["ns"]))
            return "ok"

        session.chat = chat
        session.reset = lambda *a, **k: events.append(("reset", k["chat_id"]))
        bot._session = session
        bot._ack = SimpleNamespace(enabled=False)
        bot._debouncer = SimpleNamespace(debounce=AsyncMock(side_effect=lambda u, t: t))
        bot._send_response_with_media = AsyncMock()
        bot._agent = object()

        async def tap(update, context):
            events.append(("tap",))
            approved.set()

        bot._handle_callback_query = tap
        gw = _gateway()
        gw._resolve_profile_for_message = lambda ch, facts: profiles[facts["c"]]
        gw._build_route_facts = lambda *a, channel_id=None, **k: {"c": channel_id}
        task = await _start(bot, gw)
        try:
            by_name = {h.callback.__name__: h for h in fake_ptb.handlers}

            def msg(chat):
                m = MagicMock(voice=None, audio=None, chat_id=int(chat), message_id=1)
                m.chat.type = "private"
                m.chat.id = int(chat)
                m.reply_text = AsyncMock()
                return SimpleNamespace(message=m)

            # PTB schedules block=False handlers as tasks in update order.
            t1 = asyncio.create_task(by_name["handle_message"].callback(msg("1"), None))
            await asyncio.sleep(0.01)
            t2 = asyncio.create_task(by_name["handle_message"].callback(msg("2"), None))
            t3 = asyncio.create_task(by_name["handle_new"].callback(msg("1"), None))
            await asyncio.sleep(0.01)
            assert events == [("start", "1", "tenant-a")]
            # Blocking callback handler still runs while turn 1 waits.
            await by_name["tap"].callback(SimpleNamespace(), None)
            await asyncio.wait_for(asyncio.gather(t1, t2, t3), 2)
        finally:
            await _stop(task)

    asyncio.run(run())
    assert events == [
        ("start", "1", "tenant-a"),
        ("tap",),
        ("end", "1", "tenant-a"),
        ("start", "2", "tenant-b"),
        ("end", "2", "tenant-b"),
        ("reset", "1"),
    ]
