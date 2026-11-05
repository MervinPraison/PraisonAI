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
    # Step "a" was edited (different name => different identity) so it and
    # everything after it must re-run rather than resume onto stale state.
    AgentFlow(
        steps=[_step("a2", calls, output="v2"), _step("b", calls)], cache=FileStepCache(path)
    ).run("x", verbose=False)
    assert calls == ["a2", "b"]


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
