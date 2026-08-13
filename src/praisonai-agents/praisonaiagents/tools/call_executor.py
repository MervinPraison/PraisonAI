"""
Tool Call Executor protocols for parallel and sequential tool execution.

This module implements Gap 2 from Issue #1392: enables parallel execution
of batched LLM tool calls while maintaining backward compatibility.

Design principles:
- Protocol-driven: ToolCallExecutor defines interface, concrete implementations provide behavior
- Opt-in: parallel_tool_calls=False by default (zero regression risk)
- Respects existing per-tool timeout infrastructure
- Thread-safe with bounded workers
"""

import asyncio
import concurrent.futures
import inspect
import logging
import threading
import uuid
import weakref
from typing import Any, Callable, Dict, List, Optional, Protocol
from dataclasses import dataclass, field
from ..errors import ToolExecutionError
from ..trace.context_events import copy_context_to_callable

logger = logging.getLogger(__name__)


def _probe_on_progress(execute_tool_fn: Callable) -> bool:
    """Introspect whether ``execute_tool_fn`` advertises an ``on_progress`` kwarg.

    The ``(TypeError, ValueError)`` fallback is preserved for built-in/C
    callables whose signature can't be introspected.
    """
    try:
        return "on_progress" in inspect.signature(execute_tool_fn).parameters
    except (TypeError, ValueError):
        return False


_ON_PROGRESS_CACHE: "weakref.WeakKeyDictionary[Callable, bool]" = weakref.WeakKeyDictionary()


def _accepts_on_progress(execute_tool_fn: Callable) -> bool:
    """Return whether ``execute_tool_fn`` advertises an ``on_progress`` kwarg.

    Memoised because ``execute_tool_fn`` is invariant per agent, so
    ``inspect.signature`` only needs to run once per callable rather than once
    per tool call in the loop.

    The cache holds weak references keyed by the callable, so it never keeps a
    bound method's owning agent alive: once the agent is discarded the entry is
    dropped. Callables that can't be weak-referenced or hashed (e.g. some
    built-in/C callables or objects with ``__hash__ = None``) skip the cache and
    are probed directly, preserving correct dispatch for valid 3-arg tools.
    """
    try:
        cached = _ON_PROGRESS_CACHE.get(execute_tool_fn)
    except TypeError:
        return _probe_on_progress(execute_tool_fn)
    if cached is not None:
        return cached
    result = _probe_on_progress(execute_tool_fn)
    try:
        _ON_PROGRESS_CACHE[execute_tool_fn] = result
    except TypeError:
        pass
    return result


class ToolTimeoutError(Exception):
    """Raised when a tool call exceeds its configured ``timeout_ms``."""


class ToolCancelledError(Exception):
    """Raised when a tool call is aborted via the cancel token."""


@dataclass
class ToolProgress:
    """Incremental progress update emitted by a running tool.

    A tool may accept an optional ``on_progress`` callable and emit these
    while working, so a slow tool (deep research, media generation, a long
    build) can stream feedback instead of freezing the turn.

    Attributes:
        text: Human-readable progress message.
        id: Optional stable id so a channel can edit a single draft message.
        replace: If True, this update replaces the prior draft; else appends.
        tool_call_id: Source tool call id, stamped by the executor so a
            streaming consumer can attribute concurrent updates to the right
            tool (important under parallel execution).
        function_name: Source tool name, stamped by the executor.
    """
    text: str
    id: Optional[str] = None
    replace: bool = True
    tool_call_id: Optional[str] = None
    function_name: Optional[str] = None


@dataclass
class DeferredToolResult:
    """A handle returned by a tool that started long-running background work.

    Instead of blocking the whole turn, a tool may return this to signal
    "started; will resolve later". The execution loop records it as pending
    work and surfaces the ``note`` to the model immediately.

    Attributes:
        handle_id: Identifier for the background job (used to resolve later).
        note: Message shown to the model now, e.g. "queued job 42".
    """
    handle_id: str
    note: str = "started; will resolve later"


