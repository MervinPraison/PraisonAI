"""Regression: the shared step-cache envelope must be reachable from BOTH
executors -- AgentFlow and WorkflowManager are unrelated classes (#6292)."""
from praisonaiagents.workflows.workflows import (
    AgentFlow, WorkflowManager, _with_step_cache,
)


class _DictCache:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v


def test_workflow_manager_single_step_without_cache_does_not_crash(monkeypatch):
    mgr = WorkflowManager.__new__(WorkflowManager)  # no _step_cache attribute
    sentinel = {"success": True, "output": "ok", "stop": False, "error": None}
    monkeypatch.setattr(mgr, "_execute_single_step_nocache", lambda *a, **k: sentinel, raising=False)
    out = mgr._execute_single_step(
        "step", 0, [], {}, None, None, None, None, False, False, None, None, "in",
    )
    assert out is sentinel


def test_helper_caches_success_and_skips_errors():
    cache, calls = _DictCache(), []

    def run(result):
        def _r():
            calls.append(1)
            return result
        return _r

    ok = {"output": "x", "error": None}
    assert _with_step_cache(cache, "s", (None, "i", {}), run(ok)) == ok
    hits = []
    assert _with_step_cache(cache, "s", (None, "i", {}), run(ok), on_hit=lambda: hits.append(1)) == ok
    assert len(calls) == 1 and hits == [1]

    bad = {"output": None, "error": "boom"}
    _with_step_cache(cache, "b", (None, "i", {}), run(bad))
    _with_step_cache(cache, "b", (None, "i", {}), run(bad))
    assert len(calls) == 3  # failures are never served from cache


def test_helper_is_not_a_method():
    assert not hasattr(AgentFlow, "_with_step_cache")
    assert not hasattr(WorkflowManager, "_with_step_cache")
