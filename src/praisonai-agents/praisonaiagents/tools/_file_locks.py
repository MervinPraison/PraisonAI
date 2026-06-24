"""Shared concurrency primitives for the built-in file/edit tools.

This module provides process-wide, per-canonical-path locking and an
automatic last-read-hash registry so that the built-in ``FileTools`` and
``EditTools`` can guarantee two production-robustness properties **by
default**:

1. **Per-file concurrency safety** — a keyed lock per canonical file path
   serialises read-modify-write on the same file, so parallel tool calls or
   multi-agent teams sharing a workspace cannot interleave and corrupt a
   shared file.  Different files still proceed in parallel.
2. **Automatic stale-write protection** — a read records the on-disk content
   hash for that path; a later edit/write recomputes the on-disk hash and
   aborts on mismatch unless the caller opts out (``force=True``) or supplies
   an explicit ``expected_hash``.

The state lives at module scope so it is shared across every ``FileTools`` /
``EditTools`` instance (and the module-level default instances), which is what
makes the guarantee hold across separate tool calls in an agent loop.
"""

import threading
import weakref

# Guards access to the registries below.
_registry_lock = threading.Lock()

# Per-canonical-path re-entrant locks.  ``WeakValueDictionary`` lets unused
# locks be garbage collected once no caller holds a reference, avoiding
# unbounded growth for long-running agents touching many files.
_path_locks: "weakref.WeakValueDictionary[str, threading.RLock]" = (
    weakref.WeakValueDictionary()
)

# Automatic last-read content hash per canonical path.  Populated on read,
# consulted on write/edit for the default staleness guard.
_read_hashes = {}


def get_lock(canonical_path: str) -> threading.RLock:
    """Return the shared re-entrant lock for ``canonical_path``.

    The same lock object is returned for the same path across all callers, so
    independent ``FileTools``/``EditTools`` instances serialise correctly on a
    shared file.  Re-entrant so a single thread can nest read+edit safely.
    """
    with _registry_lock:
        lock = _path_locks.get(canonical_path)
        if lock is None:
            lock = threading.RLock()
            _path_locks[canonical_path] = lock
        return lock


def record_read_hash(canonical_path: str, content_hash: str) -> None:
    """Record the content hash observed when ``canonical_path`` was read."""
    with _registry_lock:
        _read_hashes[canonical_path] = content_hash


def get_read_hash(canonical_path: str):
    """Return the last recorded read hash for ``canonical_path`` (or None)."""
    with _registry_lock:
        return _read_hashes.get(canonical_path)


def clear_read_hash(canonical_path: str) -> None:
    """Forget any recorded read hash for ``canonical_path`` (e.g. on delete)."""
    with _registry_lock:
        _read_hashes.pop(canonical_path, None)
