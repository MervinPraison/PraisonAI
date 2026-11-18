"""Swallowed failures in telemetry queueing, the token usage sink, AG-UI state
conversion and the workflow ``on_step_error`` hook leave a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
Two blocks stay silent on purpose and are pinned below.
"""

import ast
import logging
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents import Workflow
from praisonaiagents.task.task import Task
from praisonaiagents.telemetry import token_collector
from praisonaiagents.telemetry.token_collector import TokenCollector, TokenMetrics
from praisonaiagents.ui.agui import conversion
from praisonaiagents.workflows import workflows as workflows_mod
from praisonaiagents.workflows.workflow_configs import WorkflowHooksConfig

_FILES = [
    "telemetry/integration.py",
    "telemetry/token_collector.py",
    "ui/agui/conversion.py",
    "workflows/workflows.py",
]

# Deliberately silent:
# - _atexit_cleanup runs from atexit (registered in _get_telemetry_executor);
#   logging there can hit closed streams during interpreter shutdown.
# - _isolate_value's deepcopy attempt is a probe: it fails by design for every
#   un-copyable value (clients, open files, live agents) and falls back to
#   sharing that node, so a log would fire on normal parallel/loop runs.
_KEPT_SILENT = {
    ("telemetry/integration.py", "_atexit_cleanup"),
    ("workflows/workflows.py", "_isolate_value"),
}


def _is_silent_broad(node):
    if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
            and isinstance(node.body[0], ast.Pass)):
        return False
    t = node.type
    names = ([t.id] if isinstance(t, ast.Name)
             else [e.id for e in t.elts if isinstance(e, ast.Name)]
             if isinstance(t, ast.Tuple) else [])
    return t is None or bool({"Exception", "BaseException"} & set(names))


def _silent_broad_handlers(rel):
    """(file, innermost enclosing function) for each silent broad handler."""
    path = Path(praisonaiagents.__file__).parent / rel
    found = set()

    def visit(node, func_name):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if _is_silent_broad(child):
                found.add((rel, func_name))
            visit(child, func_name)

    visit(ast.parse(path.read_text(encoding="utf-8")), "<module>")
    return found


@pytest.mark.parametrize("rel", _FILES)
def test_only_the_pinned_handlers_stay_silent(rel):
    expected = {k for k in _KEPT_SILENT if k[0] == rel}
    assert _silent_broad_handlers(rel) == expected


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_token_sink_failure_is_logged_and_usage_still_counted(caplog):
    class _BrokenSink:
        def persist(self, **kwargs):
            raise RuntimeError("sink broke")

    collector = TokenCollector()
    collector.set_sink(_BrokenSink())

    with caplog.at_level(logging.DEBUG, logger=token_collector.__name__):
        collector.track_tokens(model="gpt-4o-mini", agent="writer",
                               metrics=TokenMetrics(input_tokens=7, output_tokens=5))

    summary = collector.get_session_summary()
    assert summary["total_interactions"] == 1
    assert summary["total_tokens"] == 12
    assert _debug_records(caplog, token_collector.__name__)


def test_state_to_dict_failure_is_logged_and_state_ignored(caplog):
    class _State:
        def to_dict(self):
            raise RuntimeError("to_dict broke")

    with caplog.at_level(logging.DEBUG, logger=conversion.logger.name):
        result = conversion.validate_state(_State(), "thread-1")

    assert result is None
    assert _debug_records(caplog, conversion.logger.name)


def test_on_step_error_hook_failure_is_logged_and_run_still_fails(caplog):
    class _FailingAgent:
        name = "Writer"

        def chat(self, action, **kwargs):
            raise RuntimeError("model down")

    def _hook(*args):
        raise RuntimeError("hook broke")

    wf = Workflow(
        name="hook-flow",
        steps=[Task(name="write", agent=_FailingAgent(), action="Write", max_retries=0)],
        hooks=WorkflowHooksConfig(on_step_error=_hook),
    )

    with caplog.at_level(logging.DEBUG, logger=workflows_mod.logger.name):
        result = wf.start("go")

    assert result["status"] == "failed"
    records = _debug_records(caplog, workflows_mod.logger.name)
    assert any("on_step_error" in r.getMessage() for r in records)
