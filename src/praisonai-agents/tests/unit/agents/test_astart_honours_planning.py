"""astart() must honour planning=True, as start() already does.

`planning` gates a built feature: a plan from a PlanningAgent, a TodoList, and
an approval gate before anything runs. `_start_impl` branches on it in both of
its arms. `_astart_impl` did not mention `self.planning` at all and went
straight to `arun_all_tasks()`, so every async entry point -- workflows,
gateway protocols, the AGUI stream, the eval judge, autoagents -- ran the raw
task list as though planning had never been set, with no error and no
difference in the return shape.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.agents.agents import PraisonAIAgents


class _Recorder:
    """A PraisonAIAgents with the execution and planning seams stubbed out, so
    the test observes which path was taken and nothing talks to a model."""

    def __init__(self, agents, planning, plan=None, approved=True):
        self.calls = []
        self.plan = plan
        self.approved = approved
        self.agents = agents


@pytest.fixture
def team(monkeypatch):
    def build(planning, plan=object(), approved=True):
        instance = PraisonAIAgents.__new__(PraisonAIAgents)
        instance.planning = planning
        instance.auto_approve_plan = approved
        instance.tasks = {}
        instance.calls = []

        async def arun_all_tasks():
            instance.calls.append("arun_all_tasks")

        async def _arun_with_planning():
            instance.calls.append("_arun_with_planning")

        instance.arun_all_tasks = arun_all_tasks
        instance._arun_with_planning = _arun_with_planning
        instance.get_all_tasks_status = lambda: {}
        instance.get_task_result = lambda _id: None
        return instance

    return build


@pytest.mark.asyncio
async def test_astart_runs_the_planning_path_when_planning_is_on(team):
    agents = team(planning=True)

    await agents._astart_impl()

    assert agents.calls == ["_arun_with_planning"]


@pytest.mark.asyncio
async def test_astart_runs_tasks_directly_when_planning_is_off(team):
    agents = team(planning=False)

    await agents._astart_impl()

    assert agents.calls == ["arun_all_tasks"]


@pytest.mark.asyncio
async def test_planning_falls_back_to_plain_execution_when_no_plan(team):
    # A PlanningAgent that returns nothing must not strand the run.
    agents = team(planning=True)
    ran = []

    async def _create_plan(request=None, context=None):
        ran.append(("plan", request))
        return None

    async def arun_all_tasks():
        ran.append("arun_all_tasks")

    agents._create_plan = _create_plan
    agents.arun_all_tasks = arun_all_tasks

    await PraisonAIAgents._arun_with_planning(agents)

    assert ran[-1] == "arun_all_tasks"


@pytest.mark.asyncio
async def test_a_rejected_plan_runs_nothing(team):
    agents = team(planning=True, approved=False)
    agents.auto_approve_plan = False
    ran = []

    class _Plan:
        steps = []

        def approve(self):
            ran.append("approve")

    async def _create_plan(request=None, context=None):
        return _Plan()

    async def _request_approval(plan):
        ran.append("asked")
        return False

    async def arun_all_tasks():
        ran.append("arun_all_tasks")

    agents._create_plan = _create_plan
    agents._request_approval = _request_approval
    agents.arun_all_tasks = arun_all_tasks

    await PraisonAIAgents._arun_with_planning(agents)

    # Asked, refused, and stopped. The approval gate is the point of the
    # feature, so running anyway would be worse than not planning at all.
    assert ran == ["asked"]


def test_the_plan_to_task_builder_is_shared_by_both_paths():
    # Both planning paths must build tasks the same way; the async one was
    # proposed without this, which would have planned and then run the original
    # tasks instead of the plan's steps.
    import inspect

    sync_src = inspect.getsource(PraisonAIAgents._run_with_planning)
    async_src = inspect.getsource(PraisonAIAgents._arun_with_planning)

    assert "_apply_plan" in sync_src
    assert "_apply_plan" in async_src


@pytest.mark.asyncio
async def test_the_original_task_set_is_put_back_after_a_planned_run(team):
    # _apply_plan swaps self.tasks for the plan's steps. The sync path restored
    # the caller's tasks afterwards; the async path has to as well, or a team
    # comes back from astart() holding tasks it never defined.
    agents = team(planning=True)
    original = {0: SimpleNamespace(description="the caller's task")}
    agents.tasks = dict(original)
    ran = []

    class _Plan:
        name = "a plan"
        steps = []

        def approve(self):
            pass

    async def _create_plan(request=None, context=None):
        return _Plan()

    def _apply_plan(plan, console=None):
        previous = agents.tasks
        agents.tasks = {0: SimpleNamespace(description="a plan step")}
        return previous

    async def arun_all_tasks():
        ran.append(dict(agents.tasks))

    agents._create_plan = _create_plan
    agents._apply_plan = _apply_plan
    agents.arun_all_tasks = arun_all_tasks
    agents._task_id_lock = __import__("threading").Lock()

    await PraisonAIAgents._arun_with_planning(agents)

    assert [t.description for t in ran[0].values()] == ["a plan step"]  # ran the plan
    assert agents.tasks == original                                     # gave the original back
    assert [t.description for t in agents._plan_tasks.values()] == ["a plan step"]
