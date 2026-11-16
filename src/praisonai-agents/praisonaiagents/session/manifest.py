"""
Session manifest: one durable record per ``session_id`` holding a write-ahead
"run in flight" marker (Issue #6248), so a later launch can tell that a run on
this session died before reaching a terminal outcome.

Usage::

    from praisonaiagents.session.manifest import FileSessionManifest

    manifest = FileSessionManifest()
    entry = manifest.begin_run("my-session", "run-42", run_input="fix the bug")
    ...  # run the agent
    manifest.end_run("my-session", "completed", run_id="run-42")

    # Next launch:
    stale = manifest.interrupted("my-session")   # entry or None

The run input itself is never written to disk: only a SHA-256 digest of it
is kept (``run_digest``), enough to recognise a retry of the same task without
storing prompts (which may contain secrets) in plaintext.

A run that keeps dying is bounded by ``max_attempts``: once the budget is
spent, ``begin_run`` logs the stale run as abandoned and restarts the attempt
counter instead of counting it up forever.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Protocol, runtime_checkable

from .store import FileLock, _safe_session_filename

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3


@dataclass
class ManifestEntry:
    """A session's last run state."""

    session_id: str
    run_id: Optional[str] = None
    run_status: Optional[str] = None
    run_in_flight: bool = False
    run_digest: Optional[str] = None
    attempt: int = 0
    updated_at: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestEntry":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def _digest(run_input: Optional[str]) -> Optional[str]:
    if run_input is None:
        return None
    return hashlib.sha256(run_input.encode("utf-8")).hexdigest()


@runtime_checkable
class SessionManifestProtocol(Protocol):
    """Per-session run-in-flight marker."""

    def get(self, session_id: str) -> Optional[ManifestEntry]: ...

    def begin_run(
        self,
        session_id: str,
        run_id: str,
        run_input: Optional[str] = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> ManifestEntry: ...

    def end_run(
        self, session_id: str, status: str, run_id: Optional[str] = None
    ) -> Optional[ManifestEntry]: ...

    def interrupted(self, session_id: str) -> Optional[ManifestEntry]: ...


class FileSessionManifest:
    """Default JSON-file manifest: ``<dir>/<session_id>.json``, atomic writes."""

    def __init__(self, directory: Optional[str] = None):
        """``directory`` defaults to ``<sessions>/manifests``; callers whose
        session store is scoped (e.g. per project) should pass the matching
        directory so equal ids in different scopes never share a manifest."""
        if directory is None:
            from ..paths import get_sessions_dir

            directory = str(get_sessions_dir() / "manifests")
        self._dir = Path(directory)
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        if not session_id:
            raise ValueError("session_id is required")
        # Same injective naming as the conversation store: ids that differ
        # only in ``:``/``.``/``/`` never share a file, and none escape ``_dir``.
        return self._dir / f"{_safe_session_filename(session_id)}.json"

    @contextmanager
    def _locked(self, session_id: str) -> Iterator[None]:
        """Serialise read-modify-write across threads *and* processes."""
        with self._lock, FileLock(str(self._path(session_id))):
            yield

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

    def begin_run(
        self,
        session_id: str,
        run_id: str,
        run_input: Optional[str] = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> ManifestEntry:
        """Commit the write-ahead in-flight marker for a run on this session.

        Only a digest of ``run_input`` is persisted, never the text itself.
        If the previous run never released its marker it was interrupted; a new
        run with the same ``run_input`` counts as another attempt of it. Once
        ``max_attempts`` is exceeded the stale run is abandoned and the counter
        restarts, so a run that keeps dying is not counted up forever.
        """
        with self._locked(session_id):
            entry = self._read(session_id) or ManifestEntry(session_id=session_id)
            digest = _digest(run_input)
            if entry.run_in_flight and entry.run_digest == digest:
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
            entry.run_digest = digest
            entry.run_status = "running"
            entry.run_in_flight = True
            entry.attempt = attempt
            return self._write(entry)

    def end_run(
        self, session_id: str, status: str, run_id: Optional[str] = None
    ) -> Optional[ManifestEntry]:
        """Release the in-flight marker with a terminal ``status``.

        With ``run_id``, only that run's own marker is released: if another
        run on the same session has since taken the marker, it is left alone
        (returns ``None``) so that run's later crash is still reported.
        """
        with self._locked(session_id):
            entry = self._read(session_id)
            if entry is None or (run_id is not None and entry.run_id != run_id):
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
