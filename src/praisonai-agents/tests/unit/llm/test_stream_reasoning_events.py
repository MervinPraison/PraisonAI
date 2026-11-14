"""Reasoning deltas reach stream_emitter on the OpenAI-native Chat Completions path.

OpenAI-compatible reasoning servers (DeepSeek, vLLM, Ollama, LM Studio...) send
``delta.reasoning_content``. The OpenAI-native stream loop emitted it as a
``DELTA_TEXT(is_reasoning=True)`` StreamEvent only inside the Rich live-display
branch and only with ``reasoning_steps=True``; servers and UIs run without a
display, so they never saw any reasoning. The LiteLLM path already emits it
whenever events are on. Consumers that render answer text must drop
``is_reasoning`` deltas, so they never leak into the reply.
"""
import asyncio
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionChunk

from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.streaming.events import StreamEvent, StreamEventType


def _chunks():
    def c(delta, finish=None):
        return ChatCompletionChunk(
            id="x", object="chat.completion.chunk", created=0, model="m",
            choices=[{"index": 0, "delta": delta, "finish_reason": finish}],
        )
    usage_only = ChatCompletionChunk(
        id="x", object="chat.completion.chunk", created=0, model="m", choices=[],
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    )
    return [
        c({"role": "assistant"}),
        c({"reasoning_content": "think "}),
        c({"reasoning_content": "hard"}),
        c({"content": "Hello"}),
        c({"content": " world"}, "stop"),
        usage_only,
    ]


def _client():
    def create(**kwargs):
        return iter(_chunks())

    async def acreate(**kwargs):
        async def gen():
            for ch in _chunks():
                yield ch
        return gen()

    client = OpenAIClient(api_key="sk-test-not-real", base_url="http://127.0.0.1:9/v1")
    client._sync_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client._async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=acreate)))
    return client


def _split(events):
    reasoning = [e.content for e in events if e.type == StreamEventType.DELTA_TEXT and e.is_reasoning]
    text = [e.content for e in events
            if e.type in (StreamEventType.FIRST_TOKEN, StreamEventType.DELTA_TEXT) and not e.is_reasoning]
    return reasoning, text


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_reasoning_is_emitted_without_a_display(mode):
    events = []
    client = _client()
    kwargs = dict(messages=[{"role": "user", "content": "q"}], model="m",
                  stream_callback=events.append, emit_events=True)
    if mode == "sync":
        resp = client.process_stream_response(**kwargs)
    else:
        resp = asyncio.run(client.process_stream_response_async(**kwargs))
    reasoning, text = _split(events)
    assert reasoning == ["think ", "hard"]
    assert text == ["Hello", " world"]
    assert resp.choices[0].message.content == "Hello world"
    assert resp.choices[0].message.reasoning_content == "think hard"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_nothing_is_emitted_when_events_are_off(mode):
    client = _client()
    kwargs = dict(messages=[{"role": "user", "content": "q"}], model="m")
    if mode == "sync":
        resp = client.process_stream_response(**kwargs)
    else:
        resp = asyncio.run(client.process_stream_response_async(**kwargs))
    assert resp.choices[0].message.content == "Hello world"


def test_agui_does_not_turn_reasoning_into_answer_text():
    from praisonaiagents.ui.agui.streaming import EventBuffer, stream_event_to_agui_events

    ev = StreamEvent(type=StreamEventType.DELTA_TEXT, content="secret thoughts", is_reasoning=True)
    assert stream_event_to_agui_events(ev, "m1", EventBuffer()) == []


def test_print_callback_skips_reasoning(capsys):
    from praisonaiagents.streaming.events import create_text_printer_callback

    cb = create_text_printer_callback()
    cb(StreamEvent(type=StreamEventType.DELTA_TEXT, content="secret", is_reasoning=True))
    cb(StreamEvent(type=StreamEventType.DELTA_TEXT, content="answer"))
    assert capsys.readouterr().out == "answer"
