"""Durable step cache: an interrupted AgentFlow resumes in a new process (#6249)."""
import json

import pytest

from praisonaiagents.workflows.step_cache import FileStepCache
from praisonaiagents.workflows.workflows import AgentFlow


def _step(name, calls, output=None, fail=False):
    def handler(ctx):
        calls.append(name)
        if fail:
            raise RuntimeError("interrupted")
        return output if output is not None else f"{name}-out"
    handler.__name__ = name
    return handler


def test_resume_skips_completed_steps_across_instances(tmp_path):
    path = tmp_path / "run.json"
    calls = []
    first = AgentFlow(
        steps=[_step("a", calls), _step("b", calls, fail=True)],
        cache=FileStepCache(str(path)),
    )
    try:
        first.run("in", verbose=False)
    except Exception:
        pass
    assert calls[0] == "a" and "b" in calls
    assert path.exists()

    # A fresh flow and a fresh cache object: simulates a new process.
    calls.clear()
    second = AgentFlow(
        steps=[_step("a", calls), _step("b", calls), _step("c", calls)],
        cache=FileStepCache(str(path)),
    )
    result = second.run("in", verbose=False)
    assert calls == ["b", "c"]
    assert result["output"] == "c-out"


def test_changed_input_does_not_serve_stale_results(tmp_path):
    path = str(tmp_path / "run.json")
    calls = []
    AgentFlow(steps=[_step("a", calls)], cache=FileStepCache(path)).run("x", verbose=False)
    AgentFlow(steps=[_step("a", calls)], cache=FileStepCache(path)).run("y", verbose=False)
    assert calls == ["a", "a"]


def test_changed_upstream_output_reruns_downstream(tmp_path):
    path = str(tmp_path / "run.json")
    calls = []
    AgentFlow(
        steps=[_step("a", calls, output="v1"), _step("b", calls)], cache=FileStepCache(path)
    ).run("x", verbose=False)
    calls.clear()
    # Step "a" was reconfigured under the SAME name (its closure value
    # changed), so it and everything after it must re-run.
    AgentFlow(
        steps=[_step("a", calls, output="v2"), _step("b", calls)], cache=FileStepCache(path)
    ).run("x", verbose=False)
    assert calls == ["a", "b"]


def test_unserialisable_value_is_rejected_not_stored(tmp_path):
    path = tmp_path / "run.json"
    cache = FileStepCache(str(path))
    with pytest.raises(TypeError):
        cache.set("k", {"output": object()})
    assert cache.get("k") is None and not path.exists()


def test_get_returns_a_copy_and_clear_removes_file(tmp_path):
    path = tmp_path / "run.json"
    cache = FileStepCache(str(path))
    cache.set("k", {"output": "o", "variables": {"x": 1}})
    cache.get("k")["variables"]["x"] = 2
    assert FileStepCache(str(path)).get("k") == {"output": "o", "variables": {"x": 1}}
    assert json.loads(path.read_text())["k"]["output"] == "o"
    cache.clear()
    assert len(cache) == 0 and not path.exists()


def test_edited_handler_with_same_name_reruns(tmp_path):
    path = str(tmp_path / "run.json")
    calls = []

    def a(ctx):
        calls.append("v1")
        return "v1"

    AgentFlow(steps=[a], cache=FileStepCache(path)).run("x", verbose=False)

    def a(ctx):  # noqa: F811 - same name, edited body
        calls.append("v2")
        return "v2"

    result = AgentFlow(steps=[a], cache=FileStepCache(path)).run("x", verbose=False)
    assert calls == ["v1", "v2"] and result["output"] == "v2"


@pytest.mark.parametrize("value", [{"variables": {"lookup": {1: "one"}}}, {"output": ("a", "b")}])
def test_value_that_changes_shape_in_json_is_rejected(tmp_path, value):
    cache = FileStepCache(str(tmp_path / "run.json"))
    with pytest.raises(TypeError):
        cache.set("k", value)
    assert cache.get("k") is None


