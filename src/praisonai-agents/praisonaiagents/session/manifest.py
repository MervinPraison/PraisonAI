"""
Session manifest: one durable record per ``session_id`` linking every
persistence plane of that session (Issue #6248).

The conversation store, workspace checkpoints, plans/todos, goal state and
artifacts each persist on their own. The manifest does not duplicate any of
them — it only records *references* to them (``refs``) plus a write-ahead
"run in flight" marker, so a later launch can tell that a run on this session
died before reaching a terminal outcome.

Usage::

    from praisonaiagents.session.manifest import FileSessionManifest

    manifest = FileSessionManifest()
    manifest.set_refs("my-session", checkpoint="abc123", plan="plan-1")

    entry = manifest.begin_run("my-session", "run-42", run_input="fix the bug")
    ...  # run the agent
    manifest.end_run("my-session", "completed")

    # Next launch:
    stale = manifest.interrupted("my-session")   # entry or None

A run that keeps dying is bounded by ``max_attempts``: once the budget is
spent, ``begin_run`` terminalises the stale marker (``run_status="abandoned"``)
instead of counting it as yet another attempt of the same run.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3

_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class ManifestEntry:
    """References to a session's durable planes and its last run's state."""

    session_id: str
    refs: Dict[str, Any] = field(default_factory=dict)
    run_id: Optional[str] = None
    run_status: Optional[str] = None
    run_in_flight: bool = False
    run_input: Optional[str] = None
    attempt: int = 0
    updated_at: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestEntry":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        if not isinstance(known.get("refs"), dict):
            known["refs"] = {}
        return cls(**known)


@runtime_checkable
class SessionManifestProtocol(Protocol):
    """Per-session manifest of plane references and run-in-flight marker."""

    def get(self, session_id: str) -> Optional[ManifestEntry]: ...

    def set_refs(self, session_id: str, **refs: Any) -> ManifestEntry: ...

    def begin_run(
        self,
        session_id: str,
        run_id: str,
        run_input: Optional[str] = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> ManifestEntry: ...

    def end_run(self, session_id: str, status: str) -> Optional[ManifestEntry]: ...

    def interrupted(self, session_id: str) -> Optional[ManifestEntry]: ...


class FileSessionManifest:
    """Default JSON-file manifest: ``<dir>/<session_id>.json``, atomic writes."""

    def __init__(self, directory: Optional[str] = None):
        if directory is None:
            from ..paths import get_sessions_dir

            directory = str(get_sessions_dir() / "manifests")
        self._dir = Path(directory)
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        if not session_id:
            raise ValueError("session_id is required")
        return self._dir / f"{_SAFE_ID.sub('_', session_id)}.json"

    def _read(self, session_id: str) -> Optional[ManifestEntry]:
        path = self._path(session_id)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            logger.warning("Unreadable session manifest %s: %s", path, exc)
            return None
        if not isinstance(data, dict):
            return None
        data["session_id"] = session_id
        return ManifestEntry.from_dict(data)

    def _write(self, entry: ManifestEntry) -> ManifestEntry:
        entry.updated_at = time.time()
        path = self._path(entry.session_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(asdict(entry), fh, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return entry

    def get(self, session_id: str) -> Optional[ManifestEntry]:
        with self._lock:
            return self._read(session_id)

    def set_refs(self, session_id: str, **refs: Any) -> ManifestEntry:
        """Merge plane references (e.g. ``checkpoint=``, ``plan=``) into the entry."""
        with self._lock:
            entry = self._read(session_id) or ManifestEntry(session_id=session_id)
            entry.refs.update(refs)
            return self._write(entry)

    def begin_run(
        self,
        session_id: str,
        run_id: str,
        run_input: Optional[str] = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> ManifestEntry:
        """Commit the write-ahead in-flight marker for a run on this session.

        If the previous run never released its marker it was interrupted; a new
        run with the same ``run_input`` counts as another attempt of it. Once
        ``max_attempts`` is exceeded the stale run is abandoned and the counter
        restarts, so a run that keeps dying is not counted up forever.
        """
        with self._lock:
            entry = self._read(session_id) or ManifestEntry(session_id=session_id)
            if entry.run_in_flight and entry.run_input == run_input:
                attempt = entry.attempt + 1
                if attempt > max_attempts:
                    logger.warning(
                        "Session %s: run %s abandoned after %d attempts",
                        session_id, entry.run_id, entry.attempt,
                    )
                    attempt = 1
            else:
                attempt = 1
            entry.run_id = run_id
            entry.run_input = run_input
            entry.run_status = "running"
            entry.run_in_flight = True
            entry.attempt = attempt
            return self._write(entry)

    def end_run(self, session_id: str, status: str) -> Optional[ManifestEntry]:
        """Release the in-flight marker with a terminal ``status``."""
        with self._lock:
            entry = self._read(session_id)
            if entry is None:
                return None
            entry.run_in_flight = False
            entry.run_status = status
            return self._write(entry)

    def interrupted(self, session_id: str) -> Optional[ManifestEntry]:
        """Return the entry if its last run never reached a terminal outcome."""
        entry = self.get(session_id)
        return entry if entry is not None and entry.run_in_flight else None


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "FileSessionManifest",
    "ManifestEntry",
    "SessionManifestProtocol",
]
