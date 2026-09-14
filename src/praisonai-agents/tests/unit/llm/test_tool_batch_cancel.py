"""
Tests that the LLM tool loop forwards ``cancel_token`` to the tool batch
executor, so a Stop/interrupt requested during the tool phase short-circuits
pending tool calls instead of running them to completion.

Covers Issue #5073: ``cancel_token`` was dropped at the ``execute_batch``
boundary in both the non-streaming (``get_response``) and streaming
(``get_response_stream``) paths.
"""

import threading

from praisonaiagents.tools.call_executor import (
    ToolCall,
    create_tool_call_executor,
)


class _CancelToken:
    """Minimal threading.Event-like cancel token."""

    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_set(self):
        return self._event.is_set()


def _calls(n=2):
    return [
        ToolCall(
            function_name="do_thing",
            arguments={},
            tool_call_id=f"call_{i}",
            is_ollama=False,
        )
        for i in range(n)
    ]


def _execute_tool_fn(name, args, tool_call_id, **kw):
    return "ran"


def test_cancelled_token_skips_tool_execution_sequential():
    token = _CancelToken()
    token.cancel()
    executor = create_tool_call_executor(parallel=False)

    results = executor.execute_batch(
        _calls(3), _execute_tool_fn, cancel_token=token
    )

    assert len(results) == 3
    assert all(r.error_kind == "cancelled" for r in results)
    assert all(r.error is not None for r in results)


def test_cancelled_token_skips_tool_execution_parallel():
    token = _CancelToken()
    token.cancel()
    executor = create_tool_call_executor(parallel=True)

    results = executor.execute_batch(
        _calls(3), _execute_tool_fn, cancel_token=token
    )

    assert len(results) == 3
    assert all(r.error_kind == "cancelled" for r in results)


def test_no_cancel_runs_tools_normally():
    executor = create_tool_call_executor(parallel=False)
    results = executor.execute_batch(_calls(2), _execute_tool_fn)

    assert len(results) == 2
    assert all(r.error is None for r in results)
    assert all(r.result == "ran" for r in results)


def test_llm_loop_forwards_cancel_token_to_execute_batch():
    """Both execute_batch call sites in llm.py must forward cancel_token.

    A source-level guard (matching the issue's verification) so a future
    refactor cannot silently drop the token again at the executor boundary,
    which would leave in-flight tools running after a Stop/interrupt.
    """
    import ast
    import inspect
    from praisonaiagents.llm import llm as llm_module

    source = inspect.getsource(llm_module)
    tree = ast.parse(source)

    forwarded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "execute_batch"):
            continue
        # execute_batch on an ``executor`` object (not the protocol/def)
        if not (isinstance(func.value, ast.Name) and func.value.id == "executor"):
            continue
        for kw in node.keywords:
            if kw.arg == "cancel_token" and isinstance(kw.value, ast.Name) \
                    and kw.value.id == "cancel_token":
                forwarded += 1

    assert forwarded >= 2, (
        f"expected >=2 execute_batch calls forwarding cancel_token, "
        f"found {forwarded}"
    )
