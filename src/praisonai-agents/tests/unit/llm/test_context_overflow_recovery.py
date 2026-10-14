"""Reactive recovery after a provider context-overflow rejection (issue #5811)."""

import asyncio
from collections import defaultdict
from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.compaction import ContextCompactor
from praisonaiagents.llm.llm import LLM


class ContextWindowExceededError(Exception):
    pass


def _fake_provider(limit, calls):
    """A provider that rejects any request whose prompt exceeds ``limit`` tokens."""
    counter = ContextCompactor()

    def respond(kwargs):
        tokens = counter.count_total_tokens(kwargs["messages"])
        calls.append(tokens)
        if tokens > limit:
            raise ContextWindowExceededError(
                f"prompt is too long: {tokens} tokens > {limit} maximum"
            )
        return {"choices": [{"message": {"content": "ok"}}]}

    return respond


def _llm(monkeypatch):
    llm = LLM(model="custom/test-model", api_key="test")
    llm.verbose = False
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: False)
    return llm


def _long_history(turns=40):
    history = []
    for i in range(turns):
        history.append({"role": "user", "content": f"question {i} " + "x " * 200})
        history.append({"role": "assistant", "content": f"answer {i} " + "y " * 200})
    return history


def test_get_response_recovers_after_provider_overflow(monkeypatch):
    llm = _llm(monkeypatch)
    calls = []
    provider = _fake_provider(limit=3000, calls=calls)
    monkeypatch.setattr(llm, "_call_with_retry", lambda _fn, **kw: provider(kw))

    with patch(
        "praisonaiagents.llm.llm._get_display_functions",
        return_value=defaultdict(MagicMock),
    ):
        result = llm.get_response(
            prompt="final question",
            system_prompt="You are helpful.",
            chat_history=_long_history(),
            stream=False,
            verbose=False,
        )

    assert result == "ok"
    assert len(calls) >= 2
    assert calls[-1] <= 3000 < calls[0]


def test_async_completion_recovers_after_provider_overflow(monkeypatch):
    llm = _llm(monkeypatch)
    calls = []
    provider = _fake_provider(limit=3000, calls=calls)

    async def fake_call(_fn, **kw):
        return provider(kw)

    monkeypatch.setattr(llm, "_call_with_retry_async", fake_call)
    messages = [{"role": "system", "content": "sys"}] + _long_history() + [
        {"role": "user", "content": "final question"}
    ]

    response = asyncio.run(llm._acompletion_with_retry(model="m", messages=messages))

    assert response["choices"][0]["message"]["content"] == "ok"
    assert calls[-1] <= 3000 < calls[0]
    assert messages[-1] == {"role": "user", "content": "final question"}


def test_overflow_still_raises_when_prompt_cannot_shrink(monkeypatch):
    llm = _llm(monkeypatch)
    calls = []
    provider = _fake_provider(limit=10, calls=calls)
    monkeypatch.setattr(llm, "_call_with_retry", lambda _fn, **kw: provider(kw))
    messages = [{"role": "user", "content": "a single huge prompt " * 100}]

    with pytest.raises(ContextWindowExceededError):
        llm._completion_with_retry(model="m", messages=messages)

    assert len(calls) == 1  # nothing to shrink -> no wasted retries


def test_overflow_retries_are_bounded(monkeypatch):
    llm = _llm(monkeypatch)
    calls = []
    provider = _fake_provider(limit=1, calls=calls)
    monkeypatch.setattr(llm, "_call_with_retry", lambda _fn, **kw: provider(kw))
    messages = _long_history() + [{"role": "user", "content": "final"}]

    with pytest.raises(ContextWindowExceededError):
        llm._completion_with_retry(model="m", messages=messages)

    assert len(calls) <= 4  # initial attempt + at most 3 shrink steps


def test_shrink_to_fit_keeps_current_turn_and_tool_pairs():
    big = "z" * 20000
    messages = [
        {"role": "system", "content": "sys"},
        *_long_history(5),
        {"role": "user", "content": "read the file"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "read", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": big},
    ]
    compactor = ContextCompactor()
    before = compactor.count_total_tokens(messages)

    shrunk = compactor.shrink_to_fit(messages, before // 2)

    assert compactor.count_total_tokens(shrunk) < before
    assert shrunk[0]["role"] == "system"
    assert shrunk[1] == {"role": "user", "content": "read the file"}
    assert shrunk[2]["tool_calls"][0]["id"] == "c1"
    assert shrunk[3]["tool_call_id"] == "c1"
    assert "truncated" in shrunk[3]["content"]
    assert messages[-1]["content"] == big  # input not mutated


def test_native_agent_path_shrinks_without_context_manager():
    from praisonaiagents import Agent

    agent = Agent(name="t", instructions="Be helpful")
    assert agent.context_manager is None
    messages = [{"role": "system", "content": "sys"}] + _long_history() + [
        {"role": "user", "content": "final question"}
    ]
    compactor = ContextCompactor()
    before = compactor.count_total_tokens(messages)

    shrunk = agent._shrink_after_context_overflow(messages, "gpt-4o-mini")

    assert compactor.count_total_tokens(shrunk) <= before // 2
    assert shrunk[-1] == {"role": "user", "content": "final question"}


def test_shrink_to_fit_keeps_task_behind_tool_loop_user_messages():
    """Synthesized user messages (media follow-ups, steering) don't end the turn."""
    messages = [
        {"role": "system", "content": "sys"},
        *_long_history(5),
        {"role": "user", "content": "summarise the report"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "read", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "w " * 3000},
        {"role": "user", "content": "[steering] keep it short"},
    ]
    compactor = ContextCompactor()

    shrunk = compactor.shrink_to_fit(messages, compactor.count_total_tokens(messages) // 2)

    assert shrunk[1] == {"role": "user", "content": "summarise the report"}
    assert shrunk[2]["tool_calls"][0]["id"] == "c1"
    assert shrunk[-1]["content"] == "[steering] keep it short"


def test_shrink_to_fit_never_grows_small_tool_results():
    messages = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "read", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "a" * 510},
    ]

    shrunk = ContextCompactor().shrink_to_fit(messages, 1)

    assert len(shrunk[2]["content"]) <= 510


def test_overflow_classified_by_exception_type():
    llm = LLM(model="custom/test-model", api_key="test")

    assert llm.classify_error_kind(ContextWindowExceededError("bad request")) == "context_overflow"


def test_native_restart_skipped_for_tool_turns_without_context_manager():
    """Restarting a tool turn from its outer messages would rerun finished tools."""
    from praisonaiagents import Agent

    def read():
        return "x"

    agent = Agent(name="t", instructions="Be helpful", tools=[read], context=False)
    assert agent.context_manager is None
    assert agent._can_restart_after_overflow(None) is False
    assert Agent(name="t2", instructions="hi")._can_restart_after_overflow(None) is True