@dataclass
class ToolCall:
    """Represents a single tool call from LLM."""
    function_name: str
    arguments: Dict[str, Any]
    tool_call_id: str
    is_ollama: bool = False
    iteration_index: Optional[int] = None


@dataclass 
class ToolResult:
    """Result of executing a single tool call.

    Carries the tool ``result`` plus optional structured error content,
    streamed ``progress`` updates, and a ``deferred`` handle when the tool
    hands back pending background work instead of a final value.
    """
    function_name: str
    arguments: Dict[str, Any]
    result: Any
    tool_call_id: str
    is_ollama: bool
    error: Optional[Exception] = None
    progress: List[ToolProgress] = field(default_factory=list)
    deferred: Optional[DeferredToolResult] = None
    error_kind: str = "error"

    @property
    def is_deferred(self) -> bool:
        """True if the tool returned a deferred handle rather than a value."""
        return self.deferred is not None

    @property
    def structured_error(self) -> Optional[Dict[str, Any]]:
        """Structured error content for the model, or None on success.

        Unlike the flattened ``"Error executing tool: ..."`` string, this
        exposes a discriminated error ``kind`` (``timeout`` / ``cancelled`` /
        ``error``) plus type and message so the model can reason about whether
        to retry, choose another tool, or report the failure.
        """
        if self.error is None:
            return None
        return {
            "error": True,
            "kind": self.error_kind,
            "type": type(self.error).__name__,
            "message": str(self.error),
            "tool": self.function_name,
        }


# Type alias for an optional per-batch progress emitter.
OnProgress = Callable[[ToolProgress], None]


def _resolve_value(value: Any) -> Any:
    """Await a coroutine result if a tool (or execute_tool_fn) returned one.

    Native ``async def`` tools are awaited here so callers never see an
    un-awaited coroutine.

    This helper is only reached from the synchronous executor path. When no
    loop is running we simply ``asyncio.run`` the coroutine. When a loop is
    already running on the *current* thread we cannot nest ``asyncio.run``, so
    the coroutine is driven to completion on a fresh loop in a dedicated worker
    thread. A tool whose coroutine is bound to the caller's loop (loop-bound
    clients/locks/sessions) should instead be invoked through the async
    executor path; for such a tool the resulting cross-loop error is captured
    as a structured tool error rather than crashing the turn.
    """
    if not inspect.iscoroutine(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    # Inside a running loop: run the coroutine to completion on its own loop
    # in a dedicated worker thread to avoid nesting event loops.
    import concurrent.futures as _futures

    def _runner() -> Any:
        return asyncio.run(value)

    with _futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_runner).result()


def _cancel_requested(cancel_token: Any) -> bool:
    """Best-effort check whether a cancel token has been signalled.

    Supports ``threading.Event``-like tokens (``.is_set()``) and
    ``InterruptController``-like tokens (``.is_cancelled`` / ``.cancelled``)
    without importing a concrete type, keeping the executor decoupled.
    """
    if cancel_token is None:
        return False
    for attr in ("is_set", "is_cancelled", "cancelled"):
        flag = getattr(cancel_token, attr, None)
        if flag is None:
            continue
        try:
            return bool(flag() if callable(flag) else flag)
        except Exception:
            return False
    return False


