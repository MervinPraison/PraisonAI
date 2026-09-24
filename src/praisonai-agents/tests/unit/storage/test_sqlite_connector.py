"""Tests for the hardened stdlib SQLite connection factory (Issue #5264)."""

import os

import pytest

from praisonaiagents.storage.sqlite import (
    apply_wal_with_fallback,
    connect,
    _header_is_wal,
)


def test_connect_uses_wal_on_normal_fs(tmp_path):
    db = str(tmp_path / "state.db")
    conn = connect(db)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        assert mode == "wal"
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
    finally:
        conn.close()


def test_connect_memory_db():
    conn = connect(":memory:")
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (7)")
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 7
    finally:
        conn.close()


def test_header_is_wal_reports_wal_after_connect(tmp_path):
    db = str(tmp_path / "state.db")
    conn = connect(db)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    assert _header_is_wal(db) is True


def test_header_is_wal_none_for_missing_file(tmp_path):
    assert _header_is_wal(str(tmp_path / "does_not_exist.db")) is None


class _WalRejectingConn:
    """Proxy that makes ``PRAGMA journal_mode=WAL`` fail (hostile filesystem).

    ``sqlite3.Connection.execute`` is read-only so it cannot be monkeypatched
    directly; this thin proxy forwards everything else to the real connection.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str) and "journal_mode=WAL" in sql:
            raise Exception("disk I/O error")
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_fallback_to_delete_when_wal_rejected(tmp_path):
    """When WAL cannot be applied and the header is not WAL, fall back to DELETE."""
    import sqlite3

    db = str(tmp_path / "fresh.db")
    # Seed a plain rollback-journal (non-WAL) database on disk so the header
    # probe reports non-WAL and the fallback is allowed to proceed.
    seed = sqlite3.connect(db)
    seed.execute("PRAGMA journal_mode=DELETE")
    seed.execute("CREATE TABLE t (x INTEGER)")
    seed.commit()
    seed.close()
    assert _header_is_wal(db) is False

    conn = sqlite3.connect(db)
    mode = apply_wal_with_fallback(_WalRejectingConn(conn), db)
    assert mode == "delete"
    conn.close()


def test_never_downgrades_existing_wal_header(tmp_path):
    """A DB whose on-disk header already reports WAL is never live-downgraded."""
    db = str(tmp_path / "state.db")
    # First connection puts a real WAL header on disk.
    c0 = connect(db)
    c0.execute("CREATE TABLE t (x INTEGER)")
    c0.commit()
    c0.close()
    assert _header_is_wal(db) is True

    conn = connect(db)
    # WAL "fails" but header says WAL -> must stay WAL, not downgrade to DELETE.
    mode = apply_wal_with_fallback(_WalRejectingConn(conn), db)
    assert mode == "wal"
    conn.close()


def test_connect_defaults_to_full_synchronous_under_wal(tmp_path):
    """Durability: WAL connections keep ``synchronous=FULL`` by default.

    Guards against the regression where memory/LTM writes silently dropped from
    FULL to NORMAL, losing the last committed transaction on a power crash.
    """
    db = str(tmp_path / "durable.db")
    conn = connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        # synchronous is reported as an integer: 2 == FULL (1 == NORMAL).
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
    finally:
        conn.close()


def test_connect_honours_normal_synchronous_opt_in(tmp_path):
    db = str(tmp_path / "fast.db")
    conn = connect(db, synchronous="NORMAL")
    try:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        conn.close()


def test_connect_integration_falls_back_to_delete(tmp_path, monkeypatch):
    """End-to-end: an injected WAL rejection routes ``connect()`` to DELETE.

    Exercises the public factory (not just ``apply_wal_with_fallback``) so a
    regression in the deployment-specific fallback wiring is caught.
    """
    import sqlite3

    real_connect = sqlite3.connect

    def _wal_rejecting_connect(*args, **kwargs):
        return _WalRejectingConn(real_connect(*args, **kwargs))

    db = str(tmp_path / "hostile.db")
    monkeypatch.setattr(sqlite3, "connect", _wal_rejecting_connect)

    conn = connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
        # DELETE fallback must stay fully durable (2 == FULL).
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
    finally:
        conn.close()


def test_resolve_probe_path_handles_file_uri(tmp_path):
    """A ``file:`` URI resolves back to its real path for the header probe."""
    from praisonaiagents.storage.sqlite import _resolve_probe_path

    db = tmp_path / "state.db"
    conn = connect(str(db))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    assert _header_is_wal(db.as_uri()) is True
    assert _resolve_probe_path(str(db)) == str(db)
    assert _resolve_probe_path(":memory:") is None
    assert _resolve_probe_path("file::memory:?cache=shared") is None


def test_lazy_export_from_storage_package():
    from praisonaiagents.storage import sqlite_connect

    assert sqlite_connect is connect
