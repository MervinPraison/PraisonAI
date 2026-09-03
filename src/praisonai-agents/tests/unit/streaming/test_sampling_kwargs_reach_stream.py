"""max_tokens and top_p passed to Agent.start(stream=True) must reach the wire.

The desktop forwards Max-output-tokens and Top-p into agent.start(**kwargs), the
same route temperature travels.  The OpenAI streaming path in chat_mixin only
read four keys (model/messages/temperature/stream), so max_tokens and top_p were
silently dropped.  These tests record the kwargs the stubbed completions.create
receives and assert both arrive when supplied and stay absent when omitted.
"""
import types

from praisonaiagents import Agent
from praisonaiagents.llm.openai_client import OpenAIClient


def _one_chunk_stream():
    chunk = types.SimpleNamespace(
        choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(content="hi", tool_calls=None),
            finish_reason="stop",
        )]
    )
    yield chunk


def _agent_with_recorder():
    recorded = {}

    def _create(**kwargs):
        recorded.update(kwargs)
        return _one_chunk_stream()

    client = OpenAIClient(api_key="sk-not-a-real-key")
    client._sync_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=_create)))

    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini")
    agent._Agent__openai_client = client
    return agent, recorded


def test_max_tokens_and_top_p_reach_completion_create():
    agent, recorded = _agent_with_recorder()
    list(agent.start("x", stream=True, max_tokens=7, top_p=0.5))
    assert recorded.get("max_tokens") == 7, "max_tokens dropped on streaming path"
    assert recorded.get("top_p") == 0.5, "top_p dropped on streaming path"


def test_absent_sampling_keys_stay_absent():
    agent, recorded = _agent_with_recorder()
    list(agent.start("x", stream=True))
    assert "max_tokens" not in recorded, "max_tokens must not appear when unset"
    assert "top_p" not in recorded, "top_p must not appear when unset"
