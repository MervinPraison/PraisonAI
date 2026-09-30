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


# ── hold-notice delivery (greptile #3) ───────────────────────────────


class _StatefulRunner(FakeRunner):
    """Runner whose store supports per-job state (enables the incident tracker)."""

    def __init__(self):
        super().__init__()

        class _Store:
            def __init__(self):
                self._state = {}

            def get_state(self, job_id):
                return dict(self._state.get(job_id, {}))

            def set_state(self, job_id, state):
                self._state[job_id] = dict(state)

        self._store = _Store()


def _job_with_delivery():
    return ScheduleJob(
        name="quota-job",
        schedule=Schedule(kind="every", every_seconds=1),
        message="do it",
        delivery=DeliveryTarget(channel="slack", channel_id="C1"),
    )


def test_hold_notice_delivered_even_below_alert_threshold():
    # greptile #3: with ``alert_after_failures`` > 1 the first quota failure
    # parks the job but its incident is still below the *failure*-alert
    # threshold. The hold is nonetheless a distinct state emitted once per
    # window (is_due coalesces the rest), so the operator must still be told —
    # the notice must NOT be gated on the failure-alert threshold.
    sent: List[str] = []

    def deliver(_target, text):
        sent.append(text)
        return True

    runner = _StatefulRunner()
    ex = ScheduledAgentExecutor(
        runner=runner,
        agent_resolver=lambda aid: FakeAgent(),
        run_policy=RunPolicy(alert_after_failures=5),
        delivery_handler=deliver,
    )
    job = _job_with_delivery()
    from praisonai_bot.scheduler.executor import JobResult

    result = JobResult(job=job, status="failed", error="429", duration=0.0)
    _run(ex._maybe_deliver_hold(job, result, held_until=9_999_999_999.0))

    assert len(sent) == 1
    assert "held until" in sent[0]
