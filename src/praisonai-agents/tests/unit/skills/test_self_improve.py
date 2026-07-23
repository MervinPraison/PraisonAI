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


# ---------------------------------------------------------------------------
# Post-response background execution mode (issue #2985)
# ---------------------------------------------------------------------------


def test_self_improve_mode_defaults_to_inline():
    assert Agent(instructions="x")._self_improve_mode == "inline"
    assert Agent(instructions="x", self_improve=True)._self_improve_mode == "inline"


def test_self_improve_background_string_enables_background_mode():
    agent = Agent(instructions="x", self_improve="background")
    assert agent._self_improve is True
    assert agent._self_improve_mode == "background"


def test_self_improve_inline_string_enables_inline_mode():
    agent = Agent(instructions="x", self_improve="inline")
    assert agent._self_improve is True
    assert agent._self_improve_mode == "inline"


def test_dispatch_skill_review_inline_runs_synchronously():
    agent = Agent(instructions="x", self_improve=True)
    calls = []
    agent._dispatch_skill_review(
        lambda p, r, t: calls.append((p, r, t)), "p", "r", ["shell"]
    )
    # Inline mode: the review has already run by the time dispatch returns.
    assert calls == [("p", "r", ["shell"])]


def test_dispatch_skill_review_background_runs_off_path():
    import time

    agent = Agent(instructions="x", self_improve="background")
    done = []

    def slow_review(p, r, t):
        time.sleep(0.15)
        done.append((p, r, t))

    start = time.time()
    agent._dispatch_skill_review(slow_review, "p", "r", ["shell"])
    elapsed = time.time() - start
    # Caller is not blocked by the review turn.
    assert elapsed < 0.1
    # But the review still runs on the background runner.
    for _ in range(50):
        if done:
            break
        time.sleep(0.02)
    assert done == [("p", "r", ["shell"])]


def test_clone_for_channel_preserves_background_mode():
    agent = Agent(instructions="x", self_improve="background")
    clone = agent.clone_for_channel()
    assert clone._self_improve is True
    assert clone._self_improve_mode == "background"


def test_schedule_self_improvement_falls_back_inline_on_failure(monkeypatch):
    agent = Agent(instructions="x", self_improve="background")
    ran = []

    def boom():
        raise RuntimeError("no runner")

    monkeypatch.setattr(
        "praisonaiagents.background.job_manager.get_job_manager", boom
    )
    agent._schedule_self_improvement(lambda: ran.append(True))
    assert ran == [True]


# ---------------------------------------------------------------------------
# Safe string parsing: falsy / unknown values must NOT enable review (P2)
# ---------------------------------------------------------------------------


def test_self_improve_falsy_strings_disable():
    for value in ("false", "off", "no", "0", "", "False", "OFF"):
        agent = Agent(instructions="x", self_improve=value)
        assert agent._self_improve is False, value
        assert agent._self_improve_mode == "inline"


def test_self_improve_unknown_string_disables():
    # A typo like "backround" must not silently enable inline review.
    agent = Agent(instructions="x", self_improve="backround")
    assert agent._self_improve is False
    assert agent._self_improve_mode == "inline"


def test_self_improve_truthy_strings_enable_inline():
    for value in ("true", "on", "yes", "1", "blocking", "sync"):
        agent = Agent(instructions="x", self_improve=value)
        assert agent._self_improve is True, value
        assert agent._self_improve_mode == "inline"


# ---------------------------------------------------------------------------
# Background scheduling uses a unique job id per invocation (P1)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Per-turn tool tracking feeds the review hook (issue #3037)
# ---------------------------------------------------------------------------


def test_turn_tools_used_initialized_empty():
    agent = Agent(instructions="x", self_improve=True)
    assert agent._turn_tools_used == []


def test_execute_tool_records_turn_tool():
    def read_file():
        return "contents"

    agent = Agent(instructions="x", self_improve=True, tools=[read_file])
    agent._execute_tool_with_context("read_file", {}, None, None)
    assert "read_file" in agent._turn_tools_used


