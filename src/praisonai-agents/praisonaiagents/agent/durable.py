"""Opt-in durable tool-loop context backed by :class:`RunJournal`."""

from __future__ import annotations

import contextvars
import inspect
import json
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

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
        for event in events:
            if event.kind != KIND_TOOL_RESULT:
                continue
            tool_call_id = event.payload.get("tool_call_id")
            if tool_call_id:
                self._results_by_tool_call_id[str(tool_call_id)] = event.payload.get(
                    "result"
                )

    @property
    def completed_steps(self) -> int:
        return sum(
            1
            for (seq, kind) in self._replay
            if kind == KIND_TOOL_RESULT
        )

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
    ) -> Tuple[int, str]:
        with self._lock:
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
        return seq, call_id

    def _record_result(self, seq: int, tool_call_id: str, result: Any) -> Any:
        safe_result = _json_safe(result)
        self.journal.append(
            JournalEvent(
                self.run_id,
                seq,
                KIND_TOOL_RESULT,
                {"tool_call_id": tool_call_id, "result": safe_result},
            )
        )
        self.journal.append(
            JournalEvent(
                self.run_id,
                seq,
                KIND_ITERATION,
                {"index": seq},
            )
        )
        with self._lock:
            self._results_by_tool_call_id[tool_call_id] = safe_result
            self._replay[(seq, KIND_TOOL_RESULT)] = {
                "tool_call_id": tool_call_id,
                "result": safe_result,
            }
        return safe_result

    def wrap_sync(self, execute_tool_fn: Optional[Callable]) -> Optional[Callable]:
        if execute_tool_fn is None:
            return None

        def execute(function_name, arguments, tool_call_id=None, **kwargs):
            call_id = str(tool_call_id) if tool_call_id is not None else None
            if call_id and call_id in self._results_by_tool_call_id:
                return self._results_by_tool_call_id[call_id]
            seq, call_id = self._allocate_step(
                function_name, arguments, tool_call_id
            )
            try:
                result = execute_tool_fn(
                    function_name,
                    arguments,
                    tool_call_id=tool_call_id,
                    **kwargs,
                )
            except Exception as exc:
                result = {"error": str(exc)}
            return self._record_result(seq, call_id, result)

        return execute

    def wrap_async(self, execute_tool_fn: Optional[Callable]) -> Optional[Callable]:
        if execute_tool_fn is None:
            return None

        async def execute(function_name, arguments, tool_call_id=None, **kwargs):
            call_id = str(tool_call_id) if tool_call_id is not None else None
            if call_id and call_id in self._results_by_tool_call_id:
                return self._results_by_tool_call_id[call_id]
            seq, call_id = self._allocate_step(
                function_name, arguments, tool_call_id
            )
            try:
                result = execute_tool_fn(
                    function_name,
                    arguments,
                    tool_call_id=tool_call_id,
                    **kwargs,
                )
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                result = {"error": str(exc)}
            return self._record_result(seq, call_id, result)

        return execute

    def finalize(self, outcome: str = "succeeded") -> None:
        if not self._closed:
            self.journal.close_run(self.run_id, outcome)
            self._closed = True

    def close(self) -> None:
        self.journal.close()


def begin_durable_run(agent: Any, prompt: str):
    """Create and activate a context, or return ``(None, None)`` when disabled."""
    execution = getattr(agent, "execution", None)
    if execution is None or not getattr(execution, "durable", False):
        return None, None

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
    token = _active_durable_run.set(context)
    agent._last_durable_run_id = run_id
    return context, token


def end_durable_run(token) -> None:
    if token is not None:
        _active_durable_run.reset(token)


def get_durable_run() -> Optional[DurableRunContext]:
    return _active_durable_run.get()
