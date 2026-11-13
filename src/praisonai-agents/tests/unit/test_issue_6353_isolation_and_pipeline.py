"""Regression tests for #6353.

1. Memory context / Session / as_tool() must not leak across users or callers.
2. AgentTeam must accept structured (model instance) output, enforce
   output_json schemas, and feed guardrail rejection reasons into the retry.
3. Workflow include(workflow=...) must run the sub-workflow; include cycles and
   failures must end the run with status "failed".
"""
import os

import pytest
from pydantic import BaseModel
from unittest.mock import patch

from praisonaiagents import Agent, AgentTeam, Session, Task, Workflow
from praisonaiagents.workflows import StepResult, include


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    yield tmp_path


class City(BaseModel):
    city: str
    country: str


# --------------------------------------------------------------------------- 1


def test_build_context_scoped_to_configured_user(tmp_path):
    from praisonaiagents.memory.memory import Memory

    shared = str(tmp_path / "shared.db")
    alice = Memory({"provider": "sqlite", "user_id": "alice", "db_path": shared})
    bob = Memory({"provider": "sqlite", "user_id": "bob", "db_path": shared})
    alice.store_long_term("Alice salary is 250k")
    alice.store_short_term("Alice salary note")

    assert "Alice salary" not in bob.build_context_for_task("salary")
    assert "Alice salary" in alice.build_context_for_task("salary")


def test_sessions_do_not_share_or_wipe_memory():
    alice = Session(session_id="s-alice", user_id="alice")
    bob = Session(session_id="s-bob", user_id="bob")
    alice.add_memory("Alice bank PIN is 4321")

    assert bob.search_memory("PIN") == []
    assert "4321" not in bob.get_context("PIN")

    bob.clear_memory()
    assert [r["text"] for r in alice.search_memory("PIN")] == ["Alice bank PIN is 4321"]


def test_as_tool_calls_do_not_accumulate_history():
    spec = Agent(name="Specialist", instructions="Specialist", output="silent")
    seen = []

    def fake_chat(self, prompt, **kwargs):
        seen.append([m["content"] for m in self.chat_history if m["role"] == "user"])
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": "ok"})
        return "ok"

    tool = spec.as_tool()
    parent = Agent(name="Parent", instructions="x", output="silent")
    with patch.object(Agent, "chat", fake_chat):
        tool._execute_with_runtime_resolution(parent, "user A secret SSN", None, {})
        tool._execute_with_runtime_resolution(parent, "user B question", None, {})

    assert seen == [[], []]
    assert spec.chat_history == []


# --------------------------------------------------------------------------- 2


def _team_run(task, agent):
    AgentTeam(agents=[agent], tasks=[task], process="sequential").start()
    return task


def test_team_accepts_pydantic_instance_output():
    agent = Agent(name="A", instructions="x", output="silent")
    task = Task(name="t1", description="capital", expected_output="json",
                agent=agent, output_pydantic=City)
    with patch.object(Agent, "chat", lambda self, *a, **k: City(city="Paris", country="France")):
        _team_run(task, agent)

    assert task.status == "completed"
    assert task.result.pydantic == City(city="Paris", country="France")


def test_team_output_json_model_is_validated():
    agent = Agent(name="A", instructions="x", output="silent")
    task = Task(name="t1", description="capital", expected_output="json",
                agent=agent, output_json=City, max_retries=0)
    with patch.object(Agent, "chat", lambda self, *a, **k: '{"error": "unknown"}'):
        try:
            _team_run(task, agent)
        except Exception:
            pass
    assert task.status != "completed"
    assert task.result is None or task.result.json_dict != {"error": "unknown"}


def test_guardrail_reason_reaches_retry_prompt():
    agent = Agent(name="A", instructions="x", output="silent")
    prompts = []
    replies = iter(["draft with TODO", "final answer"])

    def fake_chat(self, prompt, *a, **k):
        prompts.append(prompt)
        return next(replies)

    def guard(output):
        if "TODO" in output.raw:
            return False, "remove the TODO marker"
        return True, output

    task = Task(name="t1", description="write it", expected_output="text",
                agent=agent, guardrail=guard, max_retries=2)
    with patch.object(Agent, "chat", fake_chat):
        _team_run(task, agent)

    assert task.status == "completed"
    assert len(prompts) == 2
    assert "remove the TODO marker" not in prompts[0]
    assert "remove the TODO marker" in prompts[1]


# --------------------------------------------------------------------------- 3


def test_include_workflow_instance_runs_sub_workflow():
    calls = []

    def inner_step(ctx):
        calls.append(ctx.input)
        return StepResult(output=f"INNER: {ctx.input}")

    inner = Workflow(name="inner", steps=[inner_step])
    outer = Workflow(name="outer", steps=[
        lambda ctx: StepResult(output="draft-v1"),
        include(workflow=inner),
        lambda ctx: StepResult(output=f"PUBLISHED<{ctx.previous_result}>"),
    ])
    res = outer.run("go")

    assert calls == ["draft-v1"]
    assert res["status"] == "completed"
    assert res["output"] == "PUBLISHED<INNER: draft-v1>"
    assert "previous_output" not in inner.variables


def test_include_cycle_fails_fast(tmp_path):
    for name, other in (("recA", "recB"), ("recB", "recA")):
        os.makedirs(name)
        with open(os.path.join(name, "workflow.yaml"), "w") as fh:
            fh.write(f"name: {name}\nsteps:\n  - include: {other}\n")

    reached = []
    res = Workflow(name="o", steps=[
        include("recA"),
        lambda ctx: reached.append(1) or StepResult(output="after"),
    ]).run("go")

    assert res["status"] == "failed"
    assert reached == []
    assert "Circular include" in str(res["steps"])


def test_include_missing_recipe_fails():
    res = Workflow(name="o", steps=[include("does-not-exist-6353")]).run("go")
    assert res["status"] == "failed"
