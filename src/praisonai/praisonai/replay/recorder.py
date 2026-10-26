"""Record a run to a replay trace: ``with praisonai.replay.record(): ...``.

One place owns the writer + emitter + context-var setup that the CLI, the
workflow runner and recipes used to duplicate::

    from praisonai.replay import record

    with record(live=True) as rec:
        Agent(name="a", instructions="...").start("Say hello")
    print(rec.run_id, rec.path)

Everything the emitter records is redacted by default (the emitter's own
``redact=True``). ``live=True`` writes every event to disk as it happens
(``buffer_size=1``) so ``praisonai replay view --live`` can follow the run.
"""

from __future__ import annotations

import contextlib
import inspect
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

__all__ = ["Recording", "record", "new_run_id"]

#: Events buffered before a flush when not recording live (the writer's default).
BATCH_BUFFER_SIZE = 100


def new_run_id() -> str:
    """A fresh run id in the format the CLI has always used (``run-<12 hex>``)."""
    return f"run-{uuid.uuid4().hex[:12]}"


@dataclass
class Recording:
    """Handle yielded by :func:`record`."""

    run_id: str
    path: Path
    emitter: Any = field(repr=False, default=None)
    writer: Any = field(repr=False, default=None)
    live: bool = False
    #: Set to ``"failed"`` when the caller handled a failure itself, so
    #: ``session_end`` still reports it (an escaping exception does this too).
    status: Optional[str] = None


class _ForkTagSink:
    """Sink wrapper that stamps ``forked_from`` on the run's first ``workflow_start``."""

    def __init__(self, inner: Any, forked_from: Dict[str, Any]):
        self._inner = inner
        self._forked_from = dict(forked_from)
        self._tagged = False

    def emit(self, event: Any) -> None:
        if not self._tagged:
            kind = getattr(event, "event_type", None)
            kind = getattr(kind, "value", kind)
            if kind == "workflow_start":
                data = dict(getattr(event, "data", None) or {})
                data.setdefault("forked_from", dict(self._forked_from))
                try:
                    event.data = data
                except Exception:
                    pass
                self._tagged = True
        self._inner.emit(event)

    def flush(self) -> None:
        self._inner.flush()

    def close(self) -> None:
        self._inner.close()


def _make_emitter(sink: Any, run_id: str, full_content: bool):
    from praisonaiagents.trace.context_events import ContextTraceEmitter

    kwargs: Dict[str, Any] = {"sink": sink, "session_id": run_id, "full_content": full_content}
    # Schema 1.1 emitters stamp ``run_id`` on every event; older ones do not
    # take it. The session id equals the run id either way.
    try:
        if "run_id" in inspect.signature(ContextTraceEmitter.__init__).parameters:
            kwargs["run_id"] = run_id
    except (TypeError, ValueError):
        pass
    return ContextTraceEmitter(**kwargs)


@contextlib.contextmanager
def record(
    run_id: Optional[str] = None,
    *,
    live: bool = False,
    meta: Optional[Dict[str, Any]] = None,
    full_content: Optional[bool] = None,
    _forked_from: Optional[Dict[str, Any]] = None,
) -> Iterator[Recording]:
    """Record everything run inside the block to ``<traces dir>/<run_id>.jsonl``.

    Args:
        run_id: Trace id and file name (default: ``run-<12 hex>``).
        live: Flush every event immediately so a viewer can follow the run.
        meta: Extra ``session_start`` data (e.g. ``{"yaml_path": ...}``, which
            ``praisonai replay rerun`` uses to find the definition again).
        full_content: Keep tool results / LLM responses untruncated.

    Yields:
        :class:`Recording` with ``run_id`` and ``path``.
    """
    from praisonaiagents.trace.context_events import reset_context_emitter, set_context_emitter

    from .writer import ContextTraceWriter

    run_id = run_id or new_run_id()
    writer = ContextTraceWriter(
        session_id=run_id, buffer_size=1 if live else BATCH_BUFFER_SIZE
    )
    sink: Any = _ForkTagSink(writer, _forked_from) if _forked_from else writer
    emitter = _make_emitter(sink, run_id, bool(full_content))
    token = set_context_emitter(emitter)
    started = time.time()
    rec = Recording(run_id=run_id, path=writer.path, emitter=emitter, writer=writer, live=live)

    start_meta: Dict[str, Any] = dict(meta or {})
    start_meta.setdefault("run_id", run_id)
    if _forked_from:
        start_meta.setdefault("forked_from", dict(_forked_from))
    status = "completed"
    try:
        emitter.session_start(start_meta)
        yield rec
    except BaseException:
        status = "failed"
        raise
    finally:
        try:
            emitter.session_end(
                {"status": rec.status or status, "duration_ms": round((time.time() - started) * 1000, 1)}
            )
        finally:
            writer.close()
            reset_context_emitter(token)