def run_single_tool_call(
    tool_call: ToolCall,
    execute_tool_fn: Callable[..., Any],
    on_progress: Optional[OnProgress] = None,
    timeout_ms: Optional[int] = None,
    cancel_token: Any = None,
) -> ToolResult:
    """Execute one tool call, capturing progress, deferred, async and errors.

    - If ``execute_tool_fn`` accepts an ``on_progress`` kwarg, progress
      updates are forwarded to the caller and recorded on the result.
    - Coroutine returns (``async def`` tools) are awaited natively.
    - A ``DeferredToolResult`` return is recorded without blocking.
    - When ``timeout_ms`` is set the tool runs on a dedicated worker and is
      abandoned on expiry, returning a typed ``timeout`` result instead of
      hanging the turn.
    - When ``cancel_token`` is already signalled the call is short-circuited
      with a typed ``cancelled`` result.
    - Failures populate ``error`` (and structured error) instead of only a
      flattened string.
    """
    if _cancel_requested(cancel_token):
        err = ToolCancelledError(f"Tool '{tool_call.function_name}' cancelled before execution")
        return ToolResult(
            function_name=tool_call.function_name,
            arguments=tool_call.arguments,
            result={"error": "cancelled", "tool": tool_call.function_name},
            tool_call_id=tool_call.tool_call_id,
            is_ollama=tool_call.is_ollama,
            error=err,
            error_kind="cancelled",
        )

    timeout_s = (timeout_ms / 1000.0) if timeout_ms and timeout_ms > 0 else None
    if timeout_s is None:
        return _run_tool_body(tool_call, execute_tool_fn, on_progress)

    # Bounded execution: run on a dedicated worker so a hung tool cannot block
    # the turn indefinitely. Python threads cannot be force-killed, so on
    # expiry the worker is abandoned (daemon pool) and a typed timeout result
    # is returned to the model.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(
        copy_context_to_callable(_run_tool_body),
        tool_call,
        execute_tool_fn,
        on_progress,
    )
    try:
        result = fut.result(timeout=timeout_s)
        pool.shutdown(wait=False)
        return result
    except concurrent.futures.TimeoutError:
        # Abandon the worker without waiting; do not block the turn.
        pool.shutdown(wait=False)
        logger.error(
            f"Tool '{tool_call.function_name}' timed out after {timeout_ms}ms"
        )
        err = ToolTimeoutError(
            f"Tool '{tool_call.function_name}' timed out after {timeout_ms}ms"
        )
        return ToolResult(
            function_name=tool_call.function_name,
            arguments=tool_call.arguments,
            result={"error": "timeout", "timeout_ms": timeout_ms, "tool": tool_call.function_name},
            tool_call_id=tool_call.tool_call_id,
            is_ollama=tool_call.is_ollama,
            error=err,
            error_kind="timeout",
        )


def _run_tool_body(
    tool_call: ToolCall,
    execute_tool_fn: Callable[..., Any],
    on_progress: Optional[OnProgress] = None,
) -> ToolResult:
    """Execute the tool body without timeout/cancel wrapping."""
    collected: List[ToolProgress] = []

    def _emit(update: ToolProgress) -> None:
        # Stamp the source so a streaming consumer can attribute concurrent
        # updates (under parallel execution) to the correct tool call.
        if update.tool_call_id is None:
            update.tool_call_id = tool_call.tool_call_id
        if update.function_name is None:
            update.function_name = tool_call.function_name
        collected.append(update)
        if on_progress is not None:
            try:
                on_progress(update)
            except Exception as cb_err:  # never let a channel error kill the tool
                logger.warning(f"on_progress callback failed: {cb_err}")

    try:
        # Only pass on_progress if execute_tool_fn advertises support for it,
        # keeping full backward compatibility with existing 3-arg callables.
        # Memoised so the signature probe runs once per callable, not per call.
        supports_progress = _accepts_on_progress(execute_tool_fn)

        call_kwargs = {}
        if supports_progress:
            call_kwargs["on_progress"] = _emit
        if (
            tool_call.iteration_index is not None
            and getattr(execute_tool_fn, "_accepts_durable_iteration", False)
        ):
            call_kwargs["_durable_iteration_index"] = tool_call.iteration_index
        raw = execute_tool_fn(
            tool_call.function_name,
            tool_call.arguments,
            tool_call.tool_call_id,
            **call_kwargs,
        )

        result = _resolve_value(raw)

        deferred = result if isinstance(result, DeferredToolResult) else None
        return ToolResult(
            function_name=tool_call.function_name,
            arguments=tool_call.arguments,
            result=deferred.note if deferred is not None else result,
            tool_call_id=tool_call.tool_call_id,
            is_ollama=tool_call.is_ollama,
            progress=collected,
            deferred=deferred,
        )
    except ToolExecutionError:
        raise
    except Exception as e:
        logger.error(f"Tool execution error for {tool_call.function_name}: {e}")
        return ToolResult(
            function_name=tool_call.function_name,
            arguments=tool_call.arguments,
            result=f"Error executing tool: {e}",
            tool_call_id=tool_call.tool_call_id,
            is_ollama=tool_call.is_ollama,
            error=e,
            progress=collected,
        )


