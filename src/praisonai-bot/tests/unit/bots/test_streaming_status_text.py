#!/usr/bin/env python3
"""
Tests for the textual status-line surface on edit-less channels (issue #6162).

A channel that can neither edit messages nor react, but declares
``PlatformCapabilities.supports_status_text`` and implements
``set_status_text``, gets the curated activity line instead of silence.
Default (flag off) behaviour is unchanged: non-edit channels degrade to OFF.
"""

import asyncio

import pytest

from praisonaiagents.bots import PlatformCapabilities
from praisonaiagents.streaming.events import StreamEvent, StreamEventType
from praisonai_bot.bots._streaming import DraftStreamer, StreamingConfig, StreamingMode


class _StatusAdapter:
    capabilities = {"live_edit": False}

    def __init__(self, supports_status_text=True):
        self.platform_capabilities = PlatformCapabilities(
            supports_edit=False, supports_status_text=supports_status_text
        )
        self.status = []
        self.sent = []
        self.edits = []

    async def set_status_text(self, channel_id, text):
        self.status.append((channel_id, text))

    async def send_message(self, channel_id, content):
        self.sent.append(content)
        return {"message_id": "x"}

    async def edit_message(self, channel_id, message_id, content):
        self.edits.append(content)


def test_capability_defaults_off_and_round_trips():
    assert PlatformCapabilities().supports_status_text is False
    caps = PlatformCapabilities(supports_status_text=True)
    assert PlatformCapabilities.from_dict(caps.to_dict()).supports_status_text is True


@pytest.mark.parametrize("mode", [StreamingMode.AUTO, StreamingMode.PROGRESS])
def test_non_edit_channel_without_flag_still_degrades_to_off(mode):
    s = DraftStreamer(_StatusAdapter(False), "c", StreamingConfig(mode=mode))
    assert s._config.mode == StreamingMode.OFF
    assert not s._status_text_only


def test_flag_without_method_degrades_to_off():
    class _NoMethod:
        capabilities = {"live_edit": False}
        platform_capabilities = PlatformCapabilities(supports_status_text=True)

    s = DraftStreamer(_NoMethod(), "c", StreamingConfig(mode=StreamingMode.AUTO))
    assert s._config.mode == StreamingMode.OFF


def test_draft_mode_is_not_rerouted():
    s = DraftStreamer(_StatusAdapter(), "c", StreamingConfig(mode=StreamingMode.DRAFT))
    assert s._config.mode == StreamingMode.OFF


@pytest.mark.parametrize("mode", [StreamingMode.AUTO, StreamingMode.PROGRESS])
def test_status_text_route_end_to_end(mode):
    adapter = _StatusAdapter()
    cfg = StreamingConfig(
        mode=mode, min_interval=0, progress_prefix="",
        activity_phrases={"web": "Searching the web…"},
    )
    s = DraftStreamer(adapter, "c", cfg)
    assert s._config.mode == StreamingMode.PROGRESS
    assert s._status_text_only

    async def run():
        await s.start()
        assert s.is_streaming
        await s.on_event(StreamEvent(
            type=StreamEventType.TOOL_CALL_START, tool_call={"name": "web_search"},
        ))
        await s._update_task
        # Text tokens must not re-send an unchanged status line.
        await s.on_event(StreamEvent(type=StreamEventType.DELTA_TEXT, content="partial"))
        if s._update_task:
            await s._update_task
        await s.finalize("final answer")

    asyncio.run(run())
    assert [t for _, t in adapter.status] == ["🤔 Thinking...", "Searching the web…"]
    assert adapter.sent == ["final answer"]  # no placeholder message was sent
    assert adapter.edits == []
    assert not s.is_streaming


def test_status_text_failure_never_breaks_turn():
    adapter = _StatusAdapter()

    async def boom(channel_id, text):
        raise RuntimeError("nope")

    adapter.set_status_text = boom
    s = DraftStreamer(adapter, "c", StreamingConfig(mode=StreamingMode.AUTO))

    async def run():
        await s.start()
        await s.finalize("done")

    asyncio.run(run())
    assert adapter.sent == ["done"]
