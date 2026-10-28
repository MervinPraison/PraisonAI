"""`praisonai loop` must actually loop by default (Issue #6044).

With no ``--level`` the agent used caller mode (one ``chat()`` call) and
``timeout=None`` was forwarded into ``chat()`` -> TypeError before any LLM call.
"""
import pytest

pytest.importorskip("typer")

from praisonai_code.cli.commands import loop as loop_module


class _Result:
    success = True
    completion_reason = "promise"
    iterations = 2
    duration_seconds = 0.1
    started_at = None
    output = "done"
    error = None


@pytest.mark.parametrize("timeout, expected_kwargs", [(None, {}), (30.0, {"timeout": 30.0})])
def test_loop_defaults_to_iterative_and_omits_unset_timeout(monkeypatch, timeout, expected_kwargs):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

        def start(self, prompt, **kwargs):
            captured["start_kwargs"] = kwargs
            return _Result()

    import praisonaiagents
    monkeypatch.setattr(praisonaiagents, "Agent", FakeAgent)

    loop_module._run_loop(
        prompt="build it",
        max_iterations=4,
        completion_promise="DONE",
        clear_context=True,
        timeout=timeout,
        model=None,
        verbose=False,
    )

    autonomy = captured["agent_kwargs"]["autonomy"]
    assert autonomy["mode"] == "iterative"
    assert autonomy["max_iterations"] == 4
    assert autonomy["completion_promise"] == "DONE"
    assert autonomy["clear_context"] is True
    assert captured["start_kwargs"] == expected_kwargs

