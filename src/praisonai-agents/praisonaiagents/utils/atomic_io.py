"""
Atomic JSON persistence helper.

Consolidates the temp-file-plus-``os.replace`` pattern already used across the
SDK (scheduler stores, session store, skills manager, gateway protocols) into a
single shared writer. Serialisation happens on the temp file *before* the target
is touched, so a crash, OOM kill, or a non-serialisable value can never truncate
the previous good file: the old bytes stay intact and ``os.replace`` swaps in the
new content atomically on both POSIX and Windows.
"""

import json
import os
import tempfile
import threading
import time
from collections import defaultdict
from typing import Any, Callable

__all__ = [
    "atomic_write_json",
    "atomic_write_text",
    "quarantine_corrupt_file",
    "update_json",
]

# Per-path in-process mutexes so threads in one process serialise before they
# even reach the cross-process ``FileLock``. Keyed by absolute path.
_path_mutexes: "defaultdict[str, threading.RLock]" = defaultdict(threading.RLock)


def atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` (temp file + ``os.replace``).

    For already-serialised payloads (markdown, pre-dumped JSON strings) where
    the caller holds a string rather than a JSON-serialisable object. The old
    file is untouched until the fully-written temp file is swapped in.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(
        dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, data: Any, **dump_kwargs: Any) -> None:
    """Atomically serialise ``data`` as JSON to ``path``.

    Writes to a temp file in the target's directory, fsyncs it, then
    ``os.replace``\\ s it into place. If serialisation or the write fails the
    temp file is removed and the original ``path`` is left untouched.

    Args:
        path: Destination file path.
        data: JSON-serialisable object.
        **dump_kwargs: Passed through to :func:`json.dump` (e.g. ``indent=2``).
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(
        dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def quarantine_corrupt_file(path: str) -> str:
    """Move a corrupt file aside to a unique ``.corrupt`` sidecar.

    Each quarantine uses a distinct ``<path>.<pid>.<ns>.corrupt`` name so a
    file that goes corrupt more than once never overwrites an earlier recovery
    copy. The move uses :func:`os.replace` (atomic rename) and the chosen
    destination is reported back. Raises ``OSError`` on failure so the caller
    can stop instead of overwriting potentially recoverable bytes.
    """
    dest = "{path}.{pid}.{ns}.corrupt".format(
        path=path, pid=os.getpid(), ns=time.time_ns()
    )
    os.replace(path, dest)
    return dest


def update_json(
    path: str,
    mutate: Callable[[Any], Any],
    default: Callable[[], Any] = dict,
    **dump_kwargs: Any,
) -> Any:
    """Locked read-modify-write for a JSON file.

    Holds a per-path in-process mutex *and* the cross-process
    :class:`~praisonaiagents.session.store.FileLock` for the whole
    read-modify-write, so concurrent threads and processes no longer lose each
    other's updates (last-writer-wins). The write goes through
    :func:`atomic_write_json`, so a crash mid-write never truncates the previous
    good file.

    A corrupt JSON file is *not* treated as empty: it is moved aside to a
    unique ``<path>.<pid>.<ns>.corrupt`` sidecar and the update proceeds from
    ``default()`` so a single torn file can never silently wipe real data
    without leaving evidence. If the quarantine move itself fails, the error
    propagates instead of overwriting the original file.

    Args:
        path: JSON file path.
        mutate: Callable invoked with the loaded data; mutate it in place.
        default: Factory for the initial value when the file is missing/corrupt.
        **dump_kwargs: Passed through to :func:`json.dump` (e.g. ``indent=2``).

    Returns:
        Whatever ``mutate`` returns (useful for surfacing the new item/length).
    """
    # Imported lazily to avoid a package-level import cycle (session -> utils).
    from ..session.store import FileLock

    abspath = os.path.abspath(path)
    with _path_mutexes[abspath], FileLock(path, timeout=10):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = default()
        except (json.JSONDecodeError, ValueError):
            # Quarantine under a unique name; if the move itself fails we must
            # NOT fall through to the atomic write, which would replace the
            # original and destroy its potentially recoverable bytes.
            quarantine_corrupt_file(path)
            data = default()
        result = mutate(data)
        atomic_write_json(path, data, **dump_kwargs)
        return result
