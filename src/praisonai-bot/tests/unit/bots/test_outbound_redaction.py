#!/usr/bin/env python3
"""Outbound secret/PII redaction on the gateway reply path (Issue #5055).

The gateway must never deliver a registered secret or a credential-shaped token
to a chat user. These tests exercise the three wrapper seams that cover every
outbound path:

* ``MessageHookMixin.fire_message_sending`` — the single reply decision point
  every adapter funnels through.
* ``DraftStreamer`` — the streaming/progressive-edit path (which does not pass
  through ``fire_message_sending`` for intermediate edits).
* ``DeliveryRouter.deliver`` — the proactive/scheduled ``send_message`` path.
"""

import asyncio
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-bot"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.secrets import register_secret_for_redaction
from praisonai_bot.bots._protocol_mixin import MessageHookMixin
from praisonai_bot.bots._streaming import (
    DraftStreamer,
    StreamingConfig,
    StreamingMode,
)
from praisonai_bot.bots.delivery import DeliveryRouter


# ── fire_message_sending seam ─────────────────────────────────────────────


class _FakeBot(MessageHookMixin):
    platform = "telegram"

    def _get_hook_runner(self):
        return None


def test_fire_message_sending_masks_registered_secret():
    register_secret_for_redaction("sk-fire-registered-9999")
    bot = _FakeBot()
    res = bot.fire_message_sending("chan", "key sk-fire-registered-9999 done")
    assert res["content"] == "key [REDACTED] done"
    assert res["cancel"] is False


def test_fire_message_sending_masks_unregistered_credential_shape():
    bot = _FakeBot()
    res = bot.fire_message_sending("chan", "id AKIAIOSFODNN7EXAMPLE here")
    assert "AKIA" not in res["content"]
    assert "[REDACTED]" in res["content"]


def test_fire_message_sending_leaves_ordinary_text_unchanged():
    bot = _FakeBot()
    text = "See you at 3pm in room 42."
    assert bot.fire_message_sending("chan", text)["content"] == text


def test_fire_message_sending_opt_out_disables_redaction():
    register_secret_for_redaction("sk-fire-optout-9999")
    bot = _FakeBot()
    bot._redact_secrets_outbound = False
    res = bot.fire_message_sending("chan", "key sk-fire-optout-9999 done")
    assert res["content"] == "key sk-fire-optout-9999 done"


# ── DraftStreamer seam ────────────────────────────────────────────────────


class _FakeAdapter:
    capabilities = {"live_edit": True}

    def __init__(self):
        self.edits = []
        self.sends = []

    async def send_message(self, channel_id, content):
        self.sends.append(content)
        return {"message_id": "1"}

    async def edit_message(self, channel_id, message_id, content):
        self.edits.append(content)
        return True


def test_streamer_render_scrubs_progressive_draft():
    async def run():
        adapter = _FakeAdapter()
        cfg = StreamingConfig(mode=StreamingMode.DRAFT, min_interval=0, min_delta=0)
        streamer = DraftStreamer(adapter, "chan", cfg)
        await streamer.start()
        streamer._content_buffer = "leaking AKIAIOSFODNN7EXAMPLE now"
        rendered = streamer._render_content()
        assert "AKIA" not in rendered
        assert "[REDACTED]" in rendered

    asyncio.run(run())


def test_streamer_finalize_scrubs_final_content():
    async def run():
        adapter = _FakeAdapter()
        cfg = StreamingConfig(mode=StreamingMode.DRAFT, min_interval=0, min_delta=0)
        streamer = DraftStreamer(adapter, "chan", cfg)
        await streamer.start()
        await streamer.finalize("final AKIAIOSFODNN7EXAMPLE end")
        # finalize edits the placeholder in place with the scrubbed final answer.
        delivered = adapter.edits[-1]
        assert "AKIA" not in delivered
        assert "[REDACTED]" in delivered

    asyncio.run(run())


# ── DeliveryRouter seam ───────────────────────────────────────────────────


class _RouterBot:
    def __init__(self):
        self.last = None

    async def send_message(self, channel_id, text, **kwargs):
        self.last = text
        return {"message_id": "1"}


class _FakeBotOS:
    def __init__(self, bot):
        self._bot = bot

    def get_bot(self, platform):
        return self._bot

    def list_bots(self):
        return ["telegram"]


def _bare_router(bot):
    """A DeliveryRouter without touching disk (no ChannelDirectory load)."""
    router = DeliveryRouter.__new__(DeliveryRouter)
    router._botos = _FakeBotOS(bot)
    router._notify_on_undelivered = False
    router._undelivered_template = ""
    router._dead_targets = None
    router._rate_limiters = {}
    router._seen_keys = OrderedDict()
    router._seen_keys_max = 10
    router._idempotency_store = None
    return router


def test_delivery_router_scrubs_before_dispatch():
    async def run():
        bot = _RouterBot()
        router = _bare_router(bot)
        ok = await router.deliver("telegram:123", "reply AKIAIOSFODNN7EXAMPLE done")
        assert ok is True
        assert "AKIA" not in bot.last
        assert "[REDACTED]" in bot.last

    asyncio.run(run())


def test_delivery_router_leaves_ordinary_text_unchanged():
    async def run():
        bot = _RouterBot()
        router = _bare_router(bot)
        ok = await router.deliver("telegram:123", "meeting at 3pm room 42")
        assert ok is True
        assert bot.last == "meeting at 3pm room 42"

    asyncio.run(run())
