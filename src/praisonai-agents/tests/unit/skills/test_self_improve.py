"""Tests for the autonomous skill self-improvement loop (issue #2231)."""

import asyncio

from praisonaiagents.skills import (
    SkillReviewProtocol,
    DefaultSkillReviewPolicy,
)
from praisonaiagents import Agent


def test_default_policy_should_review_with_tools():
    policy = DefaultSkillReviewPolicy()
    assert policy.should_review({"tools_used": ["shell"]}) is True


def test_default_policy_skips_without_tools():
    policy = DefaultSkillReviewPolicy()
    assert policy.should_review({"tools_used": []}) is False
    assert policy.should_review({}) is False


def test_default_policy_min_tool_calls_threshold():
    policy = DefaultSkillReviewPolicy(min_tool_calls=2)
    assert policy.should_review({"tools_used": ["a"]}) is False
    assert policy.should_review({"tools_used": ["a", "b"]}) is True


def test_review_prompt_mentions_skill_manage():
    policy = DefaultSkillReviewPolicy()
    prompt = policy.review_prompt({"prompt": "task", "tools_used": ["shell"]})
    assert "skill_manage" in prompt
    assert "NO_SKILL" in prompt


def test_default_policy_satisfies_protocol():
    assert isinstance(DefaultSkillReviewPolicy(), SkillReviewProtocol)


def test_self_improve_off_by_default():
    agent = Agent(instructions="x")
    assert agent._self_improve is False


def test_self_improve_enabled_flag():
    agent = Agent(instructions="x", self_improve=True)
    assert agent._self_improve is True
    assert agent._in_skill_review is False


def test_self_improve_custom_policy():
    policy = DefaultSkillReviewPolicy(min_tool_calls=3)
    agent = Agent(instructions="x", self_improve=policy)
    assert agent._self_improve is True
    assert agent._self_improve_policy is policy


def test_run_skill_review_noop_when_disabled():
    agent = Agent(instructions="x")
    calls = []
    agent.chat = lambda *a, **k: calls.append(a) or "x"
    agent._run_skill_review("p", "r", ["shell"])
    assert calls == []


def test_run_skill_review_restricted_toolset():
    agent = Agent(instructions="x", self_improve=True)
    captured = {}

    def fake_chat(prompt, tools=None, **kwargs):
        captured["prompt"] = prompt
        captured["tools"] = tools
        return "NO_SKILL"

    agent.chat = fake_chat
    agent._run_skill_review("debug deploy", "done", ["shell"])

    # Restricted to exactly one tool: skill_manage.
    assert captured.get("tools") is not None
    assert len(captured["tools"]) == 1
    assert getattr(captured["tools"][0], "__name__", "") == "skill_manage"
    assert "skill_manage" in captured["prompt"]


def test_run_skill_review_reentrancy_guard():
    agent = Agent(instructions="x", self_improve=True)
    calls = []
    agent.chat = lambda *a, **k: calls.append(a) or "x"
    agent._in_skill_review = True
    agent._run_skill_review("p", "r", ["shell"])
    assert calls == []


def test_run_skill_review_skips_when_policy_declines():
    agent = Agent(instructions="x", self_improve=True)
    calls = []
    agent.chat = lambda *a, **k: calls.append(a) or "x"
    # No tools used -> default policy declines.
    agent._run_skill_review("p", "r", [])
    assert calls == []


def test_min_tool_calls_clamped_to_one():
    # min_tool_calls=0 would review on every (even no-op) turn; clamp to >=1.
    policy = DefaultSkillReviewPolicy(min_tool_calls=0)
    assert policy.min_tool_calls == 1
    assert policy.should_review({"tools_used": []}) is False


def test_review_prompt_truncates_long_prompt():
    policy = DefaultSkillReviewPolicy()
    long_prompt = "A" * 5000
    text = policy.review_prompt({"prompt": long_prompt, "tools_used": ["shell"]})
    # Original 5000-char block must not be echoed verbatim.
    assert "A" * 5000 not in text
    assert "A" * policy.MAX_PROMPT_CHARS in text


def test_review_turn_does_not_pollute_chat_history():
    agent = Agent(instructions="x", self_improve=True)
    agent.chat_history = [{"role": "user", "content": "real turn"}]

    def fake_chat(prompt, tools=None, **kwargs):
        # Simulate chat() appending the review exchange to shared history.
        agent.chat_history.append({"role": "user", "content": prompt})
        agent.chat_history.append({"role": "assistant", "content": "NO_SKILL"})
        return "NO_SKILL"

    agent.chat = fake_chat
    agent._run_skill_review("debug deploy", "done", ["shell"])

    # Review messages must be trimmed back out; only the real turn remains.
    assert agent.chat_history == [{"role": "user", "content": "real turn"}]


def test_review_turn_clears_in_review_flag_after():
    agent = Agent(instructions="x", self_improve=True)
    agent.chat = lambda *a, **k: "NO_SKILL"
    agent._run_skill_review("debug deploy", "done", ["shell"])
    assert agent._in_skill_review is False


def test_arun_skill_review_restricted_toolset():
    agent = Agent(instructions="x", self_improve=True)
    captured = {}

    async def fake_achat(prompt, tools=None, **kwargs):
        captured["prompt"] = prompt
        captured["tools"] = tools
        return "NO_SKILL"

    agent.achat = fake_achat
    asyncio.run(agent._arun_skill_review("debug deploy", "done", ["shell"]))

    assert captured.get("tools") is not None
    assert len(captured["tools"]) == 1
    assert getattr(captured["tools"][0], "__name__", "") == "skill_manage"
    assert "skill_manage" in captured["prompt"]


def test_arun_skill_review_noop_when_disabled():
    agent = Agent(instructions="x")
    calls = []

    async def fake_achat(*a, **k):
        calls.append(a)
        return "x"

    agent.achat = fake_achat
    asyncio.run(agent._arun_skill_review("p", "r", ["shell"]))
    assert calls == []


def test_arun_skill_review_reentrancy_guard():
    agent = Agent(instructions="x", self_improve=True)
    calls = []

    async def fake_achat(*a, **k):
        calls.append(a)
        return "x"

    agent.achat = fake_achat
    agent._in_skill_review = True
    asyncio.run(agent._arun_skill_review("p", "r", ["shell"]))
    assert calls == []


def test_clone_for_channel_preserves_self_improve():
    policy = DefaultSkillReviewPolicy(min_tool_calls=2)
    agent = Agent(instructions="x", self_improve=policy)
    clone = agent.clone_for_channel()
    assert clone._self_improve is True
    assert clone._self_improve_policy is policy
