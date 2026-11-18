"""Swallowed failures in the restart-loop breaker and the goal gate leave a
debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import praisonaiagents
from praisonaiagents.gateway import protocols as gw_protocols
from praisonaiagents.gateway.protocols import PersistentRestartLoopGuard
from praisonaiagents.goal import loop as goal_loop
from praisonaiagents.goal.loop import GoalLoopMixin

_FILES = [
    "gateway/protocols.py",
    "goal/loop.py",
    "guardrails/tool_guardrails.py",
]

# Kept silent on purpose: memoising the chain on a tool object that refuses
# attributes (e.g. a bound method) fails on every tool call while nothing is
# wrong; the chain is simply rebuilt, so a log line there would be noise.
_KEPT = {("guardrails/tool_guardrails.py", "get_tool_guardrail_chain")}


def _silent_broad_handlers(rel):
    path = Path(praisonaiagents.__file__).parent / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                    and isinstance(node.body[0], ast.Pass)):
                continue
            t = node.type
            names = ([t.id] if isinstance(t, ast.Name)
                     else [e.id for e in t.elts if isinstance(e, ast.Name)]
                     if isinstance(t, ast.Tuple) else [])
            if t is None or {"Exception", "BaseException"} & set(names):
                found.append((rel, func.name))
    return found


@pytest.mark.parametrize("rel", _FILES)
def test_only_deliberate_silent_handlers_remain(rel):
    assert set(_silent_broad_handlers(rel)) <= _KEPT
    if rel == "guardrails/tool_guardrails.py":
        assert _silent_broad_handlers(rel) == [
            ("guardrails/tool_guardrails.py", "get_tool_guardrail_chain")
        ]


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


class _BrokenStore:
    def load_events(self):
        return []

    def save_events(self, events):
        raise OSError("disk full")


def test_restart_store_failure_is_logged_and_breaker_still_trips(caplog):
    guard = PersistentRestartLoopGuard(_BrokenStore(), max_restarts=2, window_seconds=3600)

    with caplog.at_level(logging.DEBUG, logger=gw_protocols.__name__):
        decisions = [guard.record(1000.0 + i) for i in range(4)]
        guard.reset()

    assert decisions == [False, True, True, True]
    assert guard._events == []
    records = _debug_records(caplog, gw_protocols.__name__)
    assert len(records) == 5  # four record() flushes + one reset() flush


def test_goal_gate_failure_during_cancel_is_logged_and_cancel_propagates(monkeypatch, caplog):
    # The gate fails, and the run is cancelled before it observes that result.
    # The cancel must still propagate; the gate's failure must leave a trace.
    gate_failed = []

    async def _failing_to_thread(fn, *args, **kwargs):
        gate_failed.append(True)
        raise RuntimeError("gate broke")

    monkeypatch.setattr(asyncio, "to_thread", _failing_to_thread)

    class _Host(GoalLoopMixin):
        _goal_state = SimpleNamespace(status="active")

        def _goal_gate(self, response):  # pragma: no cover - replaced above
            raise AssertionError("not reached")

    async def _main():
        task = asyncio.ensure_future(_Host()._goal_gate_async("done"))
        for _ in range(20):
            await asyncio.sleep(0)
            if gate_failed:
                break
        assert gate_failed
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with caplog.at_level(logging.DEBUG, logger=goal_loop.logger.name):
        asyncio.run(_main())

    assert _debug_records(caplog, goal_loop.logger.name)
