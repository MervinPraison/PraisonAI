"""Opt-in durable tool-loop context backed by :class:`RunJournal`."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from ..errors import ToolExecutionError
from ..runtime.journal import (
    JournalEvent,
    KIND_ITERATION,
    KIND_MODEL_DECISION,
    KIND_TOOL_CALL,
    KIND_TOOL_RESULT,
    RunJournal,
)


_active_durable_run: contextvars.ContextVar[Optional["DurableRunContext"]] = (
    contextvars.ContextVar("praisonai_active_durable_run", default=None)
)
_active_idempotency_key: contextvars.ContextVar[Optional[str]] = (
    contextvars.ContextVar("praisonai_idempotency_key", default=None)
)


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


def _tool_result_content(result: Any) -> str:
    if result is None:
        return "Function returned an empty output"
    try:
        return json.dumps(result)
    except (TypeError, ValueError):
        return json.dumps({"result": str(result)})


def _accepts_idempotency_key(execute_tool_fn: Callable) -> bool:
    """Return whether an executor accepts the optional durable key contract."""
    try:
        parameters = inspect.signature(execute_tool_fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "idempotency_key"
        or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


class DurableRunContext:
    """Per-turn journal state; safe for parallel tool-call wrappers."""

    def __init__(
        self,
        journal: RunJournal,
        run_id: str,
        *,
        replaying: bool,
    ) -> None:
        self.journal = journal
        self.run_id = run_id
        self.replaying = replaying
        self._lock = threading.RLock()
        self._replay = journal.replay_index(run_id)
        events = journal.events(run_id)
        self._next_seq = max((event.seq for event in events), default=-1) + 1
        self._restored = False
        self._closed = False
        self._results_by_tool_call_id: Dict[str, Any] = {}
        self._pending_by_call_id: Dict[str, Tuple[int, str, Dict[str, Any], str]] = {}
        self._pending_by_fingerprint: Dict[str, Tuple[int, str, Dict[str, Any], str]] = {}
        self._recorded_iterations = set()
        for event in events:
            if event.kind == KIND_TOOL_RESULT:
                tool_call_id = event.payload.get("tool_call_id")
                if tool_call_id:
                    self._results_by_tool_call_id[str(tool_call_id)] = event.payload.get(
                        "result"
                    )
            elif event.kind == KIND_ITERATION:
                self._recorded_iterations.add(
                    int(event.payload.get("index", event.seq))
                )

        for event in events:
            if event.kind != KIND_TOOL_CALL:
                continue
            call_id = str(event.payload.get("tool_call_id") or "")
            if not call_id or call_id in self._results_by_tool_call_id:
                continue
            name = str(event.payload.get("name") or "")
            args = event.payload.get("args") or {}
            key = str(
                event.payload.get("idempotency_key")
                or f"{self.run_id}:{event.seq}:{name}"
            )
            pending = (event.seq, call_id, args, key)
            self._pending_by_call_id[call_id] = pending
            self._pending_by_fingerprint[self._fingerprint(name, args)] = pending

        self._resume_completed_steps = len(self._recorded_iterations)

    @property
    def completed_steps(self) -> int:
        return len(self._recorded_iterations)

    @staticmethod
    def _fingerprint(function_name: str, arguments: Dict[str, Any]) -> str:
        return f"{function_name}:{json.dumps(_json_safe(arguments), sort_keys=True)}"

    def restore_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Append completed decision/result pairs once, before the next model call."""
        if not self.replaying or self._restored:
            return messages

        existing_ids = set()
        for message in messages:
            for tool_call in message.get("tool_calls") or []:
                if isinstance(tool_call, dict) and tool_call.get("id"):
                    existing_ids.add(str(tool_call["id"]))

        for seq in sorted({key[0] for key in self._replay}):
            decision = self._replay.get((seq, KIND_MODEL_DECISION))
            result = self._replay.get((seq, KIND_TOOL_RESULT))
            if not decision or result is None:
                continue
            message = decision.get("message")
            tool_call_id = result.get("tool_call_id")
            if not isinstance(message, dict) or not tool_call_id:
                continue
            if str(tool_call_id) in existing_ids:
                continue
            messages.append(_json_safe(message))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(tool_call_id),
                    "content": _tool_result_content(result.get("result")),
                }
            )
            existing_ids.add(str(tool_call_id))

        self._restored = True
        return messages

    def _allocate_step(
        self,
        function_name: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
    ) -> Tuple[int, str, str]:
        with self._lock:
            requested_call_id = str(tool_call_id) if tool_call_id is not None else None
            pending = (
                self._pending_by_call_id.pop(requested_call_id, None)
                if requested_call_id
                else None
            )
            fingerprint = self._fingerprint(function_name, arguments)
            if pending is None and self.replaying:
                pending = self._pending_by_fingerprint.pop(fingerprint, None)
            if pending is not None:
                seq, call_id, _args, idempotency_key = pending
                self._pending_by_call_id.pop(call_id, None)
                self._pending_by_fingerprint.pop(fingerprint, None)
                return seq, call_id, idempotency_key

            seq = self._next_seq
            self._next_seq += 1
            call_id = str(tool_call_id or f"{self.run_id}-tool-{seq}")
            idempotency_key = f"{self.run_id}:{seq}:{function_name}"
            safe_arguments = _json_safe(arguments)
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": json.dumps(safe_arguments),
                        },
                    }
                ],
            }
            self.journal.append(
                JournalEvent(
                    self.run_id,
                    seq,
                    KIND_MODEL_DECISION,
                    {"message": message},
                )
            )
            self.journal.append(
                JournalEvent(
                    self.run_id,
                    seq,
                    KIND_TOOL_CALL,
                    {
                        "name": function_name,
                        "args": safe_arguments,
                        "tool_call_id": call_id,
                        "idempotency_key": idempotency_key,
                    },
                )
            )
            return seq, call_id, idempotency_key

    def _record_result(
        self,
        seq: int,
        tool_call_id: str,
        result: Any,
        iteration_index: Optional[int],
    ) -> Any:
        safe_result = _json_safe(result)
        with self._lock:
            self.journal.append(
                JournalEvent(
                    self.run_id,
                    seq,
                    KIND_TOOL_RESULT,
                    {"tool_call_id": tool_call_id, "result": safe_result},
                )
            )
            if iteration_index is None:
                global_iteration = max(self._recorded_iterations, default=-1) + 1
            else:
                global_iteration = self._resume_completed_steps + int(iteration_index)
            if global_iteration not in self._recorded_iterations:
                self.journal.append(
                    JournalEvent(
                        self.run_id,
                        global_iteration,
                        KIND_ITERATION,
                        {"index": global_iteration},
                    )
                )
                self._recorded_iterations.add(global_iteration)
            self._results_by_tool_call_id[tool_call_id] = safe_result
            self._replay[(seq, KIND_TOOL_RESULT)] = {
                "tool_call_id": tool_call_id,
                "result": safe_result,
            }
        return safe_result

    def _record_terminal_failure(
        self,
        seq: int,
        tool_call_id: str,
        error: ToolExecutionError,
        iteration_index: Optional[int],
    ) -> None:
        """Persist a fatal tool outcome and make the run non-resumable."""
        self._record_result(
            seq,
            tool_call_id,
            {
                "error": str(error),
                "error_type": type(error).__name__,
                "is_retryable": bool(error.is_retryable),
                "terminal": True,
            },
            iteration_index,
        )
        self.finalize("failed")

    def wrap_sync(self, execute_tool_fn: Optional[Callable]) -> Optional[Callable]:
        if execute_tool_fn is None:
            return None

        def execute(function_name, arguments, tool_call_id=None, **kwargs):
            iteration_index = kwargs.pop("_durable_iteration_index", None)
            call_id = str(tool_call_id) if tool_call_id is not None else None
            if call_id and call_id in self._results_by_tool_call_id:
                return self._results_by_tool_call_id[call_id]
            seq, call_id, idempotency_key = self._allocate_step(
                function_name, arguments, tool_call_id
            )
            token = _active_idempotency_key.set(idempotency_key)
            try:
                call_kwargs = dict(kwargs)
                call_kwargs["tool_call_id"] = tool_call_id
                if _accepts_idempotency_key(execute_tool_fn):
                    call_kwargs["idempotency_key"] = idempotency_key
                result = execute_tool_fn(function_name, arguments, **call_kwargs)
            except ToolExecutionError as exc:
                if not exc.is_retryable:
                    self._record_terminal_failure(
                        seq, call_id, exc, iteration_index
                    )
                raise
            except Exception as exc:
                result = {"error": str(exc)}
            finally:
                _active_idempotency_key.reset(token)
            return self._record_result(seq, call_id, result, iteration_index)

        return execute

    def wrap_async(self, execute_tool_fn: Optional[Callable]) -> Optional[Callable]:
        if execute_tool_fn is None:
            return None

        async def execute(function_name, arguments, tool_call_id=None, **kwargs):
            iteration_index = kwargs.pop("_durable_iteration_index", None)
            call_id = str(tool_call_id) if tool_call_id is not None else None
            if call_id and call_id in self._results_by_tool_call_id:
                return self._results_by_tool_call_id[call_id]
            seq, call_id, idempotency_key = await asyncio.to_thread(
                self._allocate_step, function_name, arguments, tool_call_id
            )
            token = _active_idempotency_key.set(idempotency_key)
            try:
                call_kwargs = dict(kwargs)
                call_kwargs["tool_call_id"] = tool_call_id
                if _accepts_idempotency_key(execute_tool_fn):
                    call_kwargs["idempotency_key"] = idempotency_key
                result = execute_tool_fn(function_name, arguments, **call_kwargs)
                if inspect.isawaitable(result):
                    result = await result
            except ToolExecutionError as exc:
                if not exc.is_retryable:
                    await asyncio.to_thread(
                        self._record_terminal_failure,
                        seq,
                        call_id,
                        exc,
                        iteration_index,
                    )
                raise
            except Exception as exc:
                result = {"error": str(exc)}
            finally:
                _active_idempotency_key.reset(token)
            return await asyncio.to_thread(
                self._record_result, seq, call_id, result, iteration_index
            )

        return execute

    def finalize(self, outcome: str = "succeeded") -> None:
        if not self._closed:
            self.journal.close_run(self.run_id, outcome)
            self._closed = True

    def close(self) -> None:
        self.journal.close()

    async def arestore_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self.restore_messages, messages)

    async def afinalize(self, outcome: str = "succeeded") -> None:
        await asyncio.to_thread(self.finalize, outcome)

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)


