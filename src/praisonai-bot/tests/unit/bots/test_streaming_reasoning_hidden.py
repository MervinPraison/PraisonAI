"""Reasoning deltas must never be posted into a chat reply.

The SDK emits a model's ``reasoning_content`` as ``DELTA_TEXT`` with
``is_reasoning=True`` (LiteLLM path, and now the OpenAI-native path too).
DraftStreamer appended every DELTA_TEXT to the visible reply, so a reasoning
model's private chain of thought would be streamed to Telegram/Slack/Discord.
"""
import asyncio

from praisonaiagents.streaming.events import StreamEvent, StreamEventType

from praisonai_bot.bots._streaming import DraftStreamer, StreamingConfig


def _streamer() -> DraftStreamer:
    class _Adapter:
        capabilities = {"live_edit": True}

    s = DraftStreamer(_Adapter(), "chan", StreamingConfig(), platform="telegram")
    s._message_id = "m1"
    s._progressive = False  # buffer only, no edits scheduled
    return s


def test_reasoning_delta_is_not_added_to_the_reply():
    s = _streamer()
    asyncio.run(s.on_event(StreamEvent(
        type=StreamEventType.DELTA_TEXT, content="private thoughts", is_reasoning=True)))
    asyncio.run(s.on_event(StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello")))
    assert s._content_buffer == "Hello"
