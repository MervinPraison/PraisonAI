"""`praisonai loop --max-budget` reaches the agent's ExecutionConfig (Issue #6206)."""
import pytest

pytest.importorskip("typer")

import typer

from praisonai_code.cli.commands import loop as loop_module


class _Result:
    success = True
    completion_reason = "promise"
    iterations = 1
    duration_seconds = 0.1
    started_at = None
    output = "done"
    error = None


def _capture(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

        def start(self, prompt, **kwargs):
            return _Result()

    import praisonaiagents
    monkeypatch.setattr(praisonaiagents, "Agent", FakeAgent)
    return captured


def _run(**extra):
    loop_module._run_loop(
        prompt="build it", max_iterations=2, completion_promise=None,
        clear_context=False, timeout=None, model=None, verbose=False, **extra,
    )


def test_max_budget_forwarded_to_execution(monkeypatch):
    captured = _capture(monkeypatch)
    _run(max_budget=0.5, on_budget_exceeded="warn")
    assert captured["agent_kwargs"]["execution"] == {
        "max_budget": 0.5, "on_budget_exceeded": "warn",
    }


def test_no_budget_leaves_execution_unset(monkeypatch):
    captured = _capture(monkeypatch)
    _run()
    assert "execution" not in captured["agent_kwargs"]


def test_invalid_on_budget_exceeded_rejected(monkeypatch):
    _capture(monkeypatch)
    with pytest.raises(typer.Exit):
        _run(max_budget=1.0, on_budget_exceeded="explode")


def test_budget_dict_builds_real_execution_config():
    pytest.importorskip("praisonaiagents")
    from praisonaiagents import Agent

    agent = Agent(name="a", execution={"max_budget": 0.25, "on_budget_exceeded": "stop"})
    assert agent._max_budget == 0.25


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_max_budget_rejected(monkeypatch, bad):
    captured = _capture(monkeypatch)
    with pytest.raises(typer.Exit):
        _run(max_budget=bad)
    assert "agent_kwargs" not in captured
