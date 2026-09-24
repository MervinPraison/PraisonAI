"""Hardened stdlib-only SQLite connection helper for core durable stores.

Every SQLite-backed store in the gateway/session/memory/run subsystems used to
open its connection with a bare ``PRAGMA journal_mode=WAL`` duplicated inline.
WAL relies on a shared-memory (``-shm``) sidecar and byte-range locking that
several common *deployment substrates* do not honour: NFS/SMB home
directories, FUSE / Docker-Desktop gRPC-FUSE mounts, overlayfs, virtiofs/9p on
cross-VM setups. On those filesystems WAL either errors (``disk I/O error``,
``database is locked``, ``unable to open database file``) or — worst case on a
cross-VM share — silently corrupts.

This module provides a single, lightweight, dependency-free factory that every
store can call so the hardening lives in one place:

    from praisonaiagents.storage.sqlite import connect
    conn = connect(db_path)

It attempts WAL and, on a filesystem that rejects it, transparently falls back
to ``journal_mode=DELETE`` — but **never live-downgrades a database whose
on-disk header already reports WAL** (a peer connection may hold uncheckpointed
commits). A read-only header probe runs first so initialisation never unlinks
sidecars another connection is using.

Only the standard library is used (``sqlite3`` is stdlib), so this adds zero
heavy dependencies and no import-time cost — it is lazy-imported by callers.
"""

from __future__ import annotations

import os
from typing import Optional

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

# SQLite database header: bytes 18 (write) / 19 (read) hold the file-format
# version numbers; both are 2 for a WAL database and 1 for rollback-journal
# (DELETE/TRUNCATE/PERSIST). Reading them lets us detect an existing WAL header
# without opening a write connection, so we never live-downgrade a DB a peer
# may hold uncheckpointed commits in.
_WAL_FILE_FORMAT = 2


