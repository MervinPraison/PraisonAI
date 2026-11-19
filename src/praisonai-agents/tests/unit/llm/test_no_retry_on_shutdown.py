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
