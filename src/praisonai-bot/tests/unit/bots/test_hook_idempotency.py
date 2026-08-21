"""Tests for durable inbound webhook/trigger idempotency store (#4208).

The gateway must not start a second agent run for an event a provider
re-delivers after a restart or on a second replica. These tests verify the
reserve/record/release contract and that the SQLite backend survives a restart.
"""
from __future__ import annotations

import pytest


class TestInMemoryIdempotencyStore:
    def test_reserve_record_dedup(self):
        from praisonaiagents.gateway import InMemoryIdempotencyStore

        s = InMemoryIdempotencyStore()
        assert s.reserve("k") is True
        assert s.reserve("k") is False  # in-flight
        s.record("k")
        assert s.reserve("k") is False  # recorded

    def test_release_allows_retry(self):
        from praisonaiagents.gateway import InMemoryIdempotencyStore

        s = InMemoryIdempotencyStore()
        assert s.reserve("k") is True
        s.release("k")
        assert s.reserve("k") is True  # failed delivery may retry

    def test_ttl_expiry(self):
        from praisonaiagents.gateway import InMemoryIdempotencyStore

        s = InMemoryIdempotencyStore(ttl_seconds=-1)  # everything immediately stale
        assert s.reserve("k") is True
        s.record("k")
        assert s.reserve("k") is True  # expired -> treated as new

    def test_satisfies_protocol(self):
        from praisonaiagents.gateway import (
            IdempotencyStoreProtocol,
            InMemoryIdempotencyStore,
        )

        assert isinstance(InMemoryIdempotencyStore(), IdempotencyStoreProtocol)


class TestSqliteIdempotencyStore:
    def test_dedup_survives_restart(self, tmp_path):
        from praisonai_bot.bots import SqliteIdempotencyStore

        p = tmp_path / "hook_idempotency.sqlite"
        store = SqliteIdempotencyStore(p)
        assert store.reserve("evt-1") is True
        store.record("evt-1")

        # Simulate a gateway restart: a fresh instance on the same file must
        # still treat the already-processed key as seen.
        restarted = SqliteIdempotencyStore(p)
        assert restarted.reserve("evt-1") is False

    def test_inflight_reserve_rejects_duplicate(self, tmp_path):
        from praisonai_bot.bots import SqliteIdempotencyStore

        store = SqliteIdempotencyStore(tmp_path / "idem.sqlite")
        assert store.reserve("evt") is True
        assert store.reserve("evt") is False  # concurrent duplicate

    def test_release_allows_retry_after_restart(self, tmp_path):
        from praisonai_bot.bots import SqliteIdempotencyStore

        p = tmp_path / "idem.sqlite"
        store = SqliteIdempotencyStore(p)
        assert store.reserve("evt") is True
        store.release("evt")  # failed run releases the reservation
        restarted = SqliteIdempotencyStore(p)
        assert restarted.reserve("evt") is True  # retry not blocked

    def test_satisfies_protocol(self, tmp_path):
        from praisonaiagents.gateway import IdempotencyStoreProtocol
        from praisonai_bot.bots import SqliteIdempotencyStore

        store = SqliteIdempotencyStore(tmp_path / "idem.sqlite")
        assert isinstance(store, IdempotencyStoreProtocol)


class TestBuildIdempotencyStore:
    def test_memory_backend_default(self):
        from praisonaiagents.gateway import InMemoryIdempotencyStore
        from praisonai_bot.bots import build_idempotency_store

        assert isinstance(build_idempotency_store("memory"), InMemoryIdempotencyStore)

    def test_sqlite_backend(self, tmp_path):
        from praisonai_bot.bots import SqliteIdempotencyStore, build_idempotency_store

        store = build_idempotency_store("sqlite", path=tmp_path / "idem.sqlite")
        assert isinstance(store, SqliteIdempotencyStore)

    def test_unknown_backend_falls_back_to_memory(self):
        from praisonaiagents.gateway import InMemoryIdempotencyStore
        from praisonai_bot.bots import build_idempotency_store

        assert isinstance(build_idempotency_store("redis"), InMemoryIdempotencyStore)
