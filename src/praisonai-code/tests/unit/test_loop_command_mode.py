"""`praisonai loop` must run the iterative autonomy loop by default (#6027)."""

from unittest.mock import MagicMock, patch

from praisonai_code.cli.commands.loop import _run_loop


def test_loop_builds_iterative_autonomy_config():
    result = MagicMock(success=True, completion_reason="promise", iterations=2,
                       duration_seconds=0.1, started_at=None)
    with patch("praisonaiagents.Agent") as agent_cls:
        agent_cls.return_value.start.return_value = result
        _run_loop("Refactor auth module", max_iterations=10, completion_promise="DONE",
                  clear_context=False, timeout=None, model=None, verbose=False)

    autonomy = agent_cls.call_args.kwargs["autonomy"]
    assert autonomy["mode"] == "iterative"
    assert autonomy["completion_promise"] == "DONE"
    assert autonomy["max_iterations"] == 10
