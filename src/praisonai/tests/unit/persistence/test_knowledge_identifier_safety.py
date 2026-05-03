"""Regression tests for GHSA-3643-7v76-5cj2.

Knowledge-store backends interpolate collection names directly into
DDL/DML because SQL/CQL identifiers cannot be parameterized. Untrusted
collection names like ``"x; DROP TABLE users; --"`` were therefore
flowing straight into ``CREATE TABLE`` / ``DROP TABLE`` / ``SELECT``
statements. The fix validates every identifier through
:func:`praisonai.persistence.knowledge.base.validate_identifier` (an
allowlist of ``[A-Za-z0-9_]+``) at the public API entry points.

These tests do not require a live database — they exercise the
validation gate with a fake driver, so attacker-controlled SQL never
reaches the cursor.
"""

from __future__ import annotations

import sys
import types
from typing import Any, List

import pytest

from praisonai.persistence.knowledge.base import validate_identifier


MALICIOUS = [
    "x; DROP TABLE users; --",
    "../etc/passwd",
    "name with spaces",
    "name-with-dashes",
    "",
    "name`backtick`",
    "name'quote'",
    "name\"dquote\"",
    "name(paren)",
]


def test_validate_identifier_accepts_safe():
    assert validate_identifier("safe_name_123") == "safe_name_123"


@pytest.mark.parametrize("bad", MALICIOUS)
def test_validate_identifier_rejects_malicious(bad):
    with pytest.raises(ValueError):
        validate_identifier(bad)


# ---------------------------------------------------------------------------
# Per-backend gate: ensure the validator fires before any SQL is executed.
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, parent): self.parent = parent
    def execute(self, query, params=None):
        self.parent.calls.append((query, params))
    def fetchone(self): return (0,)
    def fetchall(self): return []
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeConn:
    def __init__(self):
        self.calls: List[Any] = []
    def cursor(self, *a, **kw): return _FakeCursor(self)
    def commit(self): pass


def _stub_psycopg2(monkeypatch):
    psycopg2 = types.ModuleType("psycopg2")
    extras = types.ModuleType("psycopg2.extras")
    pool = types.ModuleType("psycopg2.pool")

    class _DummyPool:
        def __init__(self, *a, **k): pass
        def getconn(self): return _FakeConn()
        def putconn(self, c): pass

    pool.ThreadedConnectionPool = _DummyPool
    extras.RealDictCursor = object
    psycopg2.pool = pool
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.pool", pool)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)


def test_pgvector_rejects_malicious_collection(monkeypatch):
    _stub_psycopg2(monkeypatch)
    from praisonai.persistence.knowledge.pgvector import PGVectorKnowledgeStore

    store = PGVectorKnowledgeStore(auto_create_extension=False)
    with pytest.raises(ValueError):
        store.create_collection("x; DROP TABLE users; --", 3)
    with pytest.raises(ValueError):
        store.delete_collection("x; DROP TABLE users; --")


def test_pgvector_rejects_malicious_schema(monkeypatch):
    _stub_psycopg2(monkeypatch)
    from praisonai.persistence.knowledge.pgvector import PGVectorKnowledgeStore

    with pytest.raises(ValueError):
        PGVectorKnowledgeStore(schema="public; DROP TABLE x", auto_create_extension=False)


def test_singlestore_rejects_malicious_collection(monkeypatch):
    s2 = types.ModuleType("singlestoredb")
    s2.connect = lambda *a, **k: _FakeConn()
    monkeypatch.setitem(sys.modules, "singlestoredb", s2)
    from praisonai.persistence.knowledge.singlestore_vector import (
        SingleStoreVectorKnowledgeStore,
    )

    store = SingleStoreVectorKnowledgeStore()
    with pytest.raises(ValueError):
        store.create_collection("x; DROP TABLE u; --")
    with pytest.raises(ValueError):
        store.delete_collection("x; DROP TABLE u; --")
    with pytest.raises(ValueError):
        store.count("x; DROP TABLE u; --")


def test_cassandra_rejects_malicious_collection(monkeypatch):
    cassandra = types.ModuleType("cassandra")
    cluster = types.ModuleType("cassandra.cluster")
    auth = types.ModuleType("cassandra.auth")

    class _Sess:
        def execute(self, *a, **k): return []
        def set_keyspace(self, *a, **k): pass

    class _Cluster:
        def __init__(self, *a, **k): pass
        def connect(self): return _Sess()

    cluster.Cluster = _Cluster
    auth.PlainTextAuthProvider = object
    monkeypatch.setitem(sys.modules, "cassandra", cassandra)
    monkeypatch.setitem(sys.modules, "cassandra.cluster", cluster)
    monkeypatch.setitem(sys.modules, "cassandra.auth", auth)

    from praisonai.persistence.knowledge.cassandra import CassandraKnowledgeStore

    store = CassandraKnowledgeStore()
    with pytest.raises(ValueError):
        store.create_collection("x; DROP TABLE users; --", 3)
    with pytest.raises(ValueError):
        store.delete_collection("x; DROP TABLE users; --")
    with pytest.raises(ValueError):
        store.count("x; DROP TABLE users; --")