def test_two_writers_on_one_path_keep_both_entries(tmp_path):
    path = str(tmp_path / "run.json")
    a, b = FileStepCache(path), FileStepCache(path)
    a.set("a", {"output": "1"})
    b.set("b", {"output": "2"})
    reopened = FileStepCache(path)
    assert reopened.get("a") == {"output": "1"} and reopened.get("b") == {"output": "2"}



def test_set_constants_are_encoded_independent_of_iteration_order():
    # A set literal compiles to a frozenset constant whose iteration order
    # depends on PYTHONHASHSEED; the key must not, or resume silently re-runs.
    from praisonaiagents.workflows.step_cache import _stable, make_step_key

    words = ["apple", "banana", "cherry", "date", "elder"]
    expected = "{" + ",".join(sorted(repr(w) for w in words)) + "}"
    assert _stable(frozenset(words), set()) == expected
    assert _stable(frozenset(reversed(words)), set()) == expected

    def lookup(ctx):
        return "fruit" if ctx.input in {"apple", "banana", "cherry", "date", "elder"} else "other"

    consts = lookup.__code__.co_consts
    assert any(isinstance(c, frozenset) for c in consts)
    # Same constants, frozenset rebuilt: the key must not change.
    rebuilt = lookup.__code__.replace(
        co_consts=tuple(frozenset(sorted(c, reverse=True)) if isinstance(c, frozenset) else c for c in consts)
    )
    import types
    twin = types.FunctionType(rebuilt, lookup.__globals__, "lookup")
    assert make_step_key(lookup, None, "apple", {}) == make_step_key(twin, None, "apple", {})
    assert make_step_key(lookup, None, "x", {"t": {"b", "a"}}) == make_step_key(lookup, None, "x", {"t": {"a", "b"}})

def test_edited_helper_or_default_reruns(tmp_path):
    from praisonaiagents.workflows.step_cache import make_step_key

    def helper_v1():
        return 1

    def helper_v2():
        return 2

    def make(default):
        def step(ctx, mode=default):
            return mode
        return step

    assert make_step_key(make("fast"), None, "x", {}) != make_step_key(make("slow"), None, "x", {})
    assert make_step_key(make("fast"), None, "x", {}) == make_step_key(make("fast"), None, "x", {})

    import types

    def step(ctx):
        return helper()  # noqa: F821 - resolved from the globals given below

    def bind(helper):
        return types.FunctionType(step.__code__, {"helper": helper}, "step")

    assert make_step_key(bind(helper_v1), None, "x", {}) != make_step_key(bind(helper_v2), None, "x", {})
    assert make_step_key(bind(helper_v1), None, "x", {}) == make_step_key(bind(helper_v1), None, "x", {})


def test_agent_step_with_same_name_but_new_instructions_misses():
    from praisonaiagents.workflows.step_cache import make_step_key

    class FakeAgent:
        def __init__(self, instructions, llm="gpt-4o-mini"):
            self.name, self.instructions, self.llm, self.tools = "writer", instructions, llm, []

    k = lambda a: make_step_key(a, None, "x", {})
    assert k(FakeAgent("be brief")) == k(FakeAgent("be brief"))
    assert k(FakeAgent("be brief")) != k(FakeAgent("be verbose"))
    assert k(FakeAgent("be brief")) != k(FakeAgent("be brief", llm="gpt-4o"))


def test_agent_wrapped_in_task_keys_on_agent_config():
    # AgentFlow normalises an Agent step to Task(agent=...) before keying it,
    # so the wrapped agent's instructions and model must reach the key.
    from praisonaiagents import Agent
    from praisonaiagents.workflows.step_cache import make_step_key

    def key(instructions, llm="gpt-4o-mini"):
        agent = Agent(name="writer", instructions=instructions, llm=llm)
        task = AgentFlow(steps=[agent])._normalize_single_step(agent, 0)
        assert task.agent is agent
        return make_step_key(task, None, "x", {})

    assert key("be brief") == key("be brief")
    assert key("be brief") != key("be verbose")
    assert key("be brief") != key("be brief", llm="gpt-4o")
