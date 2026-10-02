"""
Last-run trace pointer for PraisonAI Agents.

Persists a tiny pointer to the most recently completed traced run so tools
(e.g. ``praisonai eval last-trace``) can grade the last run without a manual
JSON export. Uses only stdlib for zero dependencies and writes atomically.

Usage:
    from praisonaiagents.trace.last_run import record_completed_run, load_last_run_pointer

    record_completed_run("trace.jsonl", meta={"agent": "researcher"})
    pointer = load_last_run_pointer()  # -> {"path": "...", "meta": {...}} or None
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Schema version for forward compatibility
POINTER_SCHEMA_VERSION = "1.0"


def _pointer_dir() -> Path:
    """Directory holding the last-run pointer.

    Honours ``PRAISON_HOME`` so tests and sandboxed runs can redirect state.
    """
    home = os.environ.get("PRAISON_HOME")
    base = Path(home) if home else Path.home() / ".praison"
    return base


def last_run_pointer_path() -> Path:
    """Absolute path to the last-run pointer file."""
    return _pointer_dir() / "last_trace.json"


def _atomic_write(path: Path, data: str) -> None:
    """Write ``data`` to ``path`` atomically via a temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def record_completed_run(
    trace_path: Any,
    meta: Optional[Dict[str, Any]] = None,
) -> Path:
    """Persist a pointer to the trace file of the just-completed run.

    Args:
        trace_path: Path to the trace artifact (JSON or JSONL).
        meta: Optional run metadata (agent name, status, etc.).

    Returns:
        The path the pointer was written to.
    """
    pointer = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "path": str(Path(trace_path).resolve()),
        "recorded_at": time.time(),
        "meta": dict(meta) if meta else {},
    }
    target = last_run_pointer_path()
    _atomic_write(target, json.dumps(pointer))
    return target


def load_last_run_pointer() -> Optional[Dict[str, Any]]:
    """Load the last-run pointer, or ``None`` if none has been recorded.

    Returns ``None`` for a missing or malformed pointer file rather than
    raising, so callers can emit a typed "no completed run" message.
    """
    path = last_run_pointer_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("path"):
        return None
    return data
