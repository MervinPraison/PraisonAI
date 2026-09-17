"""Regression tests for PR #5044 fixes.

Covers three independently-provable behavioural gaps:

1. Planning result collection — after ``start()``/``astart()`` run with
   ``planning=True``, results must come from the executed plan-step tasks, not
   the (restored) original tasks.
2. Shared plan-task construction — both the sync and async planning paths must
   use ``_build_plan_tasks`` so they never diverge.
3. Async Ollama in-batch chaining — a dependent tool call in the same model
   response must resolve against an earlier call's recorded result.
"""

import asyncio
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. Planning result collection (sync + async)
# ---------------------------------------------------------------------------

def _make_plan(agent_name):
    from praisonaiagents.planning import Plan, PlanStep

    plan = Plan(
        name="do the thing",
        steps=[PlanStep(id="step_0", description="only step", agent=agent_name)],
    )
    plan.approve()
    return plan


def _build_team():
    from praisonaiagents import Agent, Task, AgentTeam

    agent = Agent(name="Worker", instructions="work", llm="gpt-4o-mini")
    task = Task(description="original task", agent=agent, expected_output="done")
    team = AgentTeam(agents=[agent], tasks=[task], planning=True)
    team.auto_approve_plan = True
    return team, agent


def test_sync_planning_returns_executed_plan_results():
    team, agent = _build_team()
    plan = _make_plan(agent.display_name)

    def _fake_run_task(task_id):
        team.tasks[task_id].status = "completed"
        from praisonaiagents.output.models import TaskOutput
        team.tasks[task_id].result = TaskOutput(
            description="plan step", raw="PLAN_RESULT", agent=agent.name
        )

    with patch.object(team, "_create_plan_sync", return_value=plan), \
         patch.object(team, "run_task", side_effect=_fake_run_task), \
         patch.object(team, "run_all_tasks"):
        results = team._start_impl(output="silent", return_dict=True)

    # The dict must reflect the executed plan-step task, not the untouched original.
    assert any(
        getattr(r, "raw", None) == "PLAN_RESULT"
        for r in results["task_results"].values()
    ), results["task_results"]

    # And the default (non-dict) return must be the plan-step raw output.
    with patch.object(team, "_create_plan_sync", return_value=_make_plan(agent.display_name)), \
         patch.object(team, "run_task", side_effect=_fake_run_task), \
         patch.object(team, "run_all_tasks"):
        raw = team._start_impl(output="silent", return_dict=False)
    assert raw == "PLAN_RESULT"


def test_async_planning_returns_executed_plan_results():
    team, agent = _build_team()
    plan = _make_plan(agent.display_name)

    async def _fake_arun_task(task_id):
        team.tasks[task_id].status = "completed"
        from praisonaiagents.output.models import TaskOutput
        team.tasks[task_id].result = TaskOutput(
            description="plan step", raw="ASYNC_PLAN_RESULT", agent=agent.name
        )

    async def _fake_create_plan(request=None):
        return plan

    async def _noop():
        return None

    with patch.object(team, "_create_plan", side_effect=_fake_create_plan), \
         patch.object(team, "arun_task", side_effect=_fake_arun_task), \
         patch.object(team, "arun_all_tasks", side_effect=_noop):
        raw = asyncio.run(team._astart_impl(return_dict=False))

    assert raw == "ASYNC_PLAN_RESULT"


def test_original_tasks_restored_after_planning():
    """Planning keeps the user's original task set as the canonical self.tasks."""
    team, agent = _build_team()
    original_ids = set(team.tasks.keys())
    plan = _make_plan(agent.display_name)

    def _fake_run_task(task_id):
        team.tasks[task_id].status = "completed"

    with patch.object(team, "_create_plan_sync", return_value=plan), \
         patch.object(team, "run_task", side_effect=_fake_run_task), \
         patch.object(team, "run_all_tasks"):
        team._start_impl(output="silent", return_dict=True)

    assert set(team.tasks.keys()) == original_ids


# ---------------------------------------------------------------------------
# 2. Shared plan-task construction
# ---------------------------------------------------------------------------

def test_sync_planning_uses_shared_build_plan_tasks():
    team, agent = _build_team()
    plan = _make_plan(agent.display_name)

    called = {"n": 0}
    real_build = team._build_plan_tasks

    def _spy(plan_arg, original_tasks):
        called["n"] += 1
        return real_build(plan_arg, original_tasks)

    with patch.object(team, "_create_plan_sync", return_value=plan), \
         patch.object(team, "_build_plan_tasks", side_effect=_spy), \
         patch.object(team, "run_task"), \
         patch.object(team, "run_all_tasks"):
        team._start_impl(output="silent", return_dict=True)

    assert called["n"] == 1, "sync planning must route through _build_plan_tasks"


# ---------------------------------------------------------------------------
# 3. String tool resolution on the OpenAI path (alias + override safe)
# ---------------------------------------------------------------------------

def test_registry_get_tool_definition_uses_alias_and_override():
    from praisonaiagents.tools.registry import ToolRegistry

    def my_func(x: int) -> int:
        """Double x."""
        return x * 2

    registry = ToolRegistry()

    def _override(schema):
        schema = dict(schema)
        schema["function"] = dict(schema["function"])
        schema["function"]["description"] = "OVERRIDDEN"
        return schema

    registry.register(
        my_func, name="aliased_tool", dynamic_schema_overrides=_override
    )

    tool_def = registry.get_tool_definition("aliased_tool")
    assert tool_def is not None
    # Advertised name must be the alias, not the callable __name__.
    assert tool_def["function"]["name"] == "aliased_tool"
    # Dynamic override must be applied.
    assert tool_def["function"]["description"] == "OVERRIDDEN"
    # Unknown names return None (not an exception).
    assert registry.get_tool_definition("does_not_exist") is None


def test_openai_client_resolves_string_tool_by_name():
    pytest.importorskip("litellm")  # OpenAIClient import chain is light, but be safe
    from praisonaiagents.tools.registry import get_registry
    from praisonaiagents.llm.openai_client import OpenAIClient

    def searchy(query: str) -> str:
        """Search."""
        return query

    get_registry().register(searchy, name="searchy", overwrite=True)

    client = OpenAIClient.__new__(OpenAIClient)  # avoid needing an API key
    tool_def = client._generate_tool_definition_from_name("searchy")
    assert tool_def is not None
    assert tool_def["function"]["name"] == "searchy"


# ---------------------------------------------------------------------------
# 4. Ollama chaining helpers (shared across sync / stream / async loops)
# ---------------------------------------------------------------------------

def test_resolve_ollama_chained_args_uses_recorded_results():
    """A dependent arg referencing an earlier tool name resolves to its value."""
    litellm = pytest.importorskip("litellm")  # noqa: F841
    from praisonaiagents.llm.llm import LLM

    llm = LLM(model="ollama/llama3.2")
    mapping = {}
    llm._record_ollama_tool_result(mapping, "get_stock_price", "The price is 100")
    assert mapping["get_stock_price"] == 100

    resolved = llm._resolve_ollama_chained_args(
        {"multiplier": "get_stock_price"}, mapping
    )
    assert resolved["multiplier"] == 100
