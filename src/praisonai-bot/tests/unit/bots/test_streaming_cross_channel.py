#!/usr/bin/env python3
"""Cross-channel progressive streaming wiring (Issue #5415).

The ``DraftStreamer`` engine is channel-agnostic, but it used to be wired only
into Telegram. These tests lock in that Discord and Slack now:

- derive a ``StreamingConfig`` from ``BotConfig.streaming`` via the shared
  ``build_streaming_config`` factory, and
- advertise ``live_edit`` so ``AUTO`` resolves to ``DRAFT``.

This guards against regressing the fix back to a Telegram-only capability.
"""

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
