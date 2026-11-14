"""Abandoned branches must be told to stop (Issue #6266)."""
import asyncio
import threading
import time

import pytest

from praisonaiagents.agent.chat_mixin import ChatMixin, _stop_scope


def _turn_token():
    # Same factory every Agent turn uses; no interrupt controller attached.
    return ChatMixin._turn_cancel_token(object(), None, explicit=False)


def test_no_token_outside_scope():
    assert _turn_token() is None


def test_stop_scope_sets_token_on_exit_and_nests():
    with _stop_scope():
        with _stop_scope():
            tok = _turn_token()
            assert tok is not None and not tok.is_set()
        assert tok.is_set()  # inner exit
    with _stop_scope() as outer:
        with _stop_scope():
            tok = _turn_token()
            outer.set()
            assert tok.is_set() and tok.reason == "run abandoned by caller"


def test_parallel_timeout_stops_running_branch():
    from praisonaiagents import AgentFlow, Parallel

    steps_done = []
    finished = threading.Event()

    def branch(x):
        tok = _turn_token()
        try:
            for i in range(20):
                if tok.is_set():
                    return "stopped"
                time.sleep(0.05)
                steps_done.append(i)
            return "done"
        finally:
            finished.set()

    with pytest.raises(Exception):
        AgentFlow(steps=[Parallel([branch], timeout=0.2)]).start("go")
    assert finished.wait(2)
    assert len(steps_done) < 10


def test_agent_team_cancel_stops_running_task():
    from praisonaiagents import Agent, AgentTeam, Task

    finished = threading.Event()
    steps_done = []

    agent = Agent(name="a", instructions="x", llm="gpt-4o-mini")

    def fake_run_task(self, task_id):
        tok = _turn_token()
        try:
            for i in range(20):
                if tok.is_set():
                    return None
                time.sleep(0.05)
                steps_done.append(i)
        finally:
            finished.set()

    team = AgentTeam(agents=[agent], tasks=[Task(description="d", agent=agent)])
    team.run_task = fake_run_task.__get__(team)

    async def main():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(team.arun_all_tasks(), timeout=0.2)

    asyncio.run(main())
    assert finished.wait(2)
    assert len(steps_done) < 10
