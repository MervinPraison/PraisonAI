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


def _method_source(cls_or_module, method_name):
    """Return the dedented source of a method/function by name via AST."""
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(cls_or_module))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return node
    raise AssertionError(f"{method_name} not found")


def test_streaming_loop_stops_model_call_when_cancelled():
    """get_response_stream must not issue a follow-up model request once the
    cancel token is signalled (Issue #5073).

    Source-level guard: the streaming method both defines a cancellation
    predicate and returns/breaks based on it, so a cancelled turn cannot spend
    another completion after the tool batch short-circuits.
    """
    import ast
    from praisonaiagents.llm import llm as llm_module

    node = _method_source(llm_module, "get_response_stream")

    defines_predicate = any(
        isinstance(n, ast.FunctionDef) and n.name == "_stream_is_cancelled"
        for n in ast.walk(node)
    )
    assert defines_predicate, "expected _stream_is_cancelled predicate in get_response_stream"

    guarded = 0
    for n in ast.walk(node):
        if not isinstance(n, ast.If):
            continue
        test = n.test
        if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) \
                and test.func.id == "_stream_is_cancelled":
            guarded += 1
    assert guarded >= 1, (
        "expected at least one cancellation guard in get_response_stream "
        f"to stop the loop, found {guarded}"
    )


def test_agent_stream_forwards_cancel_token_to_get_response_stream():
    """The public agent streaming path must forward cancel_token to
    get_response_stream (Issue #5073).

    Without this, the token extracted in get_response_stream is always None for
    start(stream=True) / iter_stream(), so streamed tools keep running after Stop.
    """
    import ast
    from praisonaiagents.agent import chat_mixin

    node = _method_source(chat_mixin, "_start_stream_impl")

    forwarded = False
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) \
                and n.value.id == "stream_sampling_kwargs":
            key = n.slice
            if isinstance(key, ast.Constant) and key.value == "cancel_token":
                forwarded = True
    assert forwarded, (
        "expected _start_stream_impl to set stream_sampling_kwargs['cancel_token']"
    )
