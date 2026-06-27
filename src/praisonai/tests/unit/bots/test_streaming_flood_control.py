#!/usr/bin/env python3
"""
Tests for DraftStreamer flood-control backoff and reasoning-tag filtering.

Covers issue #2351:
- Edit failures (flood/429) adaptively widen the interval and, after a small
  number of consecutive failures, disable progressive edits in favour of a
  single final send.
- ``<think>``/``<reasoning>`` spans are stripped from streamed output.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock

from praisonai.bots._streaming import (
    DraftStreamer,
    StreamingConfig,
    StreamingMode,
    strip_reasoning_tags,
)


class FloodError(Exception):
    """Simulated Telegram flood / 429 error."""

    def __init__(self):
        self.status_code = 429
        super().__init__("429 Too Many Requests: retry after 5")


class PermanentError(Exception):
    """Simulated non-recoverable error."""

    def __init__(self):
        super().__init__("Bad Request: message text is invalid")


def _make_adapter(edit_side_effect=None):
    adapter = AsyncMock()
    adapter.capabilities = {}
    adapter.send_message = AsyncMock(return_value={"message_id": "m1"})
    adapter.edit_message = AsyncMock(side_effect=edit_side_effect)
    return adapter


def test_strip_complete_blocks():
    assert strip_reasoning_tags("Hi <think>secret</think> there") == "Hi  there"
    assert strip_reasoning_tags("A <reasoning>x\ny</reasoning> B") == "A  B"


def test_strip_case_insensitive_and_attrs():
    assert strip_reasoning_tags("a <THINK foo='1'>x</THINK> b") == "a  b"


def test_strip_trailing_unclosed_block():
    # Internal reasoning still streaming must not leak
    assert strip_reasoning_tags("Answer <think>still going") == "Answer "


def test_strip_no_tags_passthrough():
    assert strip_reasoning_tags("plain text") == "plain text"
    assert strip_reasoning_tags("") == ""


def test_config_from_dict_defaults_and_overrides():
    cfg = StreamingConfig.from_dict({"mode": "draft"})
    assert cfg.disable_progressive_edits_after == 3
    assert cfg.flood_backoff_factor == 2.0
    assert cfg.strip_reasoning_tags is True

    cfg2 = StreamingConfig.from_dict(
        {
            "mode": "draft",
            "disable_progressive_edits_after": 2,
            "flood_backoff_factor": 3.0,
            "max_interval": 10.0,
            "strip_reasoning_tags": False,
        }
    )
    assert cfg2.disable_progressive_edits_after == 2
    assert cfg2.flood_backoff_factor == 3.0
    assert cfg2.max_interval == 10.0
    assert cfg2.strip_reasoning_tags is False


@pytest.mark.asyncio
async def test_edit_flood_widens_interval_and_disables_progressive():
    adapter = _make_adapter(edit_side_effect=FloodError())
    cfg = StreamingConfig(
        mode=StreamingMode.DRAFT,
        min_interval=1.0,
        flood_backoff_factor=2.0,
        max_interval=8.0,
        disable_progressive_edits_after=3,
    )
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()
    streamer._content_buffer = "some content"

    # Three failing edits -> progressive disabled, interval widened (capped).
    # Backoff mutates per-stream runtime state, NOT the shared config.
    await streamer._perform_update()
    assert streamer._fail_streak == 1
    assert streamer._current_min_interval == pytest.approx(2.0)
    assert cfg.min_interval == pytest.approx(1.0)  # shared config untouched
    assert streamer._progressive is True

    await streamer._perform_update()
    assert streamer._fail_streak == 2
    assert streamer._current_min_interval == pytest.approx(4.0)

    await streamer._perform_update()
    assert streamer._fail_streak == 3
    assert streamer._progressive is False
    # capped at max_interval
    assert streamer._current_min_interval == pytest.approx(8.0)
    assert cfg.min_interval == pytest.approx(1.0)  # shared config untouched


@pytest.mark.asyncio
async def test_backoff_does_not_leak_across_streams():
    """A flood in one stream must not slow a fresh stream sharing the config."""
    cfg = StreamingConfig(
        mode=StreamingMode.DRAFT,
        min_interval=1.0,
        flood_backoff_factor=2.0,
        max_interval=8.0,
        disable_progressive_edits_after=3,
    )

    flooded_adapter = _make_adapter(edit_side_effect=FloodError())
    flooded = DraftStreamer(flooded_adapter, "chan", cfg, platform="telegram")
    await flooded.start()
    flooded._content_buffer = "content"
    await flooded._perform_update()
    assert flooded._current_min_interval == pytest.approx(2.0)

    # A new stream built from the SAME config starts fresh at the base interval.
    healthy = DraftStreamer(_make_adapter(), "chan2", cfg, platform="telegram")
    assert healthy._current_min_interval == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_finalize_falls_back_to_send_when_progressive_disabled():
    adapter = _make_adapter(edit_side_effect=FloodError())
    cfg = StreamingConfig(mode=StreamingMode.DRAFT, disable_progressive_edits_after=1)
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()
    streamer._content_buffer = "partial"

    await streamer._perform_update()  # one flood failure disables progressive
    assert streamer._progressive is False

    await streamer.finalize("the complete answer")
    # Edits keep flooding, so finalize falls back to a fresh send. The user
    # always receives the full answer.
    adapter.send_message.assert_awaited_with("chan", "the complete answer")


@pytest.mark.asyncio
async def test_finalize_reuses_placeholder_when_edit_succeeds():
    """When the final edit succeeds, no stale draft and no duplicate send."""
    adapter = _make_adapter()  # edits succeed
    cfg = StreamingConfig(mode=StreamingMode.DRAFT, disable_progressive_edits_after=1)
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()
    # Simulate progressive having been disabled previously.
    streamer._progressive = False

    await streamer.finalize("the complete answer")
    # Placeholder is edited in place; no extra fresh send is issued.
    adapter.edit_message.assert_awaited_with("chan", "m1", "the complete answer")
    adapter.send_message.assert_awaited_once()  # only the start() placeholder


@pytest.mark.asyncio
async def test_finalize_falls_back_to_send_when_edit_fails():
    """A failing final edit must still deliver the answer via a fresh send."""
    adapter = _make_adapter(edit_side_effect=FloodError())
    cfg = StreamingConfig(mode=StreamingMode.DRAFT)
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()

    await streamer.finalize("the complete answer")
    adapter.send_message.assert_awaited_with("chan", "the complete answer")


@pytest.mark.asyncio
async def test_finalize_strips_reasoning_tags():
    adapter = _make_adapter()
    cfg = StreamingConfig(mode=StreamingMode.DRAFT)
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()

    await streamer.finalize("Answer <think>internal</think> done")
    adapter.edit_message.assert_awaited_with("chan", "m1", "Answer  done")


@pytest.mark.asyncio
async def test_non_recoverable_error_does_not_disable_progressive():
    adapter = _make_adapter(edit_side_effect=PermanentError())
    cfg = StreamingConfig(mode=StreamingMode.DRAFT, disable_progressive_edits_after=1)
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()
    streamer._content_buffer = "content"

    await streamer._perform_update()
    # Non-recoverable: no streak increment, progressive stays enabled
    assert streamer._fail_streak == 0
    assert streamer._progressive is True


@pytest.mark.asyncio
async def test_successful_edit_resets_streak():
    adapter = _make_adapter()
    cfg = StreamingConfig(mode=StreamingMode.DRAFT)
    streamer = DraftStreamer(adapter, "chan", cfg, platform="telegram")
    await streamer.start()
    streamer._fail_streak = 2
    streamer._content_buffer = "hello world"

    await streamer._perform_update()
    assert streamer._fail_streak == 0
    adapter.edit_message.assert_awaited()


if __name__ == "__main__":
    asyncio.run(test_edit_flood_widens_interval_and_disables_progressive())
    asyncio.run(test_finalize_falls_back_to_send_when_progressive_disabled())
    print("ok")
