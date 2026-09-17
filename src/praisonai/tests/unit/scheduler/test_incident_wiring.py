"""
Unit tests for incident-aware failure delivery in ``ScheduledAgentExecutor``.

The core :class:`IncidentTracker` (``praisonaiagents.scheduler.incidents``) is
the shipped alert-fatigue brain; these tests cover the wrapper wiring that
feeds each run outcome to it and delivers a failure summary **only when an
alert is due**:

- a distinct error alerts once; the same error on later ticks stays silent
- a genuinely different error mints a new incident and re-alerts
- the next success emits a single "recovered" note
- ``alert_after_failures`` tolerates transient blips (alert on the Nth failure)
- without a state store, latching is unavailable and the prior
  send-on-every-failure behaviour is preserved (no regression)
- disabled (``deliver_on_failure=False``) is a no-op
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from praisonai.scheduler.executor import ScheduledAgentExecutor
from praisonai.scheduler.run_policy import RunPolicy


@dataclass
class FakeDelivery:
    channel: str = "telegram"
    channel_id: str = "123"


@dataclass
class FakeJob:
    id: str = "job1"
    name: str = "test-job"
    message: str = "do the thing"
    agent_id: Optional[str] = None
    session_target: str = "isolated"
    delivery: Any = field(default_factory=FakeDelivery)
    pre_run: Optional[str] = None
    monitor: Optional[Dict[str, Any]] = None
    delete_after_run: bool = False


class FakeAgent:
    """Agent whose ``chat`` raises when ``fail`` is set (drives a failed run)."""

    def __init__(self):
        self.tools = []
        self.fail: Optional[str] = None

    def chat(self, message):
        if self.fail is not None:
            raise RuntimeError(self.fail)
        return f"answer: {message}"


class FakeStateStore:
    def __init__(self):
        self.states: Dict[str, Dict] = {}

    def get_state(self, job_id: str) -> Dict:
        return dict(self.states.get(job_id, {}))

    def set_state(self, job_id: str, state: Dict) -> None:
        self.states[job_id] = dict(state)

    def clear_state(self, job_id: str) -> None:
        self.states.pop(job_id, None)


class FakeRunner:
    def __init__(self, store=None):
        self.runs = []
        self._store = store

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})

    def get_due_jobs(self):
        return []


def _make(store=None, after=1, deliver=True):
    agent = FakeAgent()
    deliveries: List[Tuple[Any, str]] = []

    async def handler(delivery, text):
        deliveries.append((delivery, text))
        return True

    executor = ScheduledAgentExecutor(
        runner=FakeRunner(store),
        agent_resolver=lambda _id: agent,
        delivery_handler=handler,
        run_policy=RunPolicy(
            deliver_on_failure=deliver,
            alert_after_failures=after,
            scan_assembled_prompt=False,
        ),
    )
    return executor, agent, deliveries


def _run_success(executor, job):
    return asyncio.run(executor._execute_one(job))


def _run_failure(executor, agent, job, error):
    agent.fail = error
    try:
        return asyncio.run(executor._execute_one(job))
    finally:
        agent.fail = None


async def _tick_success(executor, job):
    """Route a success through ``tick`` so the recovery observer fires."""
    result = await executor._execute_one(job)
    if getattr(result, "status", None) == "succeeded":
        await executor._maybe_deliver_recovery(job, result)
    return result


def _alerts(deliveries):
    """Only the failure-alert sends (a success delivers its own output too)."""
    return [t for _d, t in deliveries if t.startswith("⚠️")]


def _recoveries(deliveries):
    return [t for _d, t in deliveries if t.startswith("✅")]


class TestFailureLatching:
    def test_same_error_alerts_once(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store)
        job = FakeJob()

        r1 = _run_failure(executor, agent, job, "401 unauthorised")
        r2 = _run_failure(executor, agent, job, "401 unauthorised")
        r3 = _run_failure(executor, agent, job, "401 unauthorised")

        assert r1.status == "failed"
        # Alerted exactly once for the repeated identical error.
        assert len(deliveries) == 1
        assert "failed" in deliveries[0][1]
        # Only the first delivered send flips ``delivered``.
        assert r1.delivered is True
        assert r2.delivered is False
        assert r3.delivered is False

    def test_changed_error_realerts(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store)
        job = FakeJob()

        _run_failure(executor, agent, job, "401 unauthorised")
        _run_failure(executor, agent, job, "401 unauthorised")
        _run_failure(executor, agent, job, "500 server error")

        assert len(deliveries) == 2
        assert "401" in deliveries[0][1]
        assert "500" in deliveries[1][1]

    def test_volatile_token_does_not_realert(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store)
        job = FakeJob()

        _run_failure(executor, agent, job, "429 rate limit (req id abcdef123456)")
        _run_failure(executor, agent, job, "429 rate limit (req id zzzzzz987654)")

        # Both collapse to one signature → a single alert.
        assert len(deliveries) == 1


class TestRecovery:
    def test_success_after_alert_sends_recovery(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store)
        job = FakeJob()

        _run_failure(executor, agent, job, "401 unauthorised")
        assert len(_alerts(deliveries)) == 1

        asyncio.run(_tick_success(executor, job))
        assert len(_recoveries(deliveries)) == 1
        assert "recovered" in _recoveries(deliveries)[0]

    def test_success_without_prior_alert_is_silent(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store)
        job = FakeJob()

        asyncio.run(_tick_success(executor, job))
        assert _alerts(deliveries) == []
        assert _recoveries(deliveries) == []

    def test_recovery_then_new_failure_realerts(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store)
        job = FakeJob()

        _run_failure(executor, agent, job, "401 unauthorised")
        asyncio.run(_tick_success(executor, job))
        _run_failure(executor, agent, job, "401 unauthorised")

        assert len(_alerts(deliveries)) == 2       # alert, alert-again
        assert len(_recoveries(deliveries)) == 1   # one recovery in between


class TestThreshold:
    def test_after_failures_tolerates_a_blip(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store, after=2)
        job = FakeJob()

        _run_failure(executor, agent, job, "timeout")
        assert deliveries == []  # first failure tolerated
        _run_failure(executor, agent, job, "timeout")
        assert len(deliveries) == 1  # alert on the 2nd consecutive failure


class TestFallbackAndDisabled:
    def test_no_state_store_sends_every_failure(self):
        # No state store → tracker cannot latch → prior behaviour preserved.
        executor, agent, deliveries = _make(store=None)
        job = FakeJob()

        _run_failure(executor, agent, job, "401 unauthorised")
        _run_failure(executor, agent, job, "401 unauthorised")

        assert len(deliveries) == 2

    def test_disabled_is_noop(self):
        store = FakeStateStore()
        executor, agent, deliveries = _make(store, deliver=False)
        job = FakeJob()

        _run_failure(executor, agent, job, "401 unauthorised")
        asyncio.run(_tick_success(executor, job))

        assert _alerts(deliveries) == []
        assert _recoveries(deliveries) == []
