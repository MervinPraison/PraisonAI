"""
Unit tests for the scheduler pre-run condition gate.

Covers:
- ``ShellConditionGate`` decisions (run / skip / context / timeout / no command)
- ``ScheduledAgentExecutor`` enforcement: gate skips the model turn, gate
  context is appended to the message, gate failures fall back to running,
  and gating can be disabled.
"""

import asyncio
import inspect
import socket
import time
from dataclasses import dataclass
from typing import Any

import pytest
from praisonai.scheduler.condition_gate import MonitorGate, ShellConditionGate
from praisonai.scheduler.executor import ScheduledAgentExecutor
from praisonaiagents.scheduler.protocols import GateResult, JobConditionProtocol

# ── lightweight fakes ────────────────────────────────────────────────


@dataclass
class FakeJob:
    id: str = "job1"
    name: str = "test-job"
    message: str = "do the thing"
    agent_id: str | None = None
    session_target: str = "isolated"
    delivery: Any = None
    pre_run: str | None = None
    condition: str | None = None
    monitor: dict | None = None


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


class TestMonitorGate:
    @pytest.mark.parametrize("monitor", ["command", [], {}, {"command": "x", "url": "https://example.com"}])
    def test_invalid_monitor_spec_fails_closed(self, monitor):
        decision = MonitorGate().should_run(FakeJob(monitor=monitor), state={})

        assert decision.run is False
        assert decision.no_change is False
        assert "monitor" in (decision.reason or "")
        assert decision.state_updates is None

    def test_first_command_observation_runs_and_stores_watermark(self):
        gate = MonitorGate()
        decision = gate.should_run(
            FakeJob(monitor={"command": "printf watched-value"}), state={},
        )

        assert decision.run is True
        assert decision.context == "watched-value"
        assert decision.state_updates == {
            "monitor_sha256": (
                "0e05219c99c1ee894858c495940c8d745b61ae77dc2430568a31df2d3932b2c3"
            ),
            "monitor_output": "watched-value",
        }

    def test_unchanged_command_suppresses_tick(self):
        gate = MonitorGate()
        first = gate.should_run(
            FakeJob(monitor={"command": "printf watched-value"}), state={},
        )
        decision = gate.should_run(
            FakeJob(monitor={"command": "printf watched-value"}),
            state=first.state_updates,
        )

        assert decision.run is False
        assert decision.no_change is True
        assert decision.reason == "monitor source unchanged"
        assert decision.state_updates is None

    def test_changed_command_runs_with_previous_and_current_context(self):
        gate = MonitorGate()
        decision = gate.should_run(
            FakeJob(monitor={"command": "printf new-value"}),
            state={
                "monitor_sha256": "old-digest",
                "monitor_output": "old-value",
            },
        )

        assert decision.run is True
        assert "--- previous" in (decision.context or "")
        assert "+++ current" in (decision.context or "")
        assert "-old-value" in (decision.context or "")
        assert "+new-value" in (decision.context or "")
        assert len(decision.context or "") <= 8000
        assert decision.state_updates["monitor_output"] == "new-value"

    def test_change_beyond_retained_preview_has_context(self, monkeypatch):
        gate = MonitorGate()
        previous = "x" * 2048
        monkeypatch.setattr(gate, "_fetch_url", lambda _url: previous + "new")

        decision = gate.should_run(
            FakeJob(monitor={"url": "https://example.com/value"}),
            state={
                "monitor_sha256": "old-digest",
                "monitor_output": previous,
            },
        )

        assert decision.run is True
        assert decision.context == "Monitor output changed outside retained preview."

    def test_persisted_preview_is_bounded_by_utf8_bytes(self, monkeypatch):
        gate = MonitorGate()
        monkeypatch.setattr(gate, "_fetch_url", lambda _url: "界" * 3000)

        decision = gate.should_run(
            FakeJob(monitor={"url": "https://example.com/value"}), state={},
        )

        preview = decision.state_updates["monitor_output"]
        assert len(preview.encode("utf-8")) <= 2048

    def test_command_timeout_does_not_replace_watermark(self):
        decision = MonitorGate(timeout=0.05).should_run(
            FakeJob(monitor={"command": "sleep 5"}),
            state={"monitor_sha256": "keep-me"},
        )

        assert decision.run is False
        assert "timed out" in (decision.reason or "")
        assert decision.state_updates is None

    def test_command_output_limit_does_not_replace_watermark(self):
        decision = MonitorGate().should_run(
            FakeJob(
                monitor={
                    "command": "head -c 9000 /dev/zero | tr '\\0' x",
                },
            ),
            state={"monitor_sha256": "keep-me"},
        )

        assert decision.run is False
        assert "exceeded" in (decision.reason or "")
        assert decision.state_updates is None

    def test_url_observation_uses_same_change_contract(self, monkeypatch):
        gate = MonitorGate()
        monkeypatch.setattr(gate, "_fetch_url", lambda _url: "url-value")

        first = gate.should_run(
            FakeJob(monitor={"url": "https://example.com/value"}), state={},
        )
        second = gate.should_run(
            FakeJob(monitor={"url": "https://example.com/value"}),
            state=first.state_updates,
        )

        assert first.run is True
        assert first.context == "url-value"
        assert second.no_change is True

    def test_url_connects_to_validated_address(self, monkeypatch):
        gate = MonitorGate()
        captured = {}
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            ],
        )
        monkeypatch.setattr(
            gate,
            "_request_url",
            lambda parsed, address: captured.update(
                hostname=parsed.hostname, address=address,
            ) or b"value",
        )

        assert gate._fetch_url("https://example.com/value") == "value"
        assert captured == {
            "hostname": "example.com",
            "address": "93.184.216.34",
        }

    def test_read_bounded_enforces_total_deadline(self):
        class _DripResponse:
            def read(self, _amount):
                return b"x"

        gate = MonitorGate()
        with pytest.raises(TimeoutError):
            gate._read_bounded(_DripResponse(), deadline=time.monotonic() - 1)

    def test_read_bounded_returns_full_body(self):
        class _OneShotResponse:
            def __init__(self):
                self._sent = False

            def read(self, _amount):
                if self._sent:
                    return b""
                self._sent = True
                return b"payload"

        gate = MonitorGate()
        body = gate._read_bounded(
            _OneShotResponse(), deadline=time.monotonic() + 30,
        )
        assert body == b"payload"

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "http://127.0.0.1/private",
            "http://169.254.169.254/latest/meta-data",
            "http://user:password@example.com/",
        ],
    )
    def test_url_rejects_unsafe_targets(self, url):
        decision = MonitorGate().should_run(
            FakeJob(monitor={"url": url}), state={},
        )

        assert decision.run is False
        assert "invalid monitor URL" in (decision.reason or "")
        assert decision.state_updates is None

    def test_failed_probe_does_not_replace_watermark(self):
        decision = MonitorGate().should_run(
            FakeJob(monitor={"command": "exit 2"}),
            state={"monitor_sha256": "keep-me"},
        )

        assert decision.run is False
        assert decision.no_change is False
        assert decision.state_updates is None


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
        from praisonaiagents.tools.schedule_tools import schedule_add

        params = inspect.signature(schedule_add).parameters
        assert "pre_run" not in params
        assert "condition" not in params

    def test_schedule_add_does_not_expose_monitor_sources(self):
        from praisonaiagents.tools.schedule_tools import schedule_add

        params = inspect.signature(schedule_add).parameters
        assert "monitor" not in params
        assert "monitor_command" not in params
        assert "monitor_url" not in params


