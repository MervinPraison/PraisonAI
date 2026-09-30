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


# Maximum forensic backups of a malformed file kept before the oldest is
# pruned, so a boot-loop on a permanently-bad file cannot fill the disk.
_MAX_FORENSIC_BACKUPS = 3
# A malformed file is repaired at most this many times before the guard gives
# up (records the exhaustion in a sidecar ledger) and stops re-repairing on
# every boot, so a permanently-bad file is not churned each start.
_MAX_REPAIR_ATTEMPTS = 3


def quick_check(conn) -> bool:
    """Return True if ``PRAGMA quick_check`` reports the database is intact.

    ``quick_check`` is the cheap structural probe (it skips the exhaustive
    per-row index cross-check that ``integrity_check`` does), so it is safe to
    run once on open without touching the hot path. Any SQLite-level error
    (a malformed header, "database disk image is malformed", an I/O error) is
    treated as *not intact* so the caller can route to backup/repair.
    """
    try:
        row = conn.execute("PRAGMA quick_check(1)").fetchone()
    except Exception as exc:  # DatabaseError / OperationalError on a bad file
        logger.warning("quick_check raised for database (%s); treating as corrupt.", exc)
        return False
    return bool(row) and str(row[0]).lower() == "ok"


def _sidecar_paths(path: str):
    """Return the WAL/SHM sidecar paths for a database file."""
    return [path + "-wal", path + "-shm"]


def _forensic_backup(path: str) -> Optional[str]:
    """Copy a malformed database (+WAL/SHM sidecars) aside for forensics.

    Mirrors the JSON store's ``_quarantine_corrupt`` behaviour: the raw,
    possibly-recoverable bytes are preserved as ``<file>.corrupt-<epoch_ms>``
    instead of being clobbered by a repair. Fails **closed** — returns ``None``
    without copying — when free disk space is below the file size plus a margin,
    so a corruption event never itself fills the disk. Retention-capped so a
    boot-loop cannot accumulate unbounded copies.
    """
    import shutil
    import time as _time

    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    try:
        free = shutil.disk_usage(os.path.dirname(path) or ".").free
    except OSError:
        free = None
    # Fail closed on low disk: need room for the file plus a small margin.
    if free is not None and free < size * 2 + (1 << 20):
        logger.error(
            "Skipping forensic backup of %s: insufficient free disk space.", path
        )
        return None

    base = f"{path}.corrupt-{int(_time.time() * 1000)}"
    dest = base
    attempt = 1
    while os.path.exists(dest):
        dest = f"{base}-{attempt}"
        attempt += 1
    try:
        shutil.copy2(path, dest)
    except OSError as exc:
        logger.error("Forensic backup of %s failed: %s", path, exc)
        return None
    # Best-effort sidecar preservation; their absence is not fatal. Each sidecar
    # is ``path + suffix`` (e.g. ``-wal``), copied next to the primary backup so
    # a later analysis can replay the write-ahead log.
    for sidecar in _sidecar_paths(path):
        if os.path.exists(sidecar):
            suffix = sidecar[len(path):]
            try:
                shutil.copy2(sidecar, dest + suffix)
            except OSError:
                pass
    _prune_forensic_backups(path)
    return dest


def _prune_forensic_backups(path: str) -> None:
    """Keep only the newest ``_MAX_FORENSIC_BACKUPS`` forensic copies."""
    directory = os.path.dirname(path) or "."
    prefix = os.path.basename(path) + ".corrupt-"
    try:
        entries = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.startswith(prefix)
        ]
    except OSError:
        return
    # Only prune the primary DB copies (no sidecar suffix like ``-wal``).
    copies = [p for p in entries if not (p.endswith("-wal") or p.endswith("-shm"))]
    if len(copies) <= _MAX_FORENSIC_BACKUPS:
        return
    copies.sort(key=lambda p: os.path.getmtime(p))
    for stale in copies[: len(copies) - _MAX_FORENSIC_BACKUPS]:
        try:
            os.remove(stale)
        except OSError:
            pass


def _repair_ledger_path(path: str) -> str:
    return path + ".repair"


def _repair_budget_ok(path: str) -> bool:
    """Return True while the file still has repair attempts left in its budget.

    A sidecar ledger (``<file>.repair``) records how many repairs have been
    attempted so a permanently-malformed file is not re-repaired on every boot
    (bounded persistent retry). Missing/unreadable ledger means a fresh budget.
    """
    try:
        with open(_repair_ledger_path(path), "r", encoding="utf-8") as fh:
            attempts = int(fh.read().strip() or "0")
    except (OSError, ValueError):
        attempts = 0
    return attempts < _MAX_REPAIR_ATTEMPTS


