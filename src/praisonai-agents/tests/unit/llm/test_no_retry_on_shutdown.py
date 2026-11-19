"""A call cut off because the process is shutting down is not retried.

Pressing Ctrl-C while a model call was in flight logged
"unknown error hit (attempt 1/4), waiting 1.0s before retry..." twice before the
process could exit: the executor had already shut down, so every retry failed
the same way. Shutdown now ends the call at once.
"""

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize("message", [
    "cannot schedule new futures after shutdown",
    "cannot schedule new futures after interpreter shutdown",
])
def test_shutdown_error_is_not_retried(message):
    decision = LLM(model="ollama/x").resolve_failover_decision(
        RuntimeError(message), {"attempt": 1, "max_retries": 3, "side_effecting": True})
    assert decision.is_retryable is False
    assert decision.action == "surface_error"


def test_other_runtime_errors_keep_their_retry_policy():
    decision = LLM(model="ollama/x").resolve_failover_decision(
        RuntimeError("something odd"), {"attempt": 1, "max_retries": 3, "side_effecting": False})
    assert decision.is_retryable is True


def test_shutdown_error_is_not_shown_as_an_error_panel():
    import io

    from rich.console import Console

    from praisonaiagents.main import display_error

    out = io.StringIO()
    display_error("Error in get_response: cannot schedule new futures after shutdown",
                  console=Console(file=out, force_terminal=False))
    assert out.getvalue() == ""
    display_error("Error in get_response: model not found", console=Console(file=out, force_terminal=False))
    assert "model not found" in out.getvalue()


def test_turn_cut_off_by_shutdown_returns_none_without_a_warning():
    import warnings

    from praisonaiagents import Agent

    agent = Agent(name="a", model="ollama/x")
    err = RuntimeError("cannot schedule new futures after interpreter shutdown")
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        assert agent._none_after_failed_turn(err) is None
    assert not [w for w in seen if issubclass(w.category, FutureWarning)]
    assert agent._last_error is err
    with pytest.warns(FutureWarning):
        agent._none_after_failed_turn(RuntimeError("boom"))
