"""Issue #2372 — concrete outbound messenger wiring.

Verifies that ``BotOutboundMessenger`` binds the gateway's ``DeliveryRouter``
to the core ``OutboundMessengerProtocol`` and that ``BotSessionManager`` /
``BotOS`` register it so the built-in ``send_message`` tool can actually
deliver instead of returning "no gateway available".
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from praisonai_bot.bots._outbound_messenger import BotOutboundMessenger
from praisonai_bot.bots._session import BotSessionManager
from praisonai_bot.bots.delivery import DeliveryRouter, SessionSource
from praisonaiagents.gateway import (
    OutboundMessengerProtocol,
    DeliveryResult,
    ReactionResult,
    TargetInfo,
    ThreadResult,
)
from praisonaiagents.session.context import (
    get_outbound_messenger,
    register_outbound_messenger,
    clear_outbound_messenger,
)


def _make_router(home=None, aliases=None):
    """Build a DeliveryRouter over a fake BotOS with one async-send bot."""
    sent = []

    class FakeBot:
        async def send_message(self, channel_id, text):
            sent.append((channel_id, text))

    fake_bot = FakeBot()

    class FakeBotOS:
        def get_bot(self, platform):
            return fake_bot if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    # Isolate from on-disk persisted directory state.
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}
    if home:
        router.directory.set_home_channel("telegram", home)
    for name, channel in (aliases or {}).items():
        router.directory.add_alias(name, "telegram", channel)
    return router, sent


def test_messenger_satisfies_protocol():
    router, _ = _make_router()
    messenger = BotOutboundMessenger(router)
    assert isinstance(messenger, OutboundMessengerProtocol)


def test_send_to_origin_delivers_to_origin_channel():
    router, sent = _make_router()
    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(messenger.send("origin", "Done"))

    assert isinstance(result, DeliveryResult)
    assert result.ok is True
    assert result.target == "telegram:123"
    assert sent == [("123", "Done")]


def test_send_to_platform_home_channel():
    router, sent = _make_router(home="999")
    messenger = BotOutboundMessenger(router)

    result = asyncio.run(messenger.send("telegram", "Nightly summary"))

    assert result.ok is True
    assert result.target == "telegram:999"
    assert sent == [("999", "Nightly summary")]


def test_send_unresolvable_target_fails_cleanly():
    router, sent = _make_router()
    messenger = BotOutboundMessenger(router)  # no origin

    result = asyncio.run(messenger.send("origin", "hi"))

    assert result.ok is False
    assert "Failed to send" in result.summary
    assert sent == []


def test_send_with_missing_media_delivers_text_and_notes_skip(tmp_path):
    router, sent = _make_router()
    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    # A non-existent path is rejected by the delivery-path guard; text still
    # delivers and the skip is reported truthfully.
    missing = tmp_path / "does-not-exist-xyz.pdf"
    result = asyncio.run(
        messenger.send("origin", "Report", media=[str(missing)])
    )

    assert result.ok is True
    assert sent == [("123", "Report")]
    assert "media not attached" in result.summary.lower()
    assert "not found" in (result.detail or "").lower()


def test_send_with_valid_media_uploads_via_adapter(tmp_path):
    # FakeBot exposes a send_media hook so the router can dispatch the upload.
    uploaded = []

    class FakeBot:
        platform = "telegram"

        async def send_message(self, channel_id, text):
            pass

        async def send_media(self, channel_id, path, caption=None):
            uploaded.append((channel_id, path, caption))

    fake_bot = FakeBot()

    class FakeBotOS:
        def get_bot(self, platform):
            return fake_bot if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}

    f = tmp_path / "chart.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(
        messenger.send("origin", "Here is your chart", media=[str(f)])
    )

    assert result.ok is True
    assert len(uploaded) == 1
    # The body text is delivered once via send_message; the attachment is sent
    # without re-captioning the full text (caption is None) to avoid duplicates.
    assert uploaded[0] == ("123", str(f), None)
    assert "1 attachment(s) delivered" in result.summary


def test_duplicate_idempotency_key_suppresses_text_and_media(tmp_path):
    # Issue #2578: a re-fired proactive send with the same idempotency_key must
    # skip BOTH the text and the media upload — otherwise the attachment would
    # be re-uploaded even though the text was deduplicated.
    uploaded = []
    sent = []

    class FakeBot:
        platform = "telegram"

        async def send_message(self, channel_id, text):
            sent.append((channel_id, text))

        async def send_media(self, channel_id, path, caption=None):
            uploaded.append((channel_id, path, caption))

    fake_bot = FakeBot()

    class FakeBotOS:
        def get_bot(self, platform):
            return fake_bot if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}

    f = tmp_path / "chart.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    r1 = asyncio.run(
        messenger.send("origin", "Report", media=[str(f)], idempotency_key="job-1")
    )
    r2 = asyncio.run(
        messenger.send("origin", "Report", media=[str(f)], idempotency_key="job-1")
    )

    assert r1.ok is True and r2.ok is True  # both report success
    assert sent == [("123", "Report")]  # text sent exactly once
    assert uploaded == [("123", str(f), None)]  # media uploaded exactly once
    assert "duplicate suppressed" in r2.summary.lower()


def test_failed_send_does_not_record_idempotency_key(tmp_path):
    # A failed send must not record the key, so a legitimate retry still sends.
    sent = []

    class FakeBot:
        platform = "telegram"
        fail = True

        async def send_message(self, channel_id, text):
            if self.fail:
                raise RuntimeError("transport down")
            sent.append((channel_id, text))

    fake_bot = FakeBot()

    class FakeBotOS:
        def get_bot(self, platform):
            return fake_bot if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}

    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    r1 = asyncio.run(messenger.send("origin", "hi", idempotency_key="job-x"))
    assert r1.ok is False

    fake_bot.fail = False  # transport recovers
    r2 = asyncio.run(messenger.send("origin", "hi", idempotency_key="job-x"))
    assert r2.ok is True
    assert sent == [("123", "hi")]  # retry reached the platform


def test_send_media_unwraps_bot_wrapper_to_adapter(tmp_path):
    # get_bot returns the Bot wrapper; the upload primitive lives on the
    # underlying adapter. The router must unwrap via ``.adapter`` so real
    # Telegram/Slack/Discord attachments are not silently skipped.
    uploaded = []

    class FakeAdapter:
        platform = "telegram"

        async def send_media(self, channel_id, path, caption=None):
            uploaded.append((channel_id, path, caption))

    class FakeWrapper:
        # Mirrors praisonai.bots.bot.Bot: exposes text send + `.adapter`.
        adapter = FakeAdapter()

        async def send_message(self, channel_id, text):
            pass

    wrapper = FakeWrapper()

    class FakeBotOS:
        def get_bot(self, platform):
            return wrapper if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}

    f = tmp_path / "chart.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(
        messenger.send("origin", "Here is your chart", media=[str(f)])
    )

    assert result.ok is True
    assert uploaded == [("123", str(f), None)]
    assert "1 attachment(s) delivered" in result.summary


def test_list_targets_includes_origin_and_directory():
    router, _ = _make_router(home="999", aliases={"ops": "555"})
    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    targets = messenger.list_targets()

    assert all(isinstance(t, TargetInfo) for t in targets)
    tokens = {t.target for t in targets}
    assert "origin" in tokens
    assert "telegram" in tokens  # home channel addressed by platform name
    assert "ops" in tokens  # alias addressed by friendly name


def _make_reaction_router(*, reactions=True, react_ok=True):
    """Build a DeliveryRouter over a fake bot with reaction primitives (#3917).

    The reaction primitives live on an ``.adapter`` so the router's unwrap path
    is exercised, matching real Telegram/Slack/Discord adapters.
    """
    calls = []

    class FakeAdapter:
        platform = "telegram"

        def __init__(self, reactions, react_ok):
            self.capabilities = {"reactions": reactions}
            self._react_ok = react_ok

        async def add_reaction(self, channel_id, message_id, emoji):
            calls.append(("add", channel_id, message_id, emoji))
            return self._react_ok

        async def remove_reaction(self, channel_id, message_id, emoji):
            calls.append(("remove", channel_id, message_id, emoji))
            return self._react_ok

    class FakeWrapper:
        def __init__(self, reactions, react_ok):
            self.adapter = FakeAdapter(reactions, react_ok)

        async def send_message(self, channel_id, text):
            pass

    wrapper = FakeWrapper(reactions, react_ok)

    class FakeBotOS:
        def get_bot(self, platform):
            return wrapper if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}
    return router, calls


def test_react_on_origin_uses_inbound_message_id():
    router, calls = _make_reaction_router()
    origin = SessionSource(platform="telegram", channel_id="123", message_id="17")
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(messenger.react("origin", "\U0001F44D"))

    assert isinstance(result, ReactionResult)
    assert result.status == "ok"
    assert result.target == "telegram:123"
    assert calls == [("add", "123", "17", "\U0001F44D")]


def test_unreact_dispatches_remove():
    router, calls = _make_reaction_router()
    origin = SessionSource(platform="telegram", channel_id="123", message_id="17")
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(messenger.react("origin", "\u2705", remove=True))

    assert result.status == "ok"
    assert calls == [("remove", "123", "17", "\u2705")]


def test_react_unsupported_channel_returns_typed_outcome():
    router, calls = _make_reaction_router(reactions=False)
    origin = SessionSource(platform="telegram", channel_id="123", message_id="17")
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(messenger.react("origin", "\U0001F44D"))

    assert result.status == "unsupported"
    assert "reactions capability" in (result.detail or "")
    assert calls == []  # never dispatched to the adapter


def test_react_without_message_id_fails_cleanly():
    router, calls = _make_reaction_router()
    origin = SessionSource(platform="telegram", channel_id="123")  # no message_id
    messenger = BotOutboundMessenger(router, origin=origin)

    result = asyncio.run(messenger.react("origin", "\U0001F44D"))

    assert result.status == "failed"
    assert calls == []


def test_react_unresolvable_target_returns_no_route():
    router, calls = _make_reaction_router()
    messenger = BotOutboundMessenger(router)  # no origin

    result = asyncio.run(messenger.react("origin", "\U0001F44D", message_id="17"))

    assert result.status == "no_route"
    assert calls == []


def test_react_explicit_target_and_message_id():
    router, calls = _make_reaction_router()
    messenger = BotOutboundMessenger(router)

    result = asyncio.run(
        messenger.react("telegram:456", "\U0001F389", message_id="88")
    )

    assert result.status == "ok"
    assert result.target == "telegram:456"
    assert calls == [("add", "456", "88", "\U0001F389")]


def test_messenger_still_satisfies_protocol_with_react():
    router, _ = _make_reaction_router()
    messenger = BotOutboundMessenger(router)
    assert isinstance(messenger, OutboundMessengerProtocol)


def _make_thread_router(*, threads=True, thread_id="T99"):
    """Build a DeliveryRouter over a fake bot with a create_thread primitive (#3987).

    The thread primitive lives on an ``.adapter`` so the router's unwrap path is
    exercised, matching real Telegram/Slack/Discord adapters.
    """
    calls = []

    class FakeAdapter:
        platform = "telegram"

        def __init__(self, threads, thread_id):
            self.capabilities = {"threads": threads}
            self._thread_id = thread_id

        async def create_thread(self, channel_id, name):
            calls.append((channel_id, name))
            return self._thread_id

    class FakeWrapper:
        def __init__(self, threads, thread_id):
            self.adapter = FakeAdapter(threads, thread_id)

        async def send_message(self, channel_id, text):
            pass

    wrapper = FakeWrapper(threads, thread_id)

    class FakeBotOS:
        def get_bot(self, platform):
            return wrapper if platform == "telegram" else None

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}
    return router, calls


def test_create_thread_ok_returns_thread_id():
    router, calls = _make_thread_router(thread_id="T123")
    messenger = BotOutboundMessenger(router)

    result = asyncio.run(messenger.create_thread("telegram:456", "research"))

    assert isinstance(result, ThreadResult)
    assert result.status == "ok"
    assert result.ok is True
    assert result.target == "telegram:456"
    assert result.thread_id == "T123"
    assert calls == [("456", "research")]


def test_create_thread_unsupported_channel_returns_typed_outcome():
    router, calls = _make_thread_router(threads=False)
    messenger = BotOutboundMessenger(router)

    result = asyncio.run(messenger.create_thread("telegram:456", "research"))

    assert result.status == "unsupported"
    assert result.ok is False
    assert result.thread_id == ""
    assert "threads capability" in (result.detail or "")
    assert calls == []  # never dispatched to the adapter


def test_create_thread_unresolvable_target_returns_no_route():
    router, calls = _make_thread_router()
    messenger = BotOutboundMessenger(router)  # no origin

    result = asyncio.run(messenger.create_thread("origin", "research"))

    assert result.status == "no_route"
    assert result.thread_id == ""
    assert calls == []


def test_create_thread_empty_id_reports_failed():
    router, calls = _make_thread_router(thread_id="")
    messenger = BotOutboundMessenger(router)

    result = asyncio.run(messenger.create_thread("telegram:456", "research"))

    assert result.status == "failed"
    assert result.thread_id == ""
    assert calls == [("456", "research")]


def test_messenger_still_satisfies_protocol_with_create_thread():
    router, _ = _make_thread_router()
    messenger = BotOutboundMessenger(router)
    assert isinstance(messenger, OutboundMessengerProtocol)


class TestSessionManagerRegistration:
    """BotSessionManager registers/clears the messenger per turn (#2372)."""

    def _agent(self):
        agent = MagicMock(name="agent")
        agent.name = "Test"
        agent.chat_history = []

        captured = {}

        def fake_chat(prompt, *args, **kwargs):
            captured["messenger"] = get_outbound_messenger()
            return "ok"

        agent.chat.side_effect = fake_chat
        return agent, captured

    def test_messenger_registered_during_turn_and_cleared_after(self):
        router, sent = _make_router()
        agent, captured = self._agent()
        mgr = BotSessionManager(platform="telegram", delivery_router=router)

        out = asyncio.run(
            mgr.chat(agent, user_id="u1", prompt="hi", chat_id="123")
        )

        assert out == "ok"
        # A concrete messenger was visible to tools during the turn...
        assert isinstance(captured["messenger"], BotOutboundMessenger)
        # ...and is cleared once the turn ends (no leak).
        assert get_outbound_messenger() is None

    def test_no_router_means_no_messenger(self):
        agent, captured = self._agent()
        mgr = BotSessionManager(platform="telegram")  # no delivery_router

        asyncio.run(mgr.chat(agent, user_id="u1", prompt="hi", chat_id="123"))

        assert captured["messenger"] is None

    def test_registered_messenger_resolves_origin_to_chat(self):
        router, sent = _make_router()
        captured = {}

        async def run():
            origin = SessionSource(platform="telegram", channel_id="123")
            messenger = BotOutboundMessenger(router, origin=origin)
            token = register_outbound_messenger(messenger)
            try:
                captured["result"] = await get_outbound_messenger().send(
                    "origin", "via-turn"
                )
            finally:
                clear_outbound_messenger(token)

        asyncio.run(run())
        assert captured["result"].ok is True
        assert sent == [("123", "via-turn")]


class TestBotOSWiring:
    def test_botos_stamps_router_onto_bot_for_lazy_adapter(self):
        from praisonai_bot.bots import BotOS

        agent = MagicMock(name="agent")
        agent.name = "Test"
        agent.chat_history = []

        os = BotOS(agent=agent, platforms=["telegram"])
        bot = os.get_bot("telegram")
        # Adapter (and its session) is built lazily in start(); the router is
        # stamped on the Bot so _build_adapter can splice it into the session.
        assert bot._delivery_router is None
        os._wire_outbound_messenger()
        assert bot._delivery_router is os._delivery_router

    def test_botos_wires_existing_session_in_place(self):
        from praisonai_bot.bots import BotOS, Bot

        os = BotOS()
        bot = Bot("telegram")
        # Simulate an already-built adapter exposing a session manager.
        session = BotSessionManager(platform="telegram")
        bot._adapter = MagicMock()
        bot._adapter._session = session
        os.add_bot(bot)

        os._wire_outbound_messenger()
        assert session._delivery_router is os._delivery_router