class TestMonitorCli:
    def test_monitor_command_is_persisted_by_trusted_cli(self, monkeypatch):
        import praisonaiagents.tools.schedule_tools as tools
        from praisonai.cli.commands.schedule import app
        from typer.testing import CliRunner

        job = FakeJob()
        job.id = "new-job-id"

        class FakeStore:
            def get(self, job_id):
                assert job_id == "new-job-id"
                return job

            def update(self, _job):
                return None

        monkeypatch.setattr(
            tools,
            "schedule_add",
            lambda **kwargs: f"Schedule '{kwargs['name']}' added (id: new-job-id, */5m)",
        )
        monkeypatch.setattr(tools, "_get_store", lambda: FakeStore())

        result = CliRunner().invoke(
            app,
            [
                "add", "price-watch", "--schedule", "*/5m",
                "--message", "summarise the change",
                "--monitor-command", "printf price",
            ],
        )

        assert result.exit_code == 0, result.stdout
        assert job.monitor == {"command": "printf price"}

    def test_monitor_url_is_persisted_by_trusted_cli(self, monkeypatch):
        import praisonaiagents.tools.schedule_tools as tools
        from praisonai.cli.commands.schedule import app
        from typer.testing import CliRunner

        job = FakeJob()
        job.id = "new-job-id"

        class FakeStore:
            def get(self, job_id):
                assert job_id == "new-job-id"
                return job

            def update(self, _job):
                return None

        monkeypatch.setattr(
            tools,
            "schedule_add",
            lambda **kwargs: f"Schedule '{kwargs['name']}' added (id: new-job-id, */5m)",
        )
        monkeypatch.setattr(tools, "_get_store", lambda: FakeStore())

        result = CliRunner().invoke(
            app,
            [
                "add", "price-watch", "--schedule", "*/5m",
                "--message", "summarise the change",
                "--monitor-url", "https://example.com/price",
            ],
        )

        assert result.exit_code == 0, result.stdout
        assert job.monitor == {"url": "https://example.com/price"}

    def test_monitor_sources_are_mutually_exclusive(self):
        from praisonai.cli.commands.schedule import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(
            app,
            [
                "add", "watch", "--schedule", "hourly",
                "--monitor-command", "printf value",
                "--monitor-url", "https://example.com/value",
            ],
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.stdout

    @pytest.mark.parametrize("conflict", ["--pre-run", "--command", "--backend"])
    def test_monitor_rejects_conflicting_execution_modes(self, conflict):
        from praisonai.cli.commands.schedule import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(
            app,
            [
                "add", "watch", "--schedule", "hourly",
                "--monitor-command", "printf value", conflict, "other",
            ],
        )

        assert result.exit_code == 1
        assert "cannot be combined" in result.stdout
