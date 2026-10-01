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
from typing import Any

__all__ = ["atomic_write_json", "atomic_write_text"]


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
