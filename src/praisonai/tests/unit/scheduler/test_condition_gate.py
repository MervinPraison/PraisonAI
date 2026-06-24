"""
Unit tests for the scheduler pre-run condition gate.

Covers:
- ``ShellConditionGate`` decisions (run / skip / context / timeout / no command)
- ``ScheduledAgentExecutor`` enforcement: gate skips the model turn, gate
  context is appended to the message, gate failures fall back to running,
  and gating can be disabled.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from praisonaiagents.scheduler.protocols import GateResult, JobConditionProtocol
from praisonai.scheduler.condition_gate import ShellConditionGate
from praisonai.scheduler.executor import ScheduledAgentExecutor, JobResult


# ── lightweight fakes ────────────────────────────────────────────────


@dataclass
class FakeJob:
    id: str = "job1"
    name: str = "test-job"
    message: str = "do the thing"
    agent_id: Optional[str] = None
    session_target: str = "isolated"
    delivery: Any = None
    pre_run: Optional[str] = None
    condition: Optional[str] = None


class FakeAgent:
    def __init__(self):
        self.tools = []
        self.last_message = None

    def chat(self, message):
        self.last_message = message
        return f"answer: {message}"


class FakeRunner:
    def __init__(self):
        self.runs = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


# ── ShellConditionGate ───────────────────────────────────────────────


class TestShellConditionGate:
    def test_no_command_runs(self):
        gate = ShellConditionGate()
        decision = gate.should_run(FakeJob(pre_run=None))
        assert decision.run is True
        assert decision.context is None

    def test_exit_zero_with_output_runs_with_context(self):
        gate = ShellConditionGate()
        decision = gate.should_run(FakeJob(pre_run="echo new-mail"))
        assert decision.run is True
        assert decision.context == "new-mail"

    def test_exit_zero_empty_output_runs_no_context(self):
        gate = ShellConditionGate()
        decision = gate.should_run(FakeJob(pre_run="true"))
        assert decision.run is True
        assert decision.context is None

    def test_nonzero_exit_skips(self):
        gate = ShellConditionGate()
        decision = gate.should_run(FakeJob(pre_run="false"))
        assert decision.run is False
        assert "nothing to do" in (decision.reason or "")

    def test_nonzero_exit_surfaces_stderr_in_reason(self):
        gate = ShellConditionGate()
        decision = gate.should_run(
            FakeJob(pre_run="echo boom 1>&2; exit 3"),
        )
        assert decision.run is False
        assert "boom" in (decision.reason or "")
        assert "exit 3" in (decision.reason or "")

    def test_timeout_skips(self):
        gate = ShellConditionGate(timeout=0.1)
        decision = gate.should_run(FakeJob(pre_run="sleep 5"))
        assert decision.run is False
        assert "timed out" in (decision.reason or "")

    def test_is_job_condition_protocol(self):
        assert isinstance(ShellConditionGate(), JobConditionProtocol)


# ── executor enforcement ─────────────────────────────────────────────


class TestExecutorGateEnforcement:
    def _run(self, executor, job):
        return asyncio.run(executor._execute_one(job))

    def test_gate_skip_does_not_call_agent(self):
        agent = FakeAgent()
        runner = FakeRunner()
        executor = ScheduledAgentExecutor(
            runner=runner, agent_resolver=lambda _id: agent,
        )
        job = FakeJob(pre_run="false")
        result = self._run(executor, job)
        assert result.status == "skipped"
        assert agent.last_message is None
        assert runner.runs[-1]["status"] == "skipped"

    def test_gate_go_appends_context(self):
        agent = FakeAgent()
        runner = FakeRunner()
        executor = ScheduledAgentExecutor(
            runner=runner, agent_resolver=lambda _id: agent,
        )
        job = FakeJob(message="Summarise", pre_run="echo new-mail")
        result = self._run(executor, job)
        assert result.status == "succeeded"
        assert agent.last_message == "Summarise\n\nnew-mail"

    def test_no_pre_run_runs_normally(self):
        agent = FakeAgent()
        runner = FakeRunner()
        executor = ScheduledAgentExecutor(
            runner=runner, agent_resolver=lambda _id: agent,
        )
        job = FakeJob(message="hi", pre_run=None)
        result = self._run(executor, job)
        assert result.status == "succeeded"
        assert agent.last_message == "hi"

    def test_custom_resolver_used(self):
        agent = FakeAgent()
        runner = FakeRunner()

        class AlwaysSkip:
            def should_run(self, job):
                return GateResult(run=False, reason="custom skip")

        executor = ScheduledAgentExecutor(
            runner=runner,
            agent_resolver=lambda _id: agent,
            condition_resolver=lambda job: AlwaysSkip(),
        )
        result = self._run(executor, FakeJob(message="hi"))
        assert result.status == "skipped"
        assert result.error == "custom skip"
        assert agent.last_message is None

    def test_gating_disabled_with_false(self):
        agent = FakeAgent()
        runner = FakeRunner()
        executor = ScheduledAgentExecutor(
            runner=runner,
            agent_resolver=lambda _id: agent,
            condition_resolver=False,
        )
        # pre_run would skip, but gating is disabled => runs anyway
        result = self._run(executor, FakeJob(message="hi", pre_run="false"))
        assert result.status == "succeeded"
        assert agent.last_message == "hi"

    def test_gate_exception_falls_back_to_running(self):
        agent = FakeAgent()
        runner = FakeRunner()

        class Boom:
            def should_run(self, job):
                raise RuntimeError("gate boom")

        executor = ScheduledAgentExecutor(
            runner=runner,
            agent_resolver=lambda _id: agent,
            condition_resolver=lambda job: Boom(),
        )
        result = self._run(executor, FakeJob(message="hi"))
        assert result.status == "succeeded"
        assert agent.last_message == "hi"


# ── model serialisation round-trip ───────────────────────────────────


class TestModelSerialisation:
    def test_pre_run_round_trips(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob(name="j", message="m", pre_run="echo hi", condition="cond")
        d = job.to_dict()
        assert d["pre_run"] == "echo hi"
        assert d["condition"] == "cond"
        restored = ScheduleJob.from_dict(d)
        assert restored.pre_run == "echo hi"
        assert restored.condition == "cond"

    def test_absent_pre_run_not_serialised(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob(name="j", message="m")
        d = job.to_dict()
        assert "pre_run" not in d
        assert "condition" not in d
        assert ScheduleJob.from_dict(d).pre_run is None


# ── security: pre_run must NOT be LLM-callable ───────────────────────


class TestPreRunNotAgentCallable:
    def test_schedule_add_rejects_pre_run_kwarg(self):
        """The agent-callable tool must not accept arbitrary shell commands.

        An LLM under prompt injection should be unable to persist a host-side
        shell command via the tool surface; ``pre_run`` is CLI/Python-only.
        """
        import inspect
        from praisonaiagents.tools.schedule_tools import schedule_add

        params = inspect.signature(schedule_add).parameters
        assert "pre_run" not in params
        assert "condition" not in params