def _resolve_probe_path(path: str) -> Optional[str]:
    """Resolve a connection target to the on-disk file to probe, or None.

    ``:memory:`` and anonymous/temporary databases have no header to read.
    ``file:`` URIs (used with ``uri=True``) embed the real filename plus a query
    string; parsing them back to the filesystem path keeps the no-downgrade
    header probe honest instead of stat-ing the URI text as a literal filename.
    """
    if not path or path == ":memory:":
        return None
    if path.startswith("file:"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(path)
        # In-memory / anonymous URIs (``file::memory:``, ``file:?...``) have no
        # backing file to probe.
        if not parsed.path or parsed.path == ":memory:":
            return None
        return unquote(parsed.path)
    return path


def _header_is_wal(path: str) -> Optional[bool]:
    """Return True/False if the on-disk header reports WAL, or None if unknown.

    Reads only the fixed 100-byte SQLite header, so it never touches sidecars
    or takes a lock. Returns None when the file is absent/empty/too short to
    have a header yet (a fresh DB), so the caller treats it as "free to set".
    Accepts either a plain filesystem path or a ``file:`` URI.
    """
    probe = _resolve_probe_path(path)
    if probe is None:
        return None
    try:
        with open(probe, "rb") as fh:
            header = fh.read(20)
    except (IOError, OSError):
        return None
    if len(header) < 20:
        return None
    return header[18] == _WAL_FILE_FORMAT and header[19] == _WAL_FILE_FORMAT


def apply_wal_with_fallback(
    conn, path: str, busy_timeout_ms: int = 5000, synchronous: str = "FULL"
) -> str:
    """Set a durable journal mode, falling back off WAL on hostile filesystems.

    Attempts ``journal_mode=WAL``. If the filesystem rejects it (a locking or
    ``disk I/O`` style error, common on NFS/SMB/FUSE/virtiofs), falls back to
    ``journal_mode=DELETE`` — unless the on-disk header already reports WAL, in
    which case the DB is left in WAL so a peer connection's uncheckpointed
    commits are never stranded. Returns the journal mode actually in effect.

    ``synchronous`` controls the ``PRAGMA synchronous`` durability level and
    defaults to ``FULL`` so committed writes survive an OS/power crash — this
    preserves the pre-hardening durability of the core stores (Issue #5264).
    Callers that favour throughput over the last-transaction durability window
    may pass ``synchronous="NORMAL"`` (safe under WAL against process crashes).
    """
    sync = (synchronous or "FULL").upper()

    try:
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    except Exception:  # pragma: no cover - busy_timeout is universally supported
        pass

    try:
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        mode = (row[0] if row else "").lower()
        if mode == "wal":
            try:
                conn.execute(f"PRAGMA synchronous={sync}")
            except Exception:
                pass
            return "wal"
    except Exception as exc:
        logger.info(
            "WAL journal mode unavailable for %s (%s); trying DELETE fallback.",
            path,
            exc,
        )

    # WAL did not take. Never live-downgrade a DB whose header already reports
    # WAL — another connection may hold uncheckpointed commits in the -wal file.
    # ``_header_is_wal`` resolves ``file:`` URIs and rejects ``:memory:`` itself.
    if _header_is_wal(path):
        logger.warning(
            "WAL requested but not applied for %s and its header already "
            "reports WAL; leaving as-is to avoid stranding peer commits.",
            path,
        )
        return "wal"

    try:
        row = conn.execute("PRAGMA journal_mode=DELETE").fetchone()
        mode = (row[0] if row else "delete").lower()
    except Exception as exc:
        logger.warning("Could not set DELETE journal mode for %s: %s", path, exc)
        return "unknown"
    try:
        # FULL is the safe default for rollback-journal mode on unreliable
        # filesystems; NORMAL is only durable under WAL.
        conn.execute("PRAGMA synchronous=FULL")
    except Exception:
        pass
    return mode


def connect(
    path,
    *,
    check_same_thread: bool = False,
    isolation_level: Optional[str] = "",
    busy_timeout_ms: int = 5000,
    synchronous: str = "FULL",
    **kwargs,
):
    """Open a hardened SQLite connection used by core durable stores.

    Applies :func:`apply_wal_with_fallback` so the connection uses WAL where the
    filesystem supports it and DELETE where it does not, with a sensible
    ``busy_timeout``. All keyword arguments other than the journal handling are
    forwarded to :func:`sqlite3.connect`.

    Args:
        path: Database path (``":memory:"`` supported).
        check_same_thread: Forwarded to ``sqlite3.connect`` (defaults False so
            stores may share a connection across threads under their own lock).
        isolation_level: Forwarded to ``sqlite3.connect``. Defaults to ``""``
            (sqlite3's default autocommit-off); pass ``None`` for autocommit.
        busy_timeout_ms: ``PRAGMA busy_timeout`` in milliseconds.
        synchronous: ``PRAGMA synchronous`` level. Defaults to ``FULL`` so
            committed writes survive an OS/power crash (matches pre-hardening
            durability). Pass ``"NORMAL"`` for higher throughput under WAL.
        **kwargs: Forwarded to ``sqlite3.connect``.
    """
    import sqlite3  # lazy import — stdlib, no heavy dependency

    db_path = path
    if isinstance(path, (str, os.PathLike)) and str(path) != ":memory:":
        db_path = str(path)

    connect_kwargs = dict(kwargs)
    connect_kwargs["check_same_thread"] = check_same_thread
    if isolation_level != "":
        connect_kwargs["isolation_level"] = isolation_level

    conn = sqlite3.connect(db_path, **connect_kwargs)
    try:
        apply_wal_with_fallback(
            conn,
            str(db_path),
            busy_timeout_ms=busy_timeout_ms,
            synchronous=synchronous,
        )
    except Exception as exc:  # never let hardening break connection creation
        logger.debug("Journal-mode hardening skipped for %s: %s", db_path, exc)
    return conn