def _record_repair_attempt(path: str) -> None:
    try:
        with open(_repair_ledger_path(path), "r", encoding="utf-8") as fh:
            attempts = int(fh.read().strip() or "0")
    except (OSError, ValueError):
        attempts = 0
    try:
        with open(_repair_ledger_path(path), "w", encoding="utf-8") as fh:
            fh.write(str(attempts + 1))
    except OSError:
        pass


def _clear_repair_ledger(path: str) -> None:
    for p in (_repair_ledger_path(path),):
        try:
            os.remove(p)
        except OSError:
            pass


def _repair_via_online_backup(path: str) -> bool:
    """Attempt a least-destructive repair of a malformed database in place.

    Recovers what SQLite's online-backup API can read into a fresh snapshot and
    promotes it back with an atomic ``os.replace`` so the canonical file is only
    swapped for a *verified-intact* rebuild — a failed attempt never touches the
    original bytes (which are already preserved by :func:`_forensic_backup`).
    Returns True only when the rebuilt file itself passes ``quick_check``.
    """
    import sqlite3

    _record_repair_attempt(path)
    snapshot = path + ".repair-tmp"
    try:
        os.remove(snapshot)
    except OSError:
        pass
    src = dst = None
    try:
        src = sqlite3.connect(path)
        dst = sqlite3.connect(snapshot)
        src.backup(dst)  # copies all readable pages into the fresh file
        dst.commit()
    except Exception as exc:
        logger.warning("Online-backup repair of %s failed to read pages: %s", path, exc)
        for c in (src, dst):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
        try:
            os.remove(snapshot)
        except OSError:
            pass
        return False
    finally:
        for c in (src, dst):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass

    # Verify the rebuilt snapshot before promoting it over the canonical file.
    verify = None
    try:
        verify = sqlite3.connect(snapshot)
        intact = quick_check(verify)
    except Exception:
        intact = False
    finally:
        try:
            if verify is not None:
                verify.close()
        except Exception:
            pass
    if not intact:
        try:
            os.remove(snapshot)
        except OSError:
            pass
        return False

    try:
        # Drop stale sidecars of the malformed file so they cannot be replayed
        # over the rebuilt database. The malformed original + its sidecars are
        # already forensically backed up before we get here.
        for sidecar in _sidecar_paths(path):
            try:
                os.remove(sidecar)
            except OSError:
                pass
        os.replace(snapshot, path)
    except OSError as exc:
        logger.error("Could not promote repaired snapshot for %s: %s", path, exc)
        return False
    _clear_repair_ledger(path)
    logger.warning("Repaired malformed SQLite database %s via online backup.", path)
    return True


def _guard_integrity(path: str, *, repair: bool, backup: bool) -> None:
    """Detect and (optionally) repair a malformed database before first use.

    Runs a cheap ``quick_check`` on open; on failure it forensically backs up
    the malformed file (+sidecars) and attempts a bounded, least-destructive
    online-backup repair. A no-op for ``:memory:``/absent/empty files.
    """
    import sqlite3

    if not path or path == ":memory:" or not os.path.exists(path):
        return
    try:
        if os.path.getsize(path) == 0:
            return
    except OSError:
        return

    probe = None
    try:
        probe = sqlite3.connect(path)
        if quick_check(probe):
            return
    except Exception:
        pass
    finally:
        try:
            if probe is not None:
                probe.close()
        except Exception:
            pass

    logger.error("SQLite database %s failed integrity check; corrupt.", path)
    if backup:
        _forensic_backup(path)
    if repair and _repair_budget_ok(path):
        _repair_via_online_backup(path)


def connect(
    path,
    *,
    check_same_thread: bool = False,
    isolation_level: Optional[str] = "",
    busy_timeout_ms: int = 5000,
    synchronous: str = "FULL",
    guard: bool = False,
    repair: bool = True,
    backup: bool = True,
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
        guard: When True, run a one-time ``quick_check`` on open and, on a
            malformed file, forensically back it up and attempt a bounded
            least-destructive online-backup repair before connecting (Issue
            #5387). Off by default so existing callers are unchanged.
        repair: Attempt an online-backup repair on corruption (only when
            ``guard`` is set). Bounded by a sidecar attempt-ledger.
        backup: Take a retention-capped, disk-space-aware forensic backup of the
            malformed file before repair (only when ``guard`` is set).
        **kwargs: Forwarded to ``sqlite3.connect``.
    """
    import sqlite3  # lazy import — stdlib, no heavy dependency

    db_path = path
    if isinstance(path, (str, os.PathLike)) and str(path) != ":memory:":
        db_path = str(path)

    if guard:
        try:
            _guard_integrity(str(db_path), repair=repair, backup=backup)
        except Exception as exc:  # detection/repair must never block open
            logger.debug("Integrity guard skipped for %s: %s", db_path, exc)

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