class ToolCallExecutor(Protocol):
    """Protocol for executing batched tool calls."""
    
    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        execute_tool_fn: Callable[[str, Dict[str, Any], Optional[str]], Any],
        on_progress: Optional[OnProgress] = None,
        timeout_ms: Optional[int] = None,
        cancel_token: Any = None,
    ) -> List[ToolResult]:
        """
        Execute a batch of tool calls and return results in original order.
        
        Args:
            tool_calls: List of tool calls to execute
            execute_tool_fn: Function to execute individual tools
            on_progress: Optional callback receiving ToolProgress updates as
                tools stream incremental progress.
            timeout_ms: Optional per-tool timeout in milliseconds; a tool that
                exceeds it is abandoned and returns a typed timeout result.
            cancel_token: Optional cancel token; a signalled token short-
                circuits pending calls with a typed cancelled result.
            
        Returns:
            List of ToolResult in same order as input tool_calls
        """
        ...


class SequentialToolCallExecutor:
    """
    Sequential tool call executor - maintains current behavior.
    
    Executes tool calls one after another, preserving exact current semantics.
    """
    
    def execute_batch(
        self,
        tool_calls: List[ToolCall], 
        execute_tool_fn: Callable[[str, Dict[str, Any], Optional[str]], Any],
        on_progress: Optional[OnProgress] = None,
        timeout_ms: Optional[int] = None,
        cancel_token: Any = None,
    ) -> List[ToolResult]:
        """Execute tool calls sequentially - current behavior."""
        return [
            run_single_tool_call(
                tool_call, execute_tool_fn, on_progress,
                timeout_ms=timeout_ms, cancel_token=cancel_token,
            )
            for tool_call in tool_calls
        ]


class ParallelToolCallExecutor:
    """
    Parallel tool call executor with bounded concurrency.
    
    Executes tool calls concurrently using thread pool while respecting:
    - Per-tool timeout (from existing infrastructure) 
    - Bounded max_workers to prevent resource exhaustion
    - Result ordering (matches input order)
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize parallel executor.
        
        Args:
            max_workers: Maximum concurrent tool executions (default 5)
        """
        self.max_workers = max_workers
    
    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        execute_tool_fn: Callable[[str, Dict[str, Any], Optional[str]], Any],
        on_progress: Optional[OnProgress] = None,
        timeout_ms: Optional[int] = None,
        cancel_token: Any = None,
    ) -> List[ToolResult]:
        """Execute tool calls in parallel using thread pool."""
        if not tool_calls:
            return []
            
        # Single tool call - no need for parallelism overhead
        if len(tool_calls) == 1:
            sequential_executor = SequentialToolCallExecutor()
            return sequential_executor.execute_batch(
                tool_calls, execute_tool_fn, on_progress,
                timeout_ms=timeout_ms, cancel_token=cancel_token,
            )
        
        # G4: Check for path conflicts - fallback to sequential if conflicts detected
        try:
            from .path_overlap import has_write_conflicts
        except ImportError:
            logger.warning(
                "Path conflict detection unavailable; using sequential execution for safety"
            )
            sequential_executor = SequentialToolCallExecutor()
            return sequential_executor.execute_batch(
                tool_calls, execute_tool_fn, on_progress,
                timeout_ms=timeout_ms, cancel_token=cancel_token,
            )

        if has_write_conflicts(tool_calls):
            logger.info(f"Path conflicts detected in {len(tool_calls)} tool calls, using sequential execution")
            sequential_executor = SequentialToolCallExecutor()
            return sequential_executor.execute_batch(
                tool_calls, execute_tool_fn, on_progress,
                timeout_ms=timeout_ms, cancel_token=cancel_token,
            )
        
        def _execute_single_tool(tool_call: ToolCall) -> ToolResult:
            """Execute a single tool call with progress/deferred/error handling."""
            return run_single_tool_call(
                tool_call, execute_tool_fn, on_progress,
                timeout_ms=timeout_ms, cancel_token=cancel_token,
            )
        
        # Use ThreadPoolExecutor for sync tools. Per-tool timeout/cancellation
        # is enforced inside run_single_tool_call, so a hung tool resolves to a
        # typed timeout result rather than blocking collection indefinitely.
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tool calls with context propagation
            future_to_index = {
                # Preserve contextvars (tracing/session context) across worker threads.
                executor.submit(copy_context_to_callable(_execute_single_tool), tool_call): i
                for i, tool_call in enumerate(tool_calls)
            }
            
            # Collect results and restore original order
            results = [None] * len(tool_calls)
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                results[index] = future.result()
            
            return results