def begin_durable_run(agent: Any, prompt: str):
    """Create and activate a context, or return ``(None, None)`` when disabled."""
    execution = getattr(agent, "execution", None)
    if execution is None or not getattr(execution, "durable", False):
        return None, None
    if _active_durable_run.get() is not None:
        return None, None

    context = _open_durable_run(agent, prompt)
    token = _active_durable_run.set(context)
    return context, token


def _open_durable_run(agent: Any, prompt: str) -> DurableRunContext:
    """Open journal state without mutating the caller's ContextVar."""
    execution = agent.execution

    journal = RunJournal(getattr(execution, "journal_path", None))
    resume_run_id = getattr(execution, "resume_run_id", None)
    replaying = bool(resume_run_id)
    run_id = str(resume_run_id or uuid4())

    if replaying:
        metadata = journal.run_meta(run_id)
        if metadata is None:
            journal.close()
            raise ValueError(f"Cannot resume unknown durable run {run_id!r}")
        if metadata.status != "running":
            journal.close()
            raise ValueError(
                f"Cannot resume terminal durable run {run_id!r} "
                f"(status={metadata.status!r})"
            )
        if metadata.task and metadata.task != prompt:
            journal.close()
            raise ValueError(
                "Resume prompt does not match the prompt recorded for durable "
                f"run {run_id!r}"
            )

    journal.open_run(
        run_id,
        agent=getattr(agent, "name", ""),
        task=prompt,
        metadata={"version": 1, "explicit_resume": replaying},
    )
    context = DurableRunContext(journal, run_id, replaying=replaying)
    agent._last_durable_run_id = run_id
    return context


async def abegin_durable_run(agent: Any, prompt: str):
    """Async durable-run creation with all SQLite I/O off the event loop."""
    execution = getattr(agent, "execution", None)
    if execution is None or not getattr(execution, "durable", False):
        return None, None
    if _active_durable_run.get() is not None:
        return None, None
    context = await asyncio.to_thread(_open_durable_run, agent, prompt)
    token = _active_durable_run.set(context)
    return context, token


def end_durable_run(token) -> None:
    if token is not None:
        _active_durable_run.reset(token)


def get_durable_run() -> Optional[DurableRunContext]:
    return _active_durable_run.get()


def get_durable_idempotency_key() -> Optional[str]:
    """Return the stable key for the currently executing durable tool call."""
    return _active_idempotency_key.get()
