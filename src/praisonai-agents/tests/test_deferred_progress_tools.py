#!/usr/bin/env python3
"""Tests for the deferred-result / progress-streaming tool-execution protocol.

Covers Issue #2925: a tool may (a) stream incremental progress via an
``on_progress`` emitter, (b) return a ``DeferredToolResult`` handle instead of
blocking the turn, (c) be an ``async def`` tool awaited natively, and (d)
surface structured (not flattened-string) errors to the model.
"""

import asyncio

import pytest

from praisonaiagents.tools.call_executor import (
    ToolCall,
    ToolProgress,
    DeferredToolResult,
    ToolResult,
    SequentialToolCallExecutor,
    ParallelToolCallExecutor,
    create_tool_call_executor,
    run_single_tool_call,
    defer,
    DeferredResolver,
    get_deferred_resolver,
    register_deferred,
    resolve_deferred,
)


def _call(name="t", args=None, cid="id-1"):
    return ToolCall(function_name=name, arguments=args or {}, tool_call_id=cid)


# --- Protocol surface --------------------------------------------------------

def test_protocol_exports_from_tools_package():
    from praisonaiagents.tools import ToolProgress as TP, DeferredToolResult as DTR, defer as d
    assert TP is ToolProgress
    assert DTR is DeferredToolResult
    assert d is defer


def test_tool_progress_defaults():
    p = ToolProgress("searching...")
    assert p.text == "searching..."
    assert p.id is None
    assert p.replace is True


def test_deferred_result_and_factory():
    d = defer(note="later", handle_id="job-7")
    assert isinstance(d, DeferredToolResult)
    assert d.handle_id == "job-7"
    assert d.note == "later"
    # auto handle id
    d2 = defer()
    assert d2.handle_id  # non-empty
    assert d2.note


# --- Basic execution stays backward compatible ------------------------------

def test_sequential_plain_result_unchanged():
    def execute(name, args, cid):
        return f"ran {name}"

    results = SequentialToolCallExecutor().execute_batch([_call()], execute)
    assert len(results) == 1
    r = results[0]
    assert r.result == "ran t"
    assert r.error is None
    assert r.is_deferred is False
    assert r.progress == []
    assert r.structured_error is None


def test_structured_error_on_failure():
    def execute(name, args, cid):
        raise ValueError("boom")

    r = SequentialToolCallExecutor().execute_batch([_call()], execute)[0]
    assert r.error is not None
    assert "Error executing tool: boom" in r.result  # legacy string preserved
    se = r.structured_error
    assert se["error"] is True
    assert se["type"] == "ValueError"
    assert se["message"] == "boom"
    assert se["tool"] == "t"


# --- Progress streaming ------------------------------------------------------

def test_progress_streamed_and_recorded():
    received = []

    def execute(name, args, cid, on_progress=None):
        on_progress(ToolProgress("step 1"))
        on_progress(ToolProgress("step 2"))
        return "done"

    r = run_single_tool_call(
        _call(), execute, on_progress=received.append
    )
    assert r.result == "done"
    assert [p.text for p in r.progress] == ["step 1", "step 2"]
    assert [p.text for p in received] == ["step 1", "step 2"]


def test_progress_callback_error_does_not_break_tool():
    def bad_cb(_):
        raise RuntimeError("channel down")

    def execute(name, args, cid, on_progress=None):
        on_progress(ToolProgress("x"))
        return "ok"

    r = run_single_tool_call(_call(), execute, on_progress=bad_cb)
    assert r.result == "ok"
    assert [p.text for p in r.progress] == ["x"]


def test_legacy_three_arg_execute_fn_without_progress():
    # execute_tool_fn that does NOT accept on_progress must still work
    def execute(name, args, cid):
        return "legacy"

    r = run_single_tool_call(_call(), execute, on_progress=lambda p: None)
    assert r.result == "legacy"
    assert r.progress == []


# --- Deferred results --------------------------------------------------------

def test_deferred_result_recorded_not_blocking():
    def execute(name, args, cid):
        return defer(note="I'll post later", handle_id="job-42")

    r = SequentialToolCallExecutor().execute_batch([_call()], execute)[0]
    assert r.is_deferred is True
    assert r.deferred.handle_id == "job-42"
    assert r.result == "I'll post later"  # note surfaced to model
    assert r.error is None


# --- Async tools -------------------------------------------------------------

def test_async_tool_awaited_natively():
    async def execute(name, args, cid):
        await asyncio.sleep(0)
        return "async-done"

    r = run_single_tool_call(_call(), execute)
    assert r.result == "async-done"
    assert r.error is None


def test_async_deferred_tool():
    async def execute(name, args, cid):
        await asyncio.sleep(0)
        return defer(note="queued", handle_id="j1")

    r = run_single_tool_call(_call(), execute)
    assert r.is_deferred is True
    assert r.result == "queued"


# --- Parallel executor parity -----------------------------------------------

def test_parallel_executor_carries_progress_and_deferred():
    def execute(name, args, cid, on_progress=None):
        if name == "a":
            on_progress(ToolProgress("a-progress"))
            return "a-done"
        return defer(note="b-later", handle_id="b1")

    calls = [_call(name="a", cid="a"), _call(name="b", cid="b")]
    results = ParallelToolCallExecutor(max_workers=2).execute_batch(calls, execute)
    by_name = {r.function_name: r for r in results}
    assert by_name["a"].result == "a-done"
    assert [p.text for p in by_name["a"].progress] == ["a-progress"]
    assert by_name["b"].is_deferred is True
    assert by_name["b"].result == "b-later"