def create_tool_call_executor(parallel: bool = False, max_workers: int = 5) -> ToolCallExecutor:
    """
    Factory function to create appropriate tool call executor.
    
    Args:
        parallel: If True, return ParallelToolCallExecutor; else SequentialToolCallExecutor
        max_workers: Maximum concurrent workers for parallel executor
        
    Returns:
        ToolCallExecutor implementation
    """
    if parallel:
        return ParallelToolCallExecutor(max_workers=max_workers)
    else:
        return SequentialToolCallExecutor()


def defer(note: str = "started; will resolve later",
          handle_id: Optional[str] = None) -> DeferredToolResult:
    """Convenience factory for a deferred tool result.

    Example::

        from praisonaiagents.tools import defer, ToolProgress

        @tool
        def deep_research(topic: str, on_progress=None) -> DeferredToolResult:
            job = enqueue(topic)
            if on_progress:
                on_progress(ToolProgress(f"queued {job.id}"))
            return defer(note="I'll post the report when it's ready",
                         handle_id=job.id)
    """
    return DeferredToolResult(
        handle_id=handle_id or uuid.uuid4().hex,
        note=note,
    )


@dataclass
class _DeferredRegistration:
    """A pending deferred handle awaiting resolution."""
    on_resolved: Callable[[str, Any, Optional[str]], None]
    session_id: Optional[str] = None


