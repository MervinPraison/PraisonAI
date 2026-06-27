"""Issue #2372 — concrete outbound messenger wiring.

Verifies that ``BotOutboundMessenger`` binds the gateway's ``DeliveryRouter``
to the core ``OutboundMessengerProtocol`` and that ``BotSessionManager`` /
``BotOS`` register it so the built-in ``send_message`` tool can actually
deliver instead of returning "no gateway available".
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from praisonai.bots._outbound_messenger import BotOutboundMessenger
from praisonai.bots._session import BotSessionManager
from praisonai.bots.delivery import DeliveryRouter, SessionSource
from praisonaiagents.gateway import (
    OutboundMessengerProtocol,
    DeliveryResult,
    TargetInfo,
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


def test_send_with_missing_media_delivers_text_and_notes_skip():
    router, sent = _make_router()
    origin = SessionSource(platform="telegram", channel_id="123")
    messenger = BotOutboundMessenger(router, origin=origin)

    # A non-existent path is rejected by the delivery-path guard; text still
    # delivers and the skip is reported truthfully.
    result = asyncio.run(
        messenger.send("origin", "Report", media=["/tmp/does-not-exist-xyz.pdf"])
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
    assert uploaded[0] == ("123", str(f), "Here is your chart")
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
        from praisonai.bots import BotOS

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
        from praisonai.bots import BotOS, Bot

        os = BotOS()
        bot = Bot("telegram")
        # Simulate an already-built adapter exposing a session manager.
        session = BotSessionManager(platform="telegram")
        bot._adapter = MagicMock()
        bot._adapter._session = session
        os.add_bot(bot)

        os._wire_outbound_messenger()
        assert session._delivery_router is os._delivery_router
