"""
Verify the portable presentation model is wired into the live delivery path.

Issue #2481: the typed presentation model + per-channel renderers existed but
had no call site. These tests assert the Telegram adapter implements
``SupportsPresentation`` (``render_presentation`` / ``presentation_limits`` /
``truncate_presentation``) and that the inbound handler consumes a captured
presentation and renders it natively after the text reply.
"""

import inspect

import pytest

pytest.importorskip("telegram")


def _make_bot():
    from praisonai.bots.telegram import TelegramBot
    from praisonaiagents.bots import BotConfig

    return TelegramBot(token="test", config=BotConfig(token="test"))


def _buttons_presentation():
    from praisonaiagents.bots.presentation import (
        MessagePresentation,
        PresentationBlock,
        PresentationButton,
        PresentationAction,
        ActionType,
    )

    return MessagePresentation(blocks=[
        PresentationBlock.make_text("Pick one"),
        PresentationBlock.make_buttons([
            PresentationButton(
                label="Yes",
                action=PresentationAction(type=ActionType.COMMAND, command="/yes"),
            ),
            PresentationButton(
                label="Docs",
                action=PresentationAction(
                    type=ActionType.URL, url="https://example.com"
                ),
            ),
        ]),
    ])


class TestTelegramSupportsPresentation:
    def test_adapter_exposes_protocol_methods(self):
        bot = _make_bot()
        assert hasattr(bot, "render_presentation")
        assert hasattr(bot, "presentation_limits")
        assert hasattr(bot, "truncate_presentation")

    def test_presentation_limits_are_telegram(self):
        bot = _make_bot()
        limits = bot.presentation_limits
        # Telegram caps buttons at 8 (see PresentationLimits.telegram()).
        assert limits.max_buttons == 8

    def test_truncate_returns_presentation(self):
        bot = _make_bot()
        adapted = bot.truncate_presentation(_buttons_presentation())
        from praisonaiagents.bots.presentation import MessagePresentation

        assert isinstance(adapted, MessagePresentation)

    @pytest.mark.asyncio
    async def test_render_presentation_sends_inline_keyboard(self):
        bot = _make_bot()

        sent = {}

        class _FakeBotAPI:
            async def send_message(self, **kwargs):
                sent.update(kwargs)

                class _Msg:
                    message_id = 42

                return _Msg()

        class _FakeApp:
            bot = _FakeBotAPI()

        bot._application = _FakeApp()

        message_id = await bot.render_presentation("123", _buttons_presentation())

        assert message_id == "42"
        assert sent["chat_id"] == 123
        # The portable buttons must reach the channel as a native inline keyboard.
        assert "reply_markup" in sent


class TestDeliveryPathWiring:
    def test_handler_consumes_last_presentation(self):
        """The inbound handler must pop and render the captured presentation."""
        from praisonai.bots.telegram import TelegramBot

        source = inspect.getsource(TelegramBot.start)
        assert "pop_last_presentation" in source
        assert "render_presentation" in source
