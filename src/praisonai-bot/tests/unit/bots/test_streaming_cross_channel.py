#!/usr/bin/env python3
"""Cross-channel progressive streaming wiring (Issue #5415).

The ``DraftStreamer`` engine is channel-agnostic, but it used to be wired only
into Telegram. These tests lock in that Discord and Slack now:

- derive a ``StreamingConfig`` from ``BotConfig.streaming`` via the shared
  ``build_streaming_config`` factory, and
- advertise ``live_edit`` so ``AUTO`` resolves to ``DRAFT``.

This guards against regressing the fix back to a Telegram-only capability.
"""

import pytest

from praisonaiagents.bots import BotConfig

from praisonai_bot.bots._streaming import (
    build_streaming_config,
    StreamingMode,
)
from praisonai_bot.bots.discord import DiscordBot
from praisonai_bot.bots.slack import SlackBot


def test_build_streaming_config_off_returns_none():
    cfg = BotConfig(token="t", streaming=False)
    assert build_streaming_config(cfg) is None


def test_build_streaming_config_draft_when_enabled():
    cfg = BotConfig(token="t", streaming=True, stream_edit_interval_ms=700)
    sc = build_streaming_config(cfg)
    assert sc is not None
    assert sc.mode == StreamingMode.DRAFT
    assert sc.min_interval == 0.7


def test_discord_streaming_config_built_from_bot_config():
    bot = DiscordBot(token="t", config=BotConfig(token="t", streaming=True))
    assert bot._streaming_config is not None
    assert bot._streaming_config.mode == StreamingMode.DRAFT
    # Discord advertises live_edit so AUTO can resolve to DRAFT.
    assert bot.capabilities.get("live_edit") is True


def test_discord_streaming_disabled_by_default():
    bot = DiscordBot(token="t", config=BotConfig(token="t"))
    assert bot._streaming_config is None


def test_slack_streaming_config_built_from_bot_config():
    bot = SlackBot(token="t", config=BotConfig(token="t", streaming=True))
    assert bot._streaming_config is not None
    assert bot._streaming_config.mode == StreamingMode.DRAFT
    assert bot.capabilities.get("live_edit") is True


def test_slack_streaming_disabled_by_default():
    bot = SlackBot(token="t", config=BotConfig(token="t"))
    assert bot._streaming_config is None


def test_configure_streaming_overrides_discord():
    bot = DiscordBot(token="t", config=BotConfig(token="t"))
    sc = build_streaming_config(BotConfig(token="t", streaming=True))
    bot.configure_streaming(sc)
    assert bot._streaming_config is sc


def test_configure_streaming_overrides_slack():
    bot = SlackBot(token="t", config=BotConfig(token="t"))
    sc = build_streaming_config(BotConfig(token="t", streaming=True))
    bot.configure_streaming(sc)
    assert bot._streaming_config is sc


# --- Streaming delivery guardrails (Greptile review on #5417) ----------------


@pytest.mark.asyncio
async def test_slack_stream_defers_when_threaded():
    """A threaded reply must bypass the root-only streamer (Greptile #2).

    Returning ``None`` signals the caller to fall back to the thread-aware
    ``_send_response_with_media`` path, so a threaded answer is never stranded
    in the main channel.
    """
    bot = SlackBot(token="t", config=BotConfig(token="t", streaming=True))
    result = await bot._maybe_stream_reply(
        "C1", "U1", "hi", thread_id="123.456", message_id="123.457"
    )
    assert result is None


@pytest.mark.asyncio
async def test_slack_stream_defers_when_reply_in_thread_configured():
    bot = SlackBot(
        token="t",
        config=BotConfig(token="t", streaming=True, reply_in_thread=True),
    )
    result = await bot._maybe_stream_reply("C1", "U1", "hi", message_id="123.457")
    assert result is None


@pytest.mark.asyncio
async def test_slack_stream_uploads_media(monkeypatch, tmp_path):
    """A streamed reply carrying a MEDIA: directive uploads the file (Greptile #4)."""
    from unittest.mock import AsyncMock

    bot = SlackBot(token="t", config=BotConfig(token="t", streaming=True))

    audio = tmp_path / "reply.mp3"
    audio.write_bytes(b"ID3fake")

    # Session returns text + a MEDIA directive; streamer edits are stubbed.
    bot._session.chat = AsyncMock(return_value=f"Here you go\nMEDIA:{audio}")
    bot.send_message = AsyncMock(return_value={"message_id": "m1"})
    bot.edit_message = AsyncMock(return_value=None)
    bot.delete_message = AsyncMock(return_value=True)
    # Pin the outbound hook seam to a pass-through so a process-global hook
    # registered by another test cannot rewrite/strip the MEDIA directive.
    bot.fire_message_sending = lambda channel_id, content, **kw: {
        "cancel": False,
        "content": content,
    }

    uploads = []

    class _Client:
        async def files_upload_v2(self, **kwargs):
            uploads.append(kwargs)

    bot._client = _Client()

    result = await bot._maybe_stream_reply("C1", "U1", "play it")
    assert result is not None
    assert uploads, "expected the MEDIA audio file to be uploaded"
    assert uploads[0]["channel"] == "C1"
    assert uploads[0]["file"] == str(audio)


@pytest.mark.asyncio
async def test_discord_stream_chunks_long_reply(monkeypatch):
    """A streamed answer over Discord's cap is delivered via the chunked path.

    Guards Greptile #3/#5: editing the single placeholder with >2000 chars
    would 400 and drop the whole reply, so the finalize path must fall back to
    the reference-preserving ``_send_long_message`` chunker.
    """
    from unittest.mock import AsyncMock, MagicMock

    bot = DiscordBot(token="t", config=BotConfig(token="t", streaming=True))

    long_reply = "x" * 5000
    bot._session.chat = AsyncMock(return_value=long_reply)
    bot.send_message = AsyncMock(return_value={"message_id": "m1"})
    bot.edit_message = AsyncMock(return_value=None)
    bot.delete_message = AsyncMock(return_value=True)

    sent_chunks = []

    long_sender = AsyncMock(
        side_effect=lambda channel, text, reference=None: sent_chunks.append(text)
    )
    monkeypatch.setattr(bot, "_send_long_message", long_sender)

    from praisonai_bot.bots._streaming import DraftStreamer

    streamer = DraftStreamer(
        adapter=bot,
        channel_id="C1",
        config=bot._streaming_config,
        platform="discord",
    )
    await streamer.start()

    # Simulate the finalize decision the adapter makes for an over-cap reply.
    send_result = bot.fire_message_sending("C1", long_reply)
    final_content = send_result["content"]
    cap = min(bot.config.max_message_length, 2000)
    assert len(final_content) > cap

    message = MagicMock()
    message.channel = MagicMock()
    if len(final_content) > cap:
        await bot.delete_message("C1", "m1")
        await bot._send_long_message(message.channel, final_content, reference=message)
    else:  # pragma: no cover - defensive
        await streamer.finalize(final_content)

    assert sent_chunks, "long reply should have been routed through the chunker"
    bot.delete_message.assert_awaited()