class DeferredResolver:
    """Registry that resolves deferred tool handles when their work finishes.

    Closes the loop the run loop cannot: a tool returns ``defer(handle_id=...)``
    for long-running background work, the run loop surfaces the note immediately
    (non-blocking) and registers the handle here; when the background job
    completes, ``resolve()`` re-injects the final value via the registered
    callback (into the same run if still open, or a new turn keyed by
    ``session_id`` — the caller decides). The eventual result is no longer lost.

    Kept intentionally tiny and dependency-free (a lock + dict) so the core stays
    lightweight. Registrations are dropped once resolved, so the registry does
    not grow unbounded. Thread-safe: ``resolve()`` is typically invoked from a
    background worker thread (e.g. ``BackgroundJobManager``'s ``on_complete``).
    """

    def __init__(self) -> None:
        self._pending: Dict[str, _DeferredRegistration] = {}
        # Values that arrived before their handle was registered. Buffered so a
        # background job that finishes faster than the run loop registers is not
        # lost; delivered immediately when register()/register_if_absent() runs.
        self._early: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(
        self,
        handle_id: str,
        on_resolved: Callable[[str, Any, Optional[str]], None],
        session_id: Optional[str] = None,
    ) -> None:
        """Register a resolution callback for a deferred ``handle_id``.

        ``on_resolved`` is invoked as ``on_resolved(handle_id, value,
        session_id)`` once :meth:`resolve` is called for the same handle. If the
        value already arrived before this call (an early resolution), the
        callback fires immediately with the buffered value.
        """
        self.register_if_absent(handle_id, on_resolved, session_id)

    def register_if_absent(
        self,
        handle_id: str,
        on_resolved: Callable[[str, Any, Optional[str]], None],
        session_id: Optional[str] = None,
    ) -> bool:
        """Atomically register only if ``handle_id`` is not already pending.

        Returns ``True`` if this call stored the registration, ``False`` if a
        registration already existed (left untouched). Prevents a check-then-set
        race where concurrent turns replace each other's callback. If an early
        resolution was buffered for this handle, its value is delivered
        immediately and no registration is stored.
        """
        with self._lock:
            if handle_id in self._pending:
                return False
            early = self._early.pop(handle_id, None)
            if early is None:
                self._pending[handle_id] = _DeferredRegistration(
                    on_resolved=on_resolved, session_id=session_id
                )
        if early is not None:
            self._fire(on_resolved, handle_id, early[0], session_id)
        return True

    @staticmethod
    def _fire(
        on_resolved: Callable[[str, Any, Optional[str]], None],
        handle_id: str,
        value: Any,
        session_id: Optional[str],
    ) -> None:
        try:
            on_resolved(handle_id, value, session_id)
        except Exception as e:  # noqa: BLE001 — resolution must never crash worker
            logger.warning(
                "Deferred resolution callback for %s raised (non-fatal): %s",
                handle_id, e,
            )

    def resolve(self, handle_id: str, value: Any) -> bool:
        """Deliver ``value`` for ``handle_id`` and drop the registration.

        Returns ``True`` if a matching registration was found and its callback
        fired, ``False`` if the handle was not yet registered. In the latter
        case the value is buffered as an early resolution and delivered when the
        handle is later registered, so a fast background job is never lost. A
        callback exception is swallowed and logged so a delivery failure never
        crashes the completing worker.
        """
        with self._lock:
            reg = self._pending.pop(handle_id, None)
            if reg is None:
                self._early[handle_id] = (value,)
        if reg is None:
            return False
        self._fire(reg.on_resolved, handle_id, value, reg.session_id)
        return True

    def is_pending(self, handle_id: str) -> bool:
        """Whether ``handle_id`` is registered and not yet resolved."""
        with self._lock:
            return handle_id in self._pending

    def cancel(self, handle_id: str) -> bool:
        """Drop a pending registration without resolving it.

        Returns ``True`` if a registration was removed. Also clears any buffered
        early resolution for the handle.
        """
        with self._lock:
            self._early.pop(handle_id, None)
            return self._pending.pop(handle_id, None) is not None


_global_deferred_resolver: Optional[DeferredResolver] = None
_global_deferred_lock = threading.Lock()


def get_deferred_resolver() -> DeferredResolver:
    """Return the process-wide :class:`DeferredResolver` (lazily created)."""
    global _global_deferred_resolver
    with _global_deferred_lock:
        if _global_deferred_resolver is None:
            _global_deferred_resolver = DeferredResolver()
        return _global_deferred_resolver


def register_deferred(
    handle_id: str,
    on_resolved: Callable[[str, Any, Optional[str]], None],
    session_id: Optional[str] = None,
) -> None:
    """Register a resolver for a deferred handle on the global resolver.

    Convenience wrapper the run loop calls when it observes a deferred tool
    result, so the eventual background value is re-injected instead of lost::

        for r in executor.execute_batch(calls):
            if r.is_deferred:
                register_deferred(r.deferred.handle_id, reinject, session_id)
    """
    get_deferred_resolver().register(handle_id, on_resolved, session_id)


def resolve_deferred(handle_id: str, value: Any) -> bool:
    """Resolve a deferred handle on the global resolver (background completion).

    Wire this to a background job's completion signal, e.g.
    ``BackgroundJobManager.start_job(..., on_complete=lambda info:
    resolve_deferred(info.job_id, info.result))``.
    """
    return get_deferred_resolver().resolve(handle_id, value)
