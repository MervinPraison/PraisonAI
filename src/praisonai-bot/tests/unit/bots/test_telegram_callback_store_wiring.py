"""Regression tests for Telegram callback-payload store wiring (issue #3312).

The core SDK can encode an overflowing ``reply``/``select`` value under a short
``@<ref>`` and resolve it back — but only when the *same* store is shared by the
render side and the inbound registry. These tests assert the production Telegram
renderer + registry actually share one store, so long option values (URLs, file
paths, IDs) round-trip losslessly past Telegram's 64-byte inline-callback cap
instead of being replaced by an unrecoverable hash.
"""

import asyncio

from praisonaiagents.bots import (
    InMemoryCallbackPayloadStore,
    InteractiveContext,
    MessagePresentation,
    PresentationBlock,
    PresentationButton,
    PresentationAction,
    SelectOption,
    create_registry,
)

from praisonai_bot.bots._presentation_renderer import TelegramPresentationRenderer


def _callback_data(rendered):
    return rendered["reply_markup"]["inline_keyboard"][0][0]["callback_data"]


def _roundtrip(callback_data, store):
    reg = create_registry(store=store)
    captured = {}

    async def handler(ctx):
        captured["value"] = ctx.platform_data["decoded_payload"]["value"]
        return "ok"

    for ns in ("select", "reply"):
        reg.register(ns, handler)
    ctx = InteractiveContext(callback_data=callback_data, user_id="u1")
    handled = asyncio.new_event_loop().run_until_complete(reg.dispatch(ctx))
    return handled, captured.get("value")


class TestTelegramCallbackStoreWiring:
    def test_long_select_value_roundtrips_via_shared_store(self):
        store = InMemoryCallbackPayloadStore()
        long_value = "https://example.com/download/" + "a" * 120
        pres = MessagePresentation(
            blocks=[
                PresentationBlock.make_select(
                    [SelectOption(label="Pick", value=long_value)],
                    action_id="menu",
                )
            ]
        )
        rendered = TelegramPresentationRenderer.render(pres, callback_store=store)
        cb = _callback_data(rendered)
        assert len(cb.encode("utf-8")) <= 64
        handled, value = _roundtrip(cb, store)
        assert handled is True
        assert value == f"menu:{long_value}"

    def test_long_reply_value_roundtrips_via_shared_store(self):
        store = InMemoryCallbackPayloadStore()
        long_value = "choose-" + "z" * 120
        pres = MessagePresentation(
            blocks=[
                PresentationBlock(
                    type="buttons",
                    buttons=[
                        PresentationButton(
                            label="Pick",
                            action=PresentationAction.reply(long_value),
                        )
                    ],
                )
            ]
        )
        rendered = TelegramPresentationRenderer.render(pres, callback_store=store)
        cb = _callback_data(rendered)
        assert len(cb.encode("utf-8")) <= 64
        handled, value = _roundtrip(cb, store)
        assert handled is True
        assert value == long_value

    def test_without_store_falls_back_to_hash(self):
        long_value = "https://example.com/" + "b" * 120
        pres = MessagePresentation(
            blocks=[
                PresentationBlock.make_select(
                    [SelectOption(label="Pick", value=long_value)],
                    action_id="menu",
                )
            ]
        )
        rendered = TelegramPresentationRenderer.render(pres)
        cb = _callback_data(rendered)
        assert len(cb.encode("utf-8")) <= 64
        assert "@" not in cb
