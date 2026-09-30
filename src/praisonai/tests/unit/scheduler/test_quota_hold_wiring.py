"""Executor wiring for the provider-quota-aware schedule hold (Issue #5386).

A scheduled run that fails with a provider 429/quota signal must park the job
past the provider's reset window (so it stops re-firing every tick) and clear
the hold on the first run that reaches the model. Covers:

- a rate-limit failure sets ``job.hold_until`` past the Retry-After window
- ``hold_on_rate_limit=False`` disables the park (prior behaviour)
- a non-quota failure never parks
- a subsequent success clears a prior hold (window reopened)
"""

import asyncio
from typing import List, Optional

from praisonaiagents.scheduler.models import DeliveryTarget, Schedule, ScheduleJob
from praisonai.scheduler.executor import ScheduledAgentExecutor
from praisonai.scheduler.run_policy import RunPolicy


class _RateLimited(Exception):
    def __init__(self, retry_after=3600):
        super().__init__("Rate limit exceeded (429)")
        self.status_code = 429

        class _Resp:
            headers = {"retry-after": str(retry_after)}

        self.response = _Resp()


class FakeRunner:
    def __init__(self):
        self.runs: List[dict] = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


class FakeAgent:
    def __init__(self, error: Optional[Exception] = None):
        self._error = error
        self.chats: List[str] = []

    def chat(self, message, **kwargs):
        self.chats.append(message)
        if self._error is not None:
            raise self._error
        return "ok"


def _run(coro):
    return asyncio.run(coro)


def _executor(agent, run_policy=None):
    return ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: agent,
        run_policy=run_policy,
    )


def _job():
    return ScheduleJob(
        name="quota-job",
        schedule=Schedule(kind="every", every_seconds=1),
        message="do it",
    )


def test_rate_limit_failure_parks_job():
    job = _job()
    ex = _executor(FakeAgent(_RateLimited(3600)), RunPolicy(hold_slack_seconds=60.0))
    result = _run(ex._execute_one(job))
    assert result.status == "failed"
    assert job.hold_until is not None
    # Parked ~Retry-After + slack into the future.
    import time

    assert job.hold_until > time.time() + 3000


def test_hold_disabled_does_not_park():
    job = _job()
    ex = _executor(FakeAgent(_RateLimited(3600)), RunPolicy(hold_on_rate_limit=False))
    _run(ex._execute_one(job))
    assert job.hold_until is None


def test_non_quota_failure_does_not_park():
    job = _job()
    ex = _executor(FakeAgent(ValueError("bad request")), RunPolicy())
    _run(ex._execute_one(job))
    assert job.hold_until is None


def test_success_clears_prior_hold():
    job = _job()
    job.hold_until = 9_999_999_999.0  # far-future park from a prior 429
    ex = _executor(FakeAgent(), RunPolicy())
    result = _run(ex._execute_one(job))
    assert result.status == "succeeded"
    assert job.hold_until is None


def test_no_policy_no_park():
    # Without a run policy the hold path is inert (opt-in via RunPolicy).
    job = _job()
    ex = _executor(FakeAgent(_RateLimited(3600)))
    _run(ex._execute_one(job))
    assert job.hold_until is None
