"""
Unit tests for per-job model pin + drift guard on scheduled jobs.

An unattended job created against one model must not silently start running on
whatever the default later becomes. Covers:

- core round-trip: provider/model/pin_model serialise and restore
- backward-compat: a job with no snapshot enforces nothing and runs
- drift fails closed: a pinned job whose resolved agent drifted is recorded
  failed (and delivered) with no model turn taken
- pin holds: a pinned job with no drift runs, with the agent pinned to snapshot
- --no-pin follows: an unpinned snapshot never fails closed
"""

import asyncio
from typing import List, Optional

from praisonaiagents.scheduler.models import (
    ScheduleJob,
    Schedule,
    DeliveryTarget,
)
from praisonai.scheduler.executor import ScheduledAgentExecutor
from praisonai.scheduler.run_policy import RunPolicy


class FakeRunner:
    def __init__(self):
        self.runs: List[dict] = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


class FakeAgent:
    def __init__(self, llm: str):
        self.llm = llm
        self.chats: List[str] = []

    def chat(self, message, **kwargs):
        self.chats.append(message)
        return f"ran on {self.llm}"


def _run(coro):
    return asyncio.run(coro)


def _executor(agent, delivered: Optional[list] = None, run_policy=None):
    async def deliver(target, text):
        if delivered is not None:
            delivered.append((target, text))

    return ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: agent,
        delivery_handler=deliver,
        run_policy=run_policy,
    )


def _job(model=None, provider=None, pin_model=True, deliver="telegram:-100"):
    return ScheduleJob(
        name="pinned",
        schedule=Schedule(kind="every", every_seconds=1),
        message="do the thing",
        model=model,
        provider=provider,
        pin_model=pin_model,
        delivery=DeliveryTarget.parse(deliver),
    )


# ── core round-trip ──────────────────────────────────────────────────


def test_snapshot_round_trips():
    job = ScheduleJob(name="j", model="gpt-4o-mini", provider="openai")
    restored = ScheduleJob.from_dict(job.to_dict())
    assert restored.model == "gpt-4o-mini"
    assert restored.provider == "openai"
    assert restored.pin_model is True


def test_no_snapshot_is_not_serialised():
    d = ScheduleJob(name="j").to_dict()
    assert "model" not in d
    assert "provider" not in d
    assert "pin_model" not in d


def test_no_pin_round_trips():
    job = ScheduleJob(name="j", model="gpt-4o-mini", pin_model=False)
    d = job.to_dict()
    assert d["model"] == "gpt-4o-mini"
    assert d["pin_model"] is False
    assert ScheduleJob.from_dict(d).pin_model is False


# ── executor behaviour ───────────────────────────────────────────────


def test_no_snapshot_runs_backward_compatible():
    agent = FakeAgent(llm="gpt-4o")
    ex = _executor(agent)
    result = _run(ex._execute_one(_job(model=None)))
    assert result.status == "succeeded"
    assert agent.chats == ["do the thing"]


def test_drift_fails_closed_no_model_turn():
    # Job pinned to a cheap model; resolver now hands back a pricier default.
    agent = FakeAgent(llm="gpt-4o")
    ex = _executor(agent)
    result = _run(ex._execute_one(_job(model="gpt-4o-mini")))
    assert result.status == "failed"
    assert "model drift" in (result.error or "")
    assert agent.chats == []  # no model turn taken


def test_drift_delivers_failure_summary_with_run_policy():
    # Fail-closed *delivery* is a RunPolicy concern: with deliver_on_failure a
    # drift-blocked run also reports the failure to the delivery target.
    agent = FakeAgent(llm="gpt-4o")
    delivered: list = []
    ex = _executor(agent, delivered, run_policy=RunPolicy(deliver_on_failure=True))
    result = _run(ex._execute_one(_job(model="gpt-4o-mini")))
    assert result.status == "failed"
    assert agent.chats == []
    assert delivered and "failed" in delivered[-1][1]


def test_pin_holds_when_no_drift():
    agent = FakeAgent(llm="gpt-4o-mini")
    ex = _executor(agent)
    result = _run(ex._execute_one(_job(model="gpt-4o-mini")))
    assert result.status == "succeeded"
    assert agent.chats == ["do the thing"]
    assert agent.llm == "gpt-4o-mini"


def test_no_pin_follows_default():
    # Snapshot present but pin_model=False → drift is tolerated, run proceeds.
    agent = FakeAgent(llm="gpt-4o")
    ex = _executor(agent)
    result = _run(ex._execute_one(_job(model="gpt-4o-mini", pin_model=False)))
    assert result.status == "succeeded"
    assert agent.chats == ["do the thing"]


def test_provider_only_snapshot_does_not_false_drift():
    # Model matches; the agent exposes no provider, so a provider snapshot must
    # not fire drift on its own.
    agent = FakeAgent(llm="gpt-4o-mini")
    ex = _executor(agent)
    result = _run(ex._execute_one(_job(model="gpt-4o-mini", provider="openai")))
    assert result.status == "succeeded"
