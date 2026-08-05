"""
Unit tests for the no-LLM command action on scheduled jobs.

A job carrying a ``command`` runs that shell command on its schedule and
delivers stdout verbatim to its ``DeliveryTarget`` — with no agent resolved and
no model turn taken. Covers:

- success: stdout delivered verbatim, status ``succeeded``
- non-zero exit: exit code + output surfaced (not silently dropped), delivered
- timeout: command killed, status ``failed`` within the bound
- model-free: a command job runs even when the agent resolver returns ``None``
- backward-compat: a job without ``command`` still takes the agent path
"""

import asyncio
import sys
import time
from typing import List, Optional

import pytest

from praisonaiagents.scheduler.models import (
    ScheduleJob,
    Schedule,
    DeliveryTarget,
)
from praisonai.scheduler.executor import ScheduledAgentExecutor


class FakeRunner:
    def __init__(self):
        self.runs: List[dict] = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


def _run(coro):
    return asyncio.run(coro)


def _executor(delivered, resolver=None):
    async def deliver(target, text):
        delivered.append((target, text))

    return ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=resolver or (lambda aid: None),
        delivery_handler=deliver,
    )


def _cmd_job(command, timeout=60.0, deliver="telegram:-100"):
    return ScheduleJob(
        name="cmd",
        schedule=Schedule(kind="every", every_seconds=1),
        command=command,
        command_timeout=timeout,
        delivery=DeliveryTarget.parse(deliver),
    )


def test_command_success_delivered_verbatim():
    delivered: list = []
    ex = _executor(delivered)
    job = _cmd_job(f'{sys.executable} -c "print(\'l1\'); print(\'l2\')"')
    result = _run(ex._execute_one(job))
    assert result.status == "succeeded"
    assert result.result == "l1\nl2"
    assert result.delivered is True
    assert delivered[-1][1] == "l1\nl2"


def test_command_nonzero_exit_surfaced():
    delivered: list = []
    ex = _executor(delivered)
    job = _cmd_job(f'{sys.executable} -c "import sys; sys.stderr.write(\'boom\'); sys.exit(3)"')
    result = _run(ex._execute_one(job))
    assert result.status == "failed"
    assert result.error.startswith("[exit 3]")
    assert "boom" in result.error
    # Failure output is still delivered rather than silently dropped.
    assert result.delivered is True


def test_command_timeout_killed_within_bound():
    delivered: list = []
    ex = _executor(delivered)
    started = time.time()
    job = _cmd_job(f'{sys.executable} -c "import time; time.sleep(5)"', timeout=1.0)
    result = _run(ex._execute_one(job))
    assert result.status == "failed"
    assert "124" in result.error and "timed out" in result.error
    assert time.time() - started < 4.0


def test_command_runs_without_agent():
    # The agent resolver returns None; an agent-only job would fail here, but a
    # command job runs model-free regardless.
    delivered: list = []
    ex = _executor(delivered, resolver=lambda aid: None)
    job = _cmd_job(f'{sys.executable} -c "print(\'ok\')"')
    result = _run(ex._execute_one(job))
    assert result.status == "succeeded"
    assert result.result == "ok"


def test_no_command_still_takes_agent_path():
    # A job without a command and no resolvable agent hits the existing hard
    # error — proving the command branch did not swallow the agent path.
    delivered: list = []
    ex = _executor(delivered, resolver=lambda aid: None)
    job = ScheduleJob(
        name="agent-job",
        schedule=Schedule(kind="every", every_seconds=1),
        message="do the thing",
        agent_id="ops",
    )
    result = _run(ex._execute_one(job))
    assert result.status == "failed"
    assert "No agent found" in (result.error or "")


def test_command_round_trips_through_store_schema():
    job = _cmd_job("df -h /", timeout=15.0)
    restored = ScheduleJob.from_dict(job.to_dict())
    assert restored.command == "df -h /"
    assert restored.command_timeout == 15.0
