"""Regression tests for the sync->async bridge and tool-timeout invariants.

Covers issue #5588:
  1. No module under ``praisonaiagents/`` (other than ``utils/async_bridge.py``)
     re-implements the sync->async bridge: detecting a running loop and then
     offloading ``asyncio.run`` to a ``ThreadPoolExecutor``. Those copies
     dropped contextvars and could mask the coroutine's real error. All such
     sites must route through the shared helper. Deliberately distinct sites
     (raising on an in-loop call, deferring to a fallback, or routing to a
     registered loop via ``run_coroutine_threadsafe``) are intentionally
     allowed because they do not match the defective shape.
  2. ``run_single_tool_call(timeout_ms=...)`` runs the tool on a *daemon*
     worker and does not leak non-daemon threads per timed-out call.
"""

import ast
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from praisonaiagents.tools import call_executor as ce
from praisonaiagents.tools.call_executor import ToolCall, run_single_tool_call


def _package_root() -> Path:
    import praisonaiagents

    return Path(praisonaiagents.__file__).resolve().parent


def _calls_name(node: ast.AST, dotted: str) -> bool:
    """Whether ``node`` is a call to ``dotted`` (e.g. ``asyncio.run``)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    parts = dotted.split(".")
    for part in reversed(parts):
        if isinstance(func, ast.Attribute):
            if func.attr != part:
                return False
            func = func.value
        elif isinstance(func, ast.Name):
            return func.id == part
        else:
            return False
    return True


def _hand_rolls_bridge(func: ast.AST) -> bool:
    """Whether ``func`` re-implements the sync->async bridge.

    The defective shape the shared helper replaces: detect a running loop, then
    offload the coroutine to a ``ThreadPoolExecutor`` that calls ``asyncio.run``.
    Those copies dropped contextvars and could mask the coroutine's real error.
    Sites that merely detect a loop to *raise*, *defer to a fallback*, or route
    to a registered loop via ``run_coroutine_threadsafe`` do not match and are
    intentionally allowed.
    """
    body = list(ast.walk(func))
    gets_loop = any(
        _calls_name(n, "asyncio.get_running_loop")
        or _calls_name(n, "get_running_loop")
        for n in body
    )
    uses_pool = any(_calls_name(n, "ThreadPoolExecutor") for n in body)
    runs_asyncio = any(_calls_name(n, "asyncio.run") for n in body)
    uses_threadsafe = any(
        _calls_name(n, "asyncio.run_coroutine_threadsafe") for n in body
    )
    return gets_loop and uses_pool and runs_asyncio and not uses_threadsafe


def test_no_handrolled_async_bridges_outside_helper():
    root = _package_root()
    allowed = {root / "utils" / "async_bridge.py"}
    offenders = []

    for path in root.rglob("*.py"):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _hand_rolls_bridge(func):
                offenders.append(f"{path.relative_to(root)}::{func.name}")

    assert not offenders, (
        "Hand-rolled sync->async bridges found (route them through "
        "utils.async_bridge.run_coroutine_from_any_context): "
        + ", ".join(offenders)
    )


def test_tool_timeout_uses_daemon_worker_and_does_not_leak():
    before = {t.ident for t in threading.enumerate()}

    def slow_tool(name, arguments, tool_call_id, **kwargs):
        time.sleep(5)
        return "done"

    call = ToolCall(function_name="slow", arguments={}, tool_call_id="c1")
    result = run_single_tool_call(call, slow_tool, timeout_ms=50)

    assert result.error_kind == "timeout"

    # The abandoned worker must be a daemon thread so it can never block
    # interpreter exit.
    new_threads = [t for t in threading.enumerate() if t.ident not in before]
    tool_workers = [t for t in new_threads if t.name == "tool-timeout"]
    assert tool_workers, "expected an abandoned tool-timeout worker thread"
    assert all(t.daemon for t in tool_workers), "timeout workers must be daemon"


def test_many_concurrent_healthy_timed_calls_are_not_refused():
    """Healthy concurrent timed calls must not be refused by the orphan cap.

    Regression for #5589: the orphaned-worker semaphore must only bound workers
    that outlive their deadline, never healthy calls that finish in time. Run
    more concurrent fast calls than the cap and assert none is refused.
    """
    count = ce._TIMEOUT_POOL_MAX + 8

    def fast_tool(name, arguments, tool_call_id, **kwargs):
        return "ok"

    def run_one(i):
        call = ToolCall(function_name="fast", arguments={}, tool_call_id=f"c{i}")
        return run_single_tool_call(call, fast_tool, timeout_ms=5000)

    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(run_one, range(count)))

    assert all(r.error is None for r in results), (
        "healthy concurrent timed calls were refused: "
        + str([r.error_kind for r in results if r.error is not None])
    )
    assert all(r.result == "ok" for r in results)


def test_saturated_orphan_pool_reports_capacity_not_timeout(monkeypatch):
    """When the orphan pool is saturated, a refused call is typed 'capacity'.

    A capacity refusal (process already full of hung workers) must be reported
    distinctly from a per-tool timeout so the model/operator can tell them apart.
    """
    import threading as _threading

    # Shrink the cap to 1 and saturate it with one genuinely hung worker.
    monkeypatch.setattr(ce, "_timeout_slots", _threading.BoundedSemaphore(1))

    release = _threading.Event()

    def hung_tool(name, arguments, tool_call_id, **kwargs):
        release.wait(5)
        return "late"

    def quick_hang(name, arguments, tool_call_id, **kwargs):
        release.wait(5)
        return "late"

    try:
        # First call times out and charges the single orphan slot.
        first = run_single_tool_call(
            ToolCall(function_name="hung1", arguments={}, tool_call_id="h1"),
            hung_tool, timeout_ms=50,
        )
        assert first.error_kind == "timeout"

        # Second call also outlives its deadline but the pool is saturated, so it
        # must be refused as a capacity error, not a timeout.
        second = run_single_tool_call(
            ToolCall(function_name="hung2", arguments={}, tool_call_id="h2"),
            quick_hang, timeout_ms=50,
        )
        assert second.error_kind == "capacity"
    finally:
        release.set()