def test_execute_tool_skips_tracking_during_review():
    def read_file():
        return "contents"

    agent = Agent(instructions="x", self_improve=True, tools=[read_file])
    agent._in_skill_review = True
    agent._execute_tool_with_context("read_file", {}, None, None)
    assert agent._turn_tools_used == []


def test_execute_tool_async_records_turn_tool():
    def read_file():
        return "contents"

    agent = Agent(instructions="x", self_improve=True, tools=[read_file])
    asyncio.run(agent.execute_tool_async("read_file", {}))
    assert "read_file" in agent._turn_tools_used


def test_execute_tool_async_skips_tracking_during_review():
    def read_file():
        return "contents"

    agent = Agent(instructions="x", self_improve=True, tools=[read_file])
    agent._in_skill_review = True
    asyncio.run(agent.execute_tool_async("read_file", {}))
    assert agent._turn_tools_used == []


def test_after_agent_hook_uses_turn_tools_used_when_not_passed():
    agent = Agent(instructions="x", self_improve=True)
    captured = {}

    def fake_review(prompt, response, tools_used):
        captured["tools_used"] = tools_used

    agent._run_skill_review = fake_review
    agent._turn_tools_used = ["read_file", "read_file"]

    agent._trigger_after_agent_hook("prompt", "response", 0.0)

    # Hook defaults tools_used from the buffer so the review policy sees them.
    assert captured.get("tools_used") == ["read_file", "read_file"]


def test_after_agent_hook_resets_turn_tools_used():
    agent = Agent(instructions="x", self_improve=True)
    agent._run_skill_review = lambda p, r, t: None
    agent._turn_tools_used = ["shell"]
    agent._trigger_after_agent_hook("p", "r", 0.0)
    # Buffer consumed so the next turn starts clean.
    assert agent._turn_tools_used == []


def test_after_agent_hook_explicit_tools_used_wins():
    agent = Agent(instructions="x", self_improve=True)
    captured = {}
    agent._run_skill_review = lambda p, r, t: captured.setdefault("t", t)
    agent._turn_tools_used = ["buffered"]
    agent._trigger_after_agent_hook("p", "r", 0.0, tools_used=["explicit"])
    assert captured["t"] == ["explicit"]


def test_atrigger_after_agent_hook_uses_turn_tools_used():
    agent = Agent(instructions="x", self_improve=True)
    captured = {}

    async def fake_areview(prompt, response, tools_used):
        captured["tools_used"] = tools_used

    agent._arun_skill_review = fake_areview
    agent._turn_tools_used = ["shell"]
    asyncio.run(agent._atrigger_after_agent_hook("p", "r", 0.0))
    assert captured.get("tools_used") == ["shell"]


def test_schedule_self_improvement_uses_unique_job_ids(monkeypatch):
    agent = Agent(instructions="x", self_improve="background")
    agent._session_id = "sess"
    job_ids = []

    class _FakeManager:
        def start_job(self, func, job_id=None):
            job_ids.append(job_id)
            return job_id

    monkeypatch.setattr(
        "praisonaiagents.background.job_manager.get_job_manager",
        lambda: _FakeManager(),
    )
    agent._schedule_self_improvement(lambda: None)
    agent._schedule_self_improvement(lambda: None)

    assert len(job_ids) == 2
    # Both scoped to the session but distinct so neither replaces the other.
    assert all(jid.startswith("self-improve:sess:") for jid in job_ids)
    assert job_ids[0] != job_ids[1]


def test_turn_tools_helpers_are_thread_safe():
    """Issue #3307 Gap 2: concurrent record/drain must not lose tool names."""
    import threading

    agent = Agent(instructions="x", self_improve=True)
    agent._reset_turn_tools()

    errors = []

    def worker():
        try:
            for _ in range(200):
                agent._record_turn_tool("t")
        except Exception as e:  # pragma: no cover - defensive
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    drained = agent._drain_turn_tools()
    # 8 threads * 200 appends, none lost to unlocked list mutation.
    assert len(drained) == 8 * 200
    # Buffer is empty after draining.
    assert agent._drain_turn_tools() == []
