"""Goal resume across a fresh Agent (simulated new process) — issue #6028.

``_load_goal_state`` used to run before the lazily created session store
existed, so a fresh Agent never saw the persisted state and restarted the goal
at ``turns_used=0``. A crashed run (still ``active``) was also never resumed.
"""

import pytest

import praisonaiagents.goal.loop as goal_loop
from praisonaiagents import Agent
from praisonaiagents.goal.models import GoalState
from praisonaiagents.model_harness import ScriptedModel

SESSION_ID = "goal-resume-6028"
GOAL = "all tests pass"


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))
    monkeypatch.setattr(
        goal_loop, "judge_goal", lambda state, *a, **k: ("continue", "not yet")
    )


def _make_agent():
    return Agent(
        name="worker",
        instructions="Fix the tests.",
        llm=ScriptedModel([f"Working, step {i}." for i in range(20)]),
        memory={"session_id": SESSION_ID, "history": True},
        output="silent",
    )


def _persisted(agent):
    session = agent._session_store.get_session(SESSION_ID)
    return session.metadata.get("goal_state")


def test_paused_goal_resumes_in_fresh_agent():
    first = _make_agent()
    r = first.run_goal("Fix the failing tests", goal=GOAL, max_turns=2)
    assert r.completion_reason == "budget_paused"
    assert _persisted(first)["turns_used"] == 2

    fresh = _make_agent()
    assert fresh._session_store is None  # store not created yet
    r = fresh.run_goal("Fix the failing tests", goal=GOAL, max_turns=3)
    # Resumed at turn 2, so only one more turn fits under max_turns=3.
    assert r.iterations == 1
    assert _persisted(fresh)["turns_used"] == 3


def test_crashed_active_goal_is_resumed():
    seed = _make_agent()
    seed._init_session_store()
    seed._goal_state = GoalState(goal=GOAL, max_turns=5, turns_used=3)
    seed._persist_goal_state()  # status "active": process died mid-run

    fresh = _make_agent()
    state = fresh._resume_or_new_goal_state(GOAL, None, 5, True)
    assert state.turns_used == 3
    assert state.status == "active"


def test_different_goal_starts_fresh():
    seed = _make_agent()
    seed._init_session_store()
    seed._goal_state = GoalState(goal=GOAL, max_turns=5, turns_used=3)
    seed._persist_goal_state()

    fresh = _make_agent()
    state = fresh._resume_or_new_goal_state("another goal", None, 5, True)
    assert state.turns_used == 0
