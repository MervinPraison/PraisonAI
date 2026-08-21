"""
Unit tests for cross-run memory wiring in ``ScheduledAgentExecutor``.

Covers:
- prior state is injected as a compact notepad block into the agent prompt
- agent-emitted ``state_updates`` / ``state`` are merged + persisted
- a stateful monitor gate's ``state_updates`` persist even on a suppressed
  (``no_change`` / skip) tick, and are folded into the notepad on a go tick
- stateless behaviour is preserved when the store has no state support
  (no notepad, no writes) and when a legacy gate ignores ``state=``
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from praisonaiagents.scheduler.protocols import GateResult
from praisonai.scheduler.executor import ScheduledAgentExecutor


@dataclass
class FakeJob:
    id: str = "job1"
    name: str = "test-job"
    message: str = "do the thing"
    agent_id: Optional[str] = None
    session_target: str = "isolated"
    delivery: Any = None
    pre_run: Optional[str] = None
    monitor: Optional[Dict[str, Any]] = None
    delete_after_run: bool = False


class FakeAgent:
    def __init__(self, emit_state: Optional[Dict] = None):
        self.tools = []
        self.last_message = None
        self._emit_state = emit_state

    def chat(self, message):
        self.last_message = message
        if self._emit_state is not None:
            class Result(str):
                state_updates: Dict[str, Any]
            r = Result(f"answer: {message}")
            r.state_updates = self._emit_state
            return r
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


def _run(executor, job):
    return asyncio.run(executor._execute_one(job))


class TestNotepadInjection:
    def test_prior_state_injected_as_notepad(self):
        store = FakeStateStore()
        store.set_state("job1", {"last_seen_pr": 4821})
        agent = FakeAgent()
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store), agent_resolver=lambda _id: agent,
        )
        result = _run(executor, FakeJob(message="List PRs"))
        assert result.status == "succeeded"
        assert "Notepad (state since last run):" in agent.last_message
        assert "last_seen_pr=4821" in agent.last_message
        assert agent.last_message.endswith("List PRs")

    def test_no_notepad_without_state(self):
        agent = FakeAgent()
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(FakeStateStore()), agent_resolver=lambda _id: agent,
        )
        _run(executor, FakeJob(message="hi"))
        assert agent.last_message == "hi"

    def test_no_notepad_when_store_unsupported(self):
        agent = FakeAgent()
        # FakeRunner with a store lacking get_state/set_state
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(object()), agent_resolver=lambda _id: agent,
        )
        _run(executor, FakeJob(message="hi"))
        assert agent.last_message == "hi"


class TestAgentEmittedState:
    def test_agent_state_persisted(self):
        store = FakeStateStore()
        agent = FakeAgent(emit_state={"last_seen_pr": 4839})
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store), agent_resolver=lambda _id: agent,
        )
        _run(executor, FakeJob(message="go"))
        assert store.get_state("job1") == {"last_seen_pr": 4839}

    def test_agent_state_merges_with_prior(self):
        store = FakeStateStore()
        store.set_state("job1", {"a": 1, "last_seen_pr": 1})
        agent = FakeAgent(emit_state={"last_seen_pr": 2})
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store), agent_resolver=lambda _id: agent,
        )
        _run(executor, FakeJob(message="go"))
        assert store.get_state("job1") == {"a": 1, "last_seen_pr": 2}

    def test_one_shot_job_does_not_recreate_state(self):
        # A ``delete_after_run`` job is already removed from the store (and its
        # state popped) by claim_due before it runs; persisting agent-emitted
        # state here would leave an orphan entry nothing cleans up.
        store = FakeStateStore()
        agent = FakeAgent(emit_state={"last_seen_pr": 4839})
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store), agent_resolver=lambda _id: agent,
        )
        _run(executor, FakeJob(message="go", delete_after_run=True))
        assert store.get_state("job1") == {}

    def test_plain_string_result_writes_nothing(self):
        store = FakeStateStore()
        store.set_state("job1", {"a": 1})
        agent = FakeAgent()  # returns a plain string
        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store), agent_resolver=lambda _id: agent,
        )
        _run(executor, FakeJob(message="go"))
        assert store.get_state("job1") == {"a": 1}


class TestGateState:
    def test_default_monitor_gate_suppresses_unchanged_tick(self):
        store = FakeStateStore()
        agent = FakeAgent()
        runner = FakeRunner(store)
        executor = ScheduledAgentExecutor(
            runner=runner, agent_resolver=lambda _id: agent,
        )
        job = FakeJob(
            message="watch",
            monitor={"command": "printf stable-value"},
        )

        first = _run(executor, job)
        agent.last_message = None
        second = _run(executor, job)

        assert first.status == "succeeded"
        assert second.status == "no_change"
        assert agent.last_message is None
        assert runner.runs[-1]["status"] == "no_change"

    def test_stateful_gate_persists_on_no_change_suppression(self):
        store = FakeStateStore()
        agent = FakeAgent()

        class MonitorGate:
            def should_run(self, job, *, state=None):
                return GateResult(
                    no_change=True,
                    reason="unchanged",
                    state_updates={"hash": "deadbeef"},
                )

        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store),
            agent_resolver=lambda _id: agent,
            condition_resolver=lambda job: MonitorGate(),
        )
        result = _run(executor, FakeJob(message="watch"))
        assert result.status == "no_change"
        assert agent.last_message is None
        # watermark carried forward even though the tick was suppressed
        assert store.get_state("job1") == {"hash": "deadbeef"}

    def test_stateful_gate_updates_fold_into_notepad_on_go(self):
        store = FakeStateStore()
        store.set_state("job1", {"hash": "old"})
        agent = FakeAgent()

        class MonitorGate:
            def should_run(self, job, *, state=None):
                return GateResult(
                    run=True,
                    context="new items: 2",
                    state_updates={"hash": "new"},
                )

        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store),
            agent_resolver=lambda _id: agent,
            condition_resolver=lambda job: MonitorGate(),
        )
        _run(executor, FakeJob(message="summarise"))
        assert "hash=new" in agent.last_message
        assert "new items: 2" in agent.last_message
        assert store.get_state("job1") == {"hash": "new"}

    def test_stateful_gate_receives_prior_state(self):
        store = FakeStateStore()
        store.set_state("job1", {"seen": 5})
        agent = FakeAgent()
        received = {}

        class MonitorGate:
            def should_run(self, job, *, state=None):
                received["state"] = state
                return GateResult(run=True)

        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store),
            agent_resolver=lambda _id: agent,
            condition_resolver=lambda job: MonitorGate(),
        )
        _run(executor, FakeJob(message="go"))
        assert received["state"] == {"seen": 5}

    def test_legacy_stateless_gate_not_passed_state(self):
        store = FakeStateStore()
        store.set_state("job1", {"seen": 5})
        agent = FakeAgent()

        class LegacyGate:
            # signature has no ``state`` and no **kwargs
            def should_run(self, job):
                return GateResult(run=True)

        executor = ScheduledAgentExecutor(
            runner=FakeRunner(store),
            agent_resolver=lambda _id: agent,
            condition_resolver=lambda job: LegacyGate(),
        )
        # must not raise TypeError; still injects prior-state notepad
        result = _run(executor, FakeJob(message="go"))
        assert result.status == "succeeded"
        assert "seen=5" in agent.last_message
