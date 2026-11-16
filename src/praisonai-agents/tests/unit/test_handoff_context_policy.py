"""Handoff context policies must keep tool-call pairs intact and keep the goal."""

from types import SimpleNamespace

from praisonaiagents.agent.handoff import (
    ContextPolicy,
    Handoff,
    HandoffConfig,
    _tool_pair_safe_tail,
)

CALL = {"id": "c1", "type": "function", "function": {"name": "search", "arguments": "{}"}}
HISTORY = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "GOAL: book flight"},
    {"role": "assistant", "content": "ok, searching"},
    {"role": "assistant", "content": None, "tool_calls": [CALL]},
    {"role": "tool", "tool_call_id": "c1", "content": "results"},
    {"role": "assistant", "content": "found 3 options"},
]


def _prepare(policy, n=10):
    target = SimpleNamespace(name="tgt")
    handoff = Handoff(agent=target, config=HandoffConfig(context_policy=policy, max_context_messages=n))
    source = SimpleNamespace(name="src", chat_history=list(HISTORY))
    return handoff._prepare_context(source, {}).messages


def _assert_pairs_valid(messages):
    call_ids = {c["id"] for m in messages for c in (m.get("tool_calls") or [])}
    response_ids = {m["tool_call_id"] for m in messages if m.get("role") == "tool"}
    assert call_ids == response_ids


def test_last_n_drops_orphan_tool_result():
    msgs = _prepare(ContextPolicy.LAST_N, n=2)
    _assert_pairs_valid(msgs)
    assert [m["role"] for m in msgs] == ["system", "assistant"]


def test_last_n_keeps_complete_pair():
    msgs = _prepare(ContextPolicy.LAST_N, n=3)
    _assert_pairs_valid(msgs)
    assert any(m.get("tool_calls") for m in msgs)


def test_summary_keeps_goal_and_valid_pairs():
    msgs = _prepare(ContextPolicy.SUMMARY)
    _assert_pairs_valid(msgs)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["content"] == "GOAL: book flight"
    assert msgs[-1]["content"] == "found 3 options"


def test_summary_does_not_duplicate_goal_in_tail():
    target = SimpleNamespace(name="tgt")
    handoff = Handoff(agent=target, config=HandoffConfig(context_policy=ContextPolicy.SUMMARY))
    source = SimpleNamespace(name="src", chat_history=[{"role": "user", "content": "hi"}])
    assert handoff._prepare_context(source, {}).messages == [{"role": "user", "content": "hi"}]


def test_tail_drops_tool_calls_without_responses():
    msgs = HISTORY[1:4]  # ends on an unanswered tool_calls message
    assert _tool_pair_safe_tail(msgs, 3) == HISTORY[1:3]
    assert _tool_pair_safe_tail(msgs, 0) == []
