"""The OpenAI-native adapter must hand the stream callback to the client.

``Agent._execute_unified_achat_completion`` passes
``stream_callback=self.stream_emitter.emit`` and ``emit_events=True`` to the
dispatcher. ``OpenAIAdapter.achat_completion`` filtered both out of
``**kwargs`` (so they never reach the OpenAI API) but never passed them as the
named parameters ``achat_completion_with_tools`` takes, so the client ran
with ``stream_callback=None, emit_events=False``: ``Agent.achat(stream=True)``
emitted no StreamEvent at all. Every stream_emitter consumer (PraisonAIUI's
``PraisonAIProvider``, AG-UI) lost text deltas, tool calls and reasoning, and
the UI only showed the final answer.
"""
import asyncio
import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.llm.unified_adapters import OpenAIAdapter, create_llm_dispatcher


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def achat_completion_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        return None


def _run(coro):
    return asyncio.run(coro)


def test_stream_callback_and_emit_events_reach_the_client():
    client = _RecordingClient()

    def cb(event):
        return None

    _run(OpenAIAdapter(client, "gpt-4o-mini").achat_completion(
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        stream_callback=cb,
        emit_events=True,
    ))
    call = client.calls[0]
    assert call["stream_callback"] is cb
    assert call["emit_events"] is True


def test_the_dispatcher_forwards_them_too():
    client = _RecordingClient()

    def cb(event):
        return None

    dispatcher = create_llm_dispatcher(openai_client=client, model="gpt-4o-mini")
    _run(dispatcher.achat_completion(
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        stream_callback=cb,
        emit_events=True,
    ))
    assert client.calls[0]["stream_callback"] is cb
    assert client.calls[0]["emit_events"] is True


def test_defaults_stay_off_and_metadata_stays_out():
    client = _RecordingClient()
    _run(OpenAIAdapter(client, "gpt-4o-mini").achat_completion(
        messages=[{"role": "user", "content": "hi"}],
        agent_role="r", task_id="t", markdown=True,
    ))
    call = client.calls[0]
    assert call["stream_callback"] is None
    assert call["emit_events"] is False
    for key in ("agent_role", "task_id", "markdown"):
        assert key not in call
