"""
Unit tests for executable completion gates (issue #4053).

Covers:
- FileCheckHook matrix (exists / non_empty / json_field equals / contains).
- CommandVerificationHook string-command parsing.
- The verification gate blocks completion until a blocking hook passes; a
  never-passing check ends at the budget cap (max_iterations), never success.
- The gate releases once a hook flips to passing (temp-file flag).
- add_verification mid-run is enforced on the same run.
- The goal loop short-circuits to 'continue' without a judge call when a
  blocking hook fails, and injects executable evidence into the judge prompt.
"""

import json
import os

from unittest.mock import patch

from praisonaiagents.hooks.verification import (
    CommandVerificationHook,
    FileCheckHook,
)
from praisonaiagents.goal.judge import _build_goal_judge_prompt
from praisonaiagents.goal.models import GoalState


def _make_agent(verification_hooks=None):
    from praisonaiagents import Agent
    return Agent(
        instructions="Test agent",
        autonomy=True,
        output="silent",
        verification_hooks=verification_hooks,
    )


# =============================================================================
# FileCheckHook matrix
# =============================================================================

class TestFileCheckHook:
    def test_exists_pass(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("x")
        r = FileCheckHook(name="f", path=str(p)).run()
        assert r.success is True

    def test_exists_fail(self, tmp_path):
        r = FileCheckHook(name="f", path=str(tmp_path / "missing.txt")).run()
        assert r.success is False
        assert "not found" in r.output.lower()

    def test_absent_pass(self, tmp_path):
        r = FileCheckHook(name="f", path=str(tmp_path / "missing.txt"),
                          exists=False).run()
        assert r.success is True

    def test_non_empty_fail(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        r = FileCheckHook(name="f", path=str(p), non_empty=True).run()
        assert r.success is False
        assert "empty" in r.output.lower()

    def test_non_empty_pass(self, tmp_path):
        p = tmp_path / "full.txt"
        p.write_text("data")
        r = FileCheckHook(name="f", path=str(p), non_empty=True).run()
        assert r.success is True

    def test_contains_pass_and_fail(self, tmp_path):
        p = tmp_path / "c.txt"
        p.write_text("hello world")
        assert FileCheckHook(name="c", path=str(p), contains="world").run().success
        r = FileCheckHook(name="c", path=str(p), contains="absent").run()
        assert r.success is False

    def test_json_field_equals(self, tmp_path):
        p = tmp_path / "d.json"
        p.write_text(json.dumps({"status": {"code": 0}}))
        ok = FileCheckHook(name="j", path=str(p),
                           json_field="status.code", equals=0).run()
        assert ok.success is True
        bad = FileCheckHook(name="j", path=str(p),
                            json_field="status.code", equals=1).run()
        assert bad.success is False
        assert "expected" in bad.output.lower()

    def test_json_invalid(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        r = FileCheckHook(name="j", path=str(p),
                          json_field="a", equals=1).run()
        assert r.success is False
        assert "json" in r.output.lower()


class TestCommandHookParsing:
    def test_string_command_is_split(self):
        hook = CommandVerificationHook(name="t", command="python -c pass")
        assert hook.command == ["python", "-c", "pass"]

    def test_list_command_preserved(self):
        hook = CommandVerificationHook(name="t", command=["echo", "hi"])
        assert hook.command == ["echo", "hi"]


# =============================================================================
# _run_verification_hooks preserves the full payload
# =============================================================================

class TestRunnerFidelity:
    def test_details_survive_rewrap(self, tmp_path):
        p = tmp_path / "x.txt"
        p.write_text("hi")
        agent = _make_agent([FileCheckHook(name="f", path=str(p))])
        results = agent._run_verification_hooks()
        assert len(results) == 1
        rec = results[0]
        assert rec["hook"] == "f"
        assert rec["success"] is True
        assert "details" in rec
        assert "duration_seconds" in rec
        assert rec["blocking"] is True


# =============================================================================
# Gate blocks / releases completion in the autonomous loop
# =============================================================================

class TestGateBlocksCompletion:
    def test_failing_hook_blocks_success_until_budget(self, tmp_path):
        # A file that never exists → blocking hook never passes.
        hook = FileCheckHook(name="need", path=str(tmp_path / "never.txt"))
        agent = _make_agent([hook])

        counter = {"n": 0}

        def fake_chat(prompt):
            counter["n"] += 1
            return f"used a tool and did work step {counter['n']} " + "x" * 200

        with patch.object(agent, "chat", side_effect=fake_chat):
            result = agent.run_autonomous("do it", max_iterations=3)

        assert result.success is False
        assert result.completion_reason == "max_iterations"
        # last feedback prompt carries the failing hook's name
        assert any(
            r.get("hook") == "need" and not r.get("success")
            for r in getattr(agent, "_last_verification_results", [])
        )

    def test_gate_releases_when_hook_flips(self, tmp_path):
        flag = tmp_path / "done.flag"
        hook = FileCheckHook(name="flag", path=str(flag))
        agent = _make_agent([hook])

        counter = {"n": 0}

        def fake_chat(prompt):
            counter["n"] += 1
            # a tool was "used" this turn so the tool_completion signal fires
            agent._autonomy_turn_tool_count = 1
            # create the flag on the 2nd turn so the gate releases afterwards
            if counter["n"] == 2:
                flag.write_text("ok")
            return f"progress {counter['n']} " + "y" * 200

        with patch.object(agent, "chat", side_effect=fake_chat), \
             patch.object(agent, "get_recommended_stage", return_value="autonomous"):
            result = agent.run_autonomous("do it", max_iterations=10)

        assert result.success is True
        # released only after the flag appeared (2+ iterations)
        assert result.iterations >= 2

    def test_add_verification_midrun_is_enforced(self, tmp_path):
        agent = _make_agent()  # no hooks initially
        missing = tmp_path / "missing.txt"

        counter = {"n": 0}

        def fake_chat(prompt):
            counter["n"] += 1
            if counter["n"] == 1:
                # discover a completion condition mid-run
                agent.add_verification(FileCheckHook(name="late", path=str(missing)))
            return f"work {counter['n']} " + "z" * 200

        with patch.object(agent, "chat", side_effect=fake_chat):
            result = agent.run_autonomous("do it", max_iterations=3)

        # Now blocked by the late-added hook → cannot finish successfully.
        assert result.success is False
        assert result.completion_reason == "max_iterations"

    def test_no_hooks_unchanged(self):
        agent = _make_agent()
        with patch.object(agent, "chat",
                          side_effect=lambda p: "used tool " + "q" * 200):
            result = agent.run_autonomous("do it", max_iterations=5)
        # Behaviour is unchanged for agents without verification hooks: the
        # existing heuristics still terminate successfully (not blocked).
        assert result.success is True
        assert result.completion_reason != "max_iterations"


# =============================================================================
# Goal loop: executable evidence + short-circuit
# =============================================================================

class TestGoalLoopEvidence:
    def test_failing_blocking_hook_short_circuits_without_judge(self, tmp_path):
        hook = FileCheckHook(name="need", path=str(tmp_path / "never.txt"))
        agent = _make_agent([hook])
        judge_calls = {"n": 0}

        def fake_judge(*a, **k):
            judge_calls["n"] += 1
            return ("done", "met")

        counter = {"n": 0}

        with patch.object(agent, "chat",
                          side_effect=lambda p: f"step {counter.__setitem__('n', counter['n'] + 1) or counter['n']}"), \
             patch("praisonaiagents.goal.loop.judge_goal", side_effect=fake_judge):
            result = agent.run_goal("task", goal="g", max_turns=2)

        # Blocking hook fails every turn → judge never consulted, ends paused.
        assert judge_calls["n"] == 0
        assert result.completion_reason == "budget_paused"

    def test_passing_hook_evidence_reaches_judge(self, tmp_path):
        p = tmp_path / "ok.txt"
        p.write_text("data")
        hook = FileCheckHook(name="ok", path=str(p))
        agent = _make_agent([hook])
        seen = {}

        def fake_judge(state, tail, **k):
            seen["block"] = k.get("verification_block")
            return ("done", "met")

        with patch.object(agent, "chat", side_effect=lambda pr: "did it"), \
             patch("praisonaiagents.goal.loop.judge_goal", side_effect=fake_judge):
            result = agent.run_goal("task", goal="g", max_turns=5)

        assert result.completion_reason == "goal_met"
        assert seen.get("block") is not None
        assert "ok" in seen["block"]

    def test_judge_prompt_includes_verification_block(self):
        state = GoalState(goal="G")
        prompt = _build_goal_judge_prompt(
            state, "output", verification_block="[PASS] tests (exit=0)"
        )
        assert "[PASS] tests (exit=0)" in prompt

    def test_goal_failure_carries_diagnostics_into_continuation(self, tmp_path):
        # A failing blocking command hook must surface its captured stderr in
        # the next continuation prompt (not just a bare label).
        hook = CommandVerificationHook(
            name="fails",
            command="python -c \"import sys; sys.stderr.write('boom-detail'); sys.exit(1)\"",
        )
        agent = _make_agent([hook])
        prompts = []

        def fake_chat(pr):
            prompts.append(pr)
            return "trying"

        with patch.object(agent, "chat", side_effect=fake_chat), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   side_effect=lambda *a, **k: ("done", "met")):
            result = agent.run_goal("task", goal="g", max_turns=2)

        assert result.completion_reason == "budget_paused"
        # The continuation prompt after the first failing turn embeds the
        # hook's captured stderr so the agent can repair the failure.
        assert any("boom-detail" in p for p in prompts)


# =============================================================================
# Async gate: hook execution must not block the event loop
# =============================================================================

class TestAsyncGate:
    def test_async_gate_offloads_to_thread(self, tmp_path):
        import asyncio
        import threading

        loop_thread = {"id": None}
        hook_thread = {"id": None}

        class _ThreadProbeHook:
            name = "probe"
            blocking = True

            def run(self, context=None):
                from praisonaiagents.hooks.verification import VerificationResult
                hook_thread["id"] = threading.get_ident()
                return VerificationResult(success=True, output="ok")

        agent = _make_agent([_ThreadProbeHook()])

        async def _drive():
            loop_thread["id"] = threading.get_ident()
            return await agent._verification_gate_async("resp", 1)

        feedback = asyncio.run(_drive())
        # Passing hook → gate releases (None) and ran off the loop thread.
        assert feedback is None
        assert hook_thread["id"] is not None
        assert hook_thread["id"] != loop_thread["id"]


# =============================================================================
# Durable journal: verification results are persisted as journal events
# =============================================================================

class TestDurableJournal:
    def test_gate_records_verification_events(self, tmp_path):
        from praisonaiagents.runtime.journal import RunJournal
        from praisonaiagents.agent.durable import DurableRunContext

        journal = RunJournal(":memory:")
        journal.open_run("r1", agent="a", task="t")
        ctx = DurableRunContext(journal, "r1", replaying=False)

        p = tmp_path / "ok.txt"
        p.write_text("data")
        agent = _make_agent([FileCheckHook(name="ok", path=str(p))])

        with patch.object(agent, "_get_durable_run_context", return_value=ctx):
            feedback = agent._verification_gate("resp", 1)

        assert feedback is None
        events = [e for e in journal.events("r1") if e.kind == "verification"]
        assert len(events) == 1
        assert events[0].payload["name"] == "ok"
        assert events[0].payload["success"] is True

    def test_no_durable_run_is_noop(self, tmp_path):
        p = tmp_path / "ok.txt"
        p.write_text("data")
        agent = _make_agent([FileCheckHook(name="ok", path=str(p))])
        # No durable context attached → journal write is a silent no-op.
        assert agent._verification_gate("resp", 1) is None