def test_progress_stamped_with_source_identity():
    received = []

    def execute(name, args, cid, on_progress=None):
        on_progress(ToolProgress("working"))
        return "done"

    r = run_single_tool_call(
        _call(name="deep", cid="call-9"), execute, on_progress=received.append
    )
    assert r.progress[0].tool_call_id == "call-9"
    assert r.progress[0].function_name == "deep"
    assert received[0].tool_call_id == "call-9"
    assert received[0].function_name == "deep"


def test_parallel_progress_attributable_to_each_tool():
    seen = []

    def execute(name, args, cid, on_progress=None):
        on_progress(ToolProgress(f"{name}-tick"))
        return f"{name}-done"

    calls = [_call(name="a", cid="a"), _call(name="b", cid="b")]
    ParallelToolCallExecutor(max_workers=2).execute_batch(
        calls, execute, on_progress=seen.append
    )
    by_tool = {p.tool_call_id: p for p in seen}
    assert by_tool["a"].function_name == "a"
    assert by_tool["b"].function_name == "b"


def test_explicit_progress_source_not_overwritten():
    def execute(name, args, cid, on_progress=None):
        on_progress(ToolProgress("x", tool_call_id="custom", function_name="fn"))
        return "ok"

    r = run_single_tool_call(_call(name="deep", cid="call-9"), execute)
    assert r.progress[0].tool_call_id == "custom"
    assert r.progress[0].function_name == "fn"


def test_factory_still_returns_expected_executors():
    assert isinstance(create_tool_call_executor(parallel=False), SequentialToolCallExecutor)
    assert isinstance(create_tool_call_executor(parallel=True), ParallelToolCallExecutor)


# --- Deferred resolution (Issue #3716) --------------------------------------

def test_deferred_resolver_register_and_resolve():
    resolver = DeferredResolver()
    received = []

    def on_resolved(handle_id, value, session_id):
        received.append((handle_id, value, session_id))

    resolver.register("job-1", on_resolved, session_id="s-9")
    assert resolver.is_pending("job-1") is True

    # Resolve delivers value + drops the registration.
    assert resolver.resolve("job-1", "final report") is True
    assert received == [("job-1", "final report", "s-9")]
    assert resolver.is_pending("job-1") is False

    # Resolving again is a no-op (already dropped).
    assert resolver.resolve("job-1", "again") is False


def test_deferred_resolver_unknown_handle():
    resolver = DeferredResolver()
    assert resolver.resolve("nope", 123) is False


def test_deferred_resolver_cancel():
    resolver = DeferredResolver()
    resolver.register("job-2", lambda *a: None)
    assert resolver.cancel("job-2") is True
    assert resolver.is_pending("job-2") is False
    assert resolver.cancel("job-2") is False


def test_deferred_resolver_callback_error_swallowed():
    resolver = DeferredResolver()

    def boom(handle_id, value, session_id):
        raise RuntimeError("delivery down")

    resolver.register("job-3", boom)
    # Must not raise even though the callback does.
    assert resolver.resolve("job-3", "x") is True
    assert resolver.is_pending("job-3") is False


def test_global_resolver_helpers_end_to_end():
    resolver = get_deferred_resolver()
    seen = []
    handle = defer(note="later", handle_id="global-1").handle_id

    register_deferred(handle, lambda h, v, s: seen.append((h, v, s)))
    assert resolve_deferred(handle, "done") is True
    assert seen == [("global-1", "done", None)]
    # Cleaned up so the global registry does not leak between runs.
    assert resolver.is_pending(handle) is False


def test_deferred_early_resolution_is_buffered_then_delivered():
    # Background job finishes BEFORE the run loop registers the handle: the
    # value must be buffered and delivered on registration, not discarded.
    resolver = DeferredResolver()
    assert resolver.resolve("job-early", "report") is False
    assert resolver.is_pending("job-early") is False

    seen = []
    resolver.register("job-early", lambda h, v, s: seen.append((h, v, s)),
                      session_id="s-1")
    assert seen == [("job-early", "report", "s-1")]
    # Buffer consumed; no lingering pending registration.
    assert resolver.is_pending("job-early") is False


def test_register_if_absent_is_atomic_and_no_clobber():
    resolver = DeferredResolver()
    first = []
    second = []

    assert resolver.register_if_absent("job-a", lambda h, v, s: first.append(v)) is True
    # Second concurrent registration must NOT replace the first callback.
    assert resolver.register_if_absent("job-a", lambda h, v, s: second.append(v)) is False

    resolver.resolve("job-a", "ok")
    assert first == ["ok"]
    assert second == []


def test_cancel_clears_buffered_early_resolution():
    resolver = DeferredResolver()
    assert resolver.resolve("job-c", "v") is False
    # Cancel must drop the buffered early value so a later register gets nothing.
    assert resolver.cancel("job-c") is False
    seen = []
    resolver.register("job-c", lambda h, v, s: seen.append(v))
    assert seen == []


def test_resolver_exported_from_tools_package():
    from praisonaiagents.tools import (
        DeferredResolver as DR,
        get_deferred_resolver as g,
        register_deferred as reg,
        resolve_deferred as res,
    )
    assert DR is DeferredResolver
    assert g is get_deferred_resolver
    assert reg is register_deferred
    assert res is resolve_deferred


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
