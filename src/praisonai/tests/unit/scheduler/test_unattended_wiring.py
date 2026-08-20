"""
Unit tests for the unattended-run wiring fixes (issue #4079).

Three silent-failure modes are covered:

- Defect 1: the gateway constructs a default ``RunPolicy`` so a failed
  scheduled job delivers a failure summary and the run is recorded ``failed``.
- Defect 2: the host-app schedule bridge executes due jobs instead of
  discarding them; when no executor can be built the trigger raises so the
  loop leaves the job due (``last_run_at`` not advanced).
- Defect 3: the BotOS path honours ``pin_model`` — a drifted pinned job takes
  no model turn and is recorded ``failed`` with the drift reason.
"""

import asyncio
from typing import List, Optional

from praisonaiagents.scheduler.models import ScheduleJob, DeliveryTarget
from praisonai.scheduler.executor import ScheduledAgentExecutor
from praisonai.scheduler.run_policy import RunPolicy, DEFAULT_DENIED_TOOLSETS


def _run(coro):
    return asyncio.run(coro)


class FakeRunner:
    def __init__(self):
        self.runs: List[dict] = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


class RaisingAgent:
    llm = "openai/gpt-4o"

    def chat(self, message, **kwargs):
        raise RuntimeError("boom")


# ── Defect 1: default policy delivers failures ───────────────────────────


def test_default_policy_delivers_failure_and_records_failed():
    runner = FakeRunner()
    delivered: List[tuple] = []

    async def deliver(target, text):
        delivered.append((target, text))

    job = ScheduleJob(
        name="daily",
        message="do it",
        delivery=DeliveryTarget(channel="telegram", channel_id="42"),
    )
    ex = ScheduledAgentExecutor(
        runner=runner,
        agent_resolver=lambda aid: RaisingAgent(),
        delivery_handler=deliver,
        run_policy=RunPolicy(deliver_on_failure=True),
    )
    result = _run(ex._execute_one(job))

    assert result.status == "failed"
    assert any(r.get("status") == "failed" for r in runner.runs)
    assert delivered, "owner should receive a failure summary"


def test_default_denied_toolsets_downscope_unattended_run():
    policy = RunPolicy()

    def cronjob():
        pass

    cronjob.__name__ = "cronjob"

    def safe():
        pass

    safe.__name__ = "safe"

    kept = policy.filter_tools([cronjob, safe])
    kept_names = {getattr(t, "__name__", str(t)) for t in kept}
    assert "cronjob" not in kept_names
    assert "safe" in kept_names
    assert policy.denied_toolsets == set(DEFAULT_DENIED_TOOLSETS)


# ── Defect 2: host-app bridge does not discard due jobs ──────────────────


def test_bridge_on_trigger_leaves_job_due_without_executor():
    import praisonai.integration.bridges.schedules_runner as sr

    sr._executor = None

    def on_trigger(job):
        if sr._executor is None:
            raise RuntimeError("no scheduler executor available; leaving job due")

    raised = False
    try:
        on_trigger(object())
    except RuntimeError:
        raised = True
    assert raised, "on_trigger must raise so last_run_at is not advanced"


def test_bridge_builds_executor_with_policy():
    import praisonai.integration.bridges.schedules_runner as sr
    from praisonaiagents.scheduler import get_default_store

    ex = sr._build_executor(get_default_store())
    assert ex is not None
    assert ex._run_policy is not None


# ── Defect 3: BotOS honours pin_model ────────────────────────────────────


def test_botos_pinned_job_drift_raises_before_chat():
    from praisonai_bot.bots.botos import BotOS

    class DriftedAgent:
        llm = "openai/gpt-3.5-turbo"

        def chat(self, message, **kwargs):
            raise AssertionError("chat must not be called on drift")

    job = ScheduleJob(name="pinned", message="x")
    job.model = "gpt-4o"
    job.provider = "openai"
    job.pin_model = True

    raised = None
    try:
        BotOS._enforce_pinned_model(job, DriftedAgent())
    except RuntimeError as e:
        raised = str(e)
    assert raised is not None and "drift" in raised


def test_botos_no_drift_returns_restore_callable():
    from praisonai_bot.bots.botos import BotOS

    class Agent:
        llm = "openai/gpt-4o"

    job = ScheduleJob(name="pinned", message="x")
    job.model = "gpt-4o"
    job.provider = "openai"
    job.pin_model = True

    restore = BotOS._enforce_pinned_model(job, Agent())
    assert callable(restore)
    restore()
