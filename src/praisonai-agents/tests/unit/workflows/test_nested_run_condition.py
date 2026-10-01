"""Nested execution must honor Task gates, including cached pattern runs."""

import os

import pytest

from praisonaiagents import Task
from praisonaiagents.workflows.workflows import AgentFlow, Include, Parallel, Repeat


@pytest.mark.parametrize("cache", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_nested_task_gate_is_rechecked(cache, nested):
    enabled = {"value": False}
    checks = []
    calls = []

    def gate(ctx):
        checks.append(enabled["value"])
        return enabled["value"]

    def handler(ctx):
        calls.append("run")
        return "done"

    step = Task(name="conditional", handler=handler, should_run=gate)
    pattern = Parallel(steps=[step])
    if nested:
        pattern = Parallel(steps=[pattern])
    flow = AgentFlow(steps=[pattern], cache=cache)
    flow.run("same", verbose=False)
    assert calls == []
    assert flow.step_statuses["conditional"] == "skipped"

    enabled["value"] = True
    flow.run("same", verbose=False)
    flow.run("same", verbose=False)
    enabled["value"] = False
    flow.run("same", verbose=False)
    assert checks == [False, True, True, False]
    assert calls == ["run"] * (1 if cache else 2)
    assert flow.step_statuses["conditional"] == "skipped"


def test_skipped_parallel_branch_does_not_duplicate_upstream_output():
    flow = AgentFlow(steps=[Task(name="upstream", handler=lambda ctx: "upstream"), Parallel(steps=[
        Task(name="skip", handler=lambda ctx: "unused", should_run=lambda ctx: False),
        Task(name="run", handler=lambda ctx: "fresh"),
    ])])
    result = flow.run("upstream", verbose=False)
    assert result["variables"]["parallel_outputs"] == [None, "fresh"]
    assert result["output"] == "fresh"


def test_skipped_repeat_does_not_overwrite_parallel_sibling_write():
    flow = AgentFlow(steps=[Parallel(steps=[
        Task(name="writer", handler=lambda ctx: "new", output_variable="shared"),
        Repeat(Task(name="skip", handler=lambda ctx: "unused",
                    should_run=lambda ctx: False), max_iterations=1),
    ])], variables={"shared": "old"})
    result = flow.run("same", verbose=False)
    assert result["variables"]["shared"] == "new"


def test_hierarchical_skip_bypasses_manager_and_completion(monkeypatch):
    from praisonaiagents.llm import LLM

    manager_calls = []
    completed = []
    monkeypatch.setattr(LLM, "get_response", lambda *args, **kwargs:
                        manager_calls.append(kwargs) or '{"approved": true}')
    step = Task(name="skip", handler=lambda ctx: "unused", should_run=lambda ctx: False)
    flow = AgentFlow(steps=[step], process="hierarchical",
                     hooks={"on_step_complete": lambda *args: completed.append(args)})
    result = flow.run("upstream", verbose=False)
    assert result["steps"] == [{"step": "skip", "output": None, "status": "skipped"}]
    assert flow.step_statuses["skip"] == "skipped"
    assert "skip_output" not in result["variables"]
    assert manager_calls == completed == []
    assert result["output"] == "upstream"


def test_included_recipe_leaves_reuse_cache_without_cross_recipe_hits(tmp_path, monkeypatch):
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    calls = []
    recipes = []
    for name in ("first", "second"):
        recipe = tmp_path / name
        recipe.mkdir()
        (recipe / "workflow.yaml").write_text("name: placeholder\n", encoding="utf-8")
        recipes.append(recipe)

    def parse_file(parser, path):
        name = str(path)
        return AgentFlow(steps=[Task(name="same_leaf", handler=lambda ctx:
                                    calls.append(name) or name)])

    monkeypatch.setattr(YAMLWorkflowParser, "parse_file", parse_file)
    monkeypatch.setitem(__import__("sys").modules, "agent_recipes", None)
    flow = AgentFlow(steps=[Parallel(steps=[Include(recipe=str(p)) for p in recipes])], cache=True)
    first = flow.run("same", verbose=False)
    second = flow.run("same", verbose=False)
    assert len(calls) == 2
    assert first["variables"]["parallel_outputs"] == second["variables"]["parallel_outputs"]
    assert first["variables"]["parallel_outputs"][0] != first["variables"]["parallel_outputs"][1]


@pytest.mark.skipif(
    os.getenv("RUN_REAL_KEY_TESTS") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="requires an explicitly enabled real test provider",
)
def test_nested_gate_with_real_agent():
    from praisonaiagents import Agent

    enabled = {"value": True}
    calls = []
    agent = Agent(name="nested", instructions="Answer briefly.",
                  llm=os.getenv("PRAISONAI_TEST_MODEL", "gpt-4o-mini"))

    def handler(ctx):
        calls.append("run")
        response = agent.start("Say hello in one short sentence.")
        print(response)
        assert response
        return response

    flow = AgentFlow(steps=[Parallel(steps=[Task(
        name="conditional", handler=handler,
        should_run=lambda ctx: enabled["value"],
    )])], cache=True)
    flow.run("same", verbose=False)
    flow.run("same", verbose=False)
    enabled["value"] = False
    flow.run("same", verbose=False)
    assert calls == ["run"]
    assert flow.step_statuses["conditional"] == "skipped"

