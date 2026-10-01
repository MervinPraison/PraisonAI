"""Thread-scoped SQLite cleanup must preserve the shared adapter (#5486).

`Memory.close_connections()` is documented as thread-scoped: it closes only the
calling thread's SQLite connections and leaves the shared `SqliteMemoryAdapter`
(and other threads' connections) intact. A previous adapter-shutdown block
cleared `self.memory_adapter` unconditionally, so subsequent searches fell back
to legacy SQL against `short_mem` / `long_mem` and raised
``sqlite3.OperationalError: no such table``.

These tests pin the contract: after another thread (or the same thread) calls
`close_connections()`, the shared adapter survives and searches keep working by
lazily reopening the calling thread's connection.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from praisonaiagents.memory.memory import Memory
from praisonaiagents.memory.adapters.sqlite_adapter import SqliteMemoryAdapter


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return Memory(config={"provider": "sqlite"})


def _texts(results):
    items = results if isinstance(results, list) else results.get("results", [])
    return [r.get("text") or r.get("memory") or "" for r in items]


def test_adapter_is_sqlite(store):
    """Control: these tests only mean something for the SQLite adapter."""
    assert isinstance(store.memory_adapter, SqliteMemoryAdapter)


def test_search_before_cleanup(store):
    """Control: searching works before any cleanup happens."""
    store.store_short_term("shared record")
    assert "shared record" in _texts(store.search_short_term("shared record"))


def test_short_term_search_survives_idle_worker_cleanup(store):
    """An idle worker that never opened a connection must not break searches."""
    store.store_short_term("shared record")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(store.close_connections).result()

    assert store.memory_adapter is not None
    assert "shared record" in _texts(store.search_short_term("shared record"))


def test_long_term_search_survives_idle_worker_cleanup(store):
    store.store_long_term("shared long record")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(store.close_connections).result()

    assert store.memory_adapter is not None
    assert "shared long record" in _texts(store.search_long_term("shared long record"))


def test_short_term_search_survives_initialized_worker_cleanup(store):
    """A worker that has opened its own connection cleans up only its own."""
    store.store_short_term("shared record")

    def worker():
        store.store_short_term("worker record")
        store.close_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(worker).result()

    assert store.memory_adapter is not None
    assert "shared record" in _texts(store.search_short_term("shared record"))
    assert "worker record" in _texts(store.search_short_term("worker record"))


def test_same_thread_repeated_cleanup_and_reopen(store):
    """Repeated same-thread cleanup must keep the adapter usable (lazy reopen)."""
    store.store_short_term("shared record")
    store.close_connections()
    store.close_connections()

    assert store.memory_adapter is not None
    assert "shared record" in _texts(store.search_short_term("shared record"))


def test_same_thread_long_term_cleanup_and_reopen(store):
    store.store_long_term("shared long record")
    store.close_connections()

    assert store.memory_adapter is not None
    assert "shared long record" in _texts(store.search_long_term("shared long record"))


def test_adapter_thread_close_is_idempotent(store):
    """Adapter-level thread close tolerates being called with no open conns."""
    store.memory_adapter.close_thread_connections()
    store.memory_adapter.close_thread_connections()
    store.store_short_term("shared record")
    assert "shared record" in _texts(store.search_short_term("shared record"))
