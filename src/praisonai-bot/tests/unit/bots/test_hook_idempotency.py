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

    def test_stale_inflight_reclaimed_after_crash(self, tmp_path):
        # A crash between reserve and record/release leaves a durable
        # ``inflight`` row. Once it outlives the lease, the provider's retry
        # (after a restart) must be able to re-run rather than be deduplicated.
        from praisonai_bot.bots import SqliteIdempotencyStore

        p = tmp_path / "idem.sqlite"
        store = SqliteIdempotencyStore(p, inflight_lease_seconds=-1)
        assert store.reserve("evt") is True  # neither recorded nor released
        restarted = SqliteIdempotencyStore(p, inflight_lease_seconds=-1)
        assert restarted.reserve("evt") is True  # stale claim reclaimed

    def test_recorded_key_not_reclaimed_by_lease(self, tmp_path):
        # The lease only reclaims ``inflight`` rows; a successfully recorded key
        # keeps deduplicating until its TTL regardless of the lease.
        from praisonai_bot.bots import SqliteIdempotencyStore

        p = tmp_path / "idem.sqlite"
        store = SqliteIdempotencyStore(p, inflight_lease_seconds=-1)
        assert store.reserve("evt") is True
        store.record("evt")
        restarted = SqliteIdempotencyStore(p, inflight_lease_seconds=-1)
        assert restarted.reserve("evt") is False  # recorded still dedups


class TestGatewayConfigWiring:
    """The ``hooks.idempotency.store_backend`` config must actually reach the
    store the gateway builds — the prior code read a ``GatewayConfig`` field that
    no config path populated, leaving the durable backend unreachable (#4208).
    """

    def _bare_server(self):
        # Build the method's required attributes without the full (network-
        # binding) __init__ so the wiring is unit-tested in isolation.
        from praisonai_bot.gateway.server import WebSocketGateway

        srv = object.__new__(WebSocketGateway)
        srv._hooks = {}
        srv._hook_idem = None
        srv._hook_idempotency_backend = None
        srv._hook_idempotency_max = 10_000
        srv._hook_idempotency_ttl = 86_400.0
        return srv

    def test_sqlite_backend_selected_from_config(self, tmp_path, monkeypatch):
        from praisonai_bot.bots import SqliteIdempotencyStore

        srv = self._bare_server()
        srv._apply_hooks_from_config(
            {"hooks": {"idempotency": {"store_backend": "sqlite"}, "hooks": []}}
        )
        assert srv._hook_idempotency_backend == "sqlite"
        monkeypatch.setattr(
            "pathlib.Path.home", lambda: tmp_path, raising=True
        )
        assert isinstance(srv._get_hook_idem_store(), SqliteIdempotencyStore)

    def test_sibling_idempotency_key_selected(self, tmp_path, monkeypatch):
        from praisonai_bot.bots import SqliteIdempotencyStore

        srv = self._bare_server()
        srv._apply_hooks_from_config(
            {"hooks": [], "hooks_idempotency": {"store_backend": "sqlite"}}
        )
        assert srv._hook_idempotency_backend == "sqlite"
        monkeypatch.setattr(
            "pathlib.Path.home", lambda: tmp_path, raising=True
        )
        assert isinstance(srv._get_hook_idem_store(), SqliteIdempotencyStore)

    def test_default_is_durable(self, tmp_path, monkeypatch):
        # Issue #4339: an out-of-box gateway (no ``store_backend`` configured)
        # must be durable by default so a redelivered webhook after a restart is
        # suppressed rather than re-processed. ``memory`` is now an explicit
        # opt-in only.
        from praisonai_bot.bots import SqliteIdempotencyStore

        monkeypatch.setattr(
            "pathlib.Path.home", lambda: tmp_path, raising=True
        )
        srv = self._bare_server()
        srv._apply_hooks_from_config({"hooks": []})
        assert srv._hook_idempotency_backend is None
        assert isinstance(srv._get_hook_idem_store(), SqliteIdempotencyStore)

    def test_explicit_memory_opt_in(self, tmp_path, monkeypatch):
        # ``memory`` stays available as an explicit choice for ephemeral runs.
        from praisonaiagents.gateway import InMemoryIdempotencyStore

        monkeypatch.setattr(
            "pathlib.Path.home", lambda: tmp_path, raising=True
        )
        srv = self._bare_server()
        srv._apply_hooks_from_config(
            {"hooks": {"idempotency": {"store_backend": "memory"}, "hooks": []}}
        )
        assert srv._hook_idempotency_backend == "memory"
        assert isinstance(srv._get_hook_idem_store(), InMemoryIdempotencyStore)

    def test_backend_change_rebuilds_store(self, tmp_path, monkeypatch):
        from praisonaiagents.gateway import InMemoryIdempotencyStore
        from praisonai_bot.bots import SqliteIdempotencyStore

        monkeypatch.setattr(
            "pathlib.Path.home", lambda: tmp_path, raising=True
        )
        srv = self._bare_server()
        # Explicit ``memory`` opt-in, then hot-reload to durable sqlite.
        srv._apply_hooks_from_config(
            {"hooks": {"idempotency": {"store_backend": "memory"}, "hooks": []}}
        )
        assert isinstance(srv._get_hook_idem_store(), InMemoryIdempotencyStore)
        # Hot-reload flips to sqlite: the cached in-memory store is discarded.
        srv._apply_hooks_from_config(
            {"hooks": {"idempotency": {"store_backend": "sqlite"}, "hooks": []}}
        )
        assert isinstance(srv._get_hook_idem_store(), SqliteIdempotencyStore)


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

        assert isinstance(
            build_idempotency_store("totally-unknown"), InMemoryIdempotencyStore
        )

    def test_redis_backend_falls_back_to_durable_sqlite(self, tmp_path):
        # #4768: ``redis`` is not implemented, but it must not silently downgrade
        # to per-process memory. It falls back to the *durable* SQLite store
        # (still cross-restart dedup, and cross-replica with a shared file).
        from praisonai_bot.bots import (
            SqliteIdempotencyStore,
            build_idempotency_store,
        )

        store = build_idempotency_store("redis", path=tmp_path / "idem.sqlite")
        assert isinstance(store, SqliteIdempotencyStore)

    def test_none_backend_is_durable_by_default(self, tmp_path):
        # Issue #4339: unset backend -> durable SQLite store, not in-memory.
        from praisonai_bot.bots import SqliteIdempotencyStore, build_idempotency_store

        store = build_idempotency_store(None, path=tmp_path / "idem.sqlite")
        assert isinstance(store, SqliteIdempotencyStore)


class TestDurabilityDegradation:
    """Issue #4339: a durable store that cannot init is a *reported* fact."""

    def test_idempotency_fallback_records_degraded(self, tmp_path):
        from praisonai_bot.bots import build_idempotency_store
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
        )
        from praisonaiagents.gateway import InMemoryIdempotencyStore

        clear_durability_degraded("idempotency")
        # A path under a file (not a dir) makes the SQLite store fail to open,
        # exercising the recorded-degradation fallback.
        bad_parent = tmp_path / "afile"
        bad_parent.write_text("x")
        bad_path = bad_parent / "idem.sqlite"
        store = build_idempotency_store("sqlite", path=bad_path)
        assert isinstance(store, InMemoryIdempotencyStore)
        owners = durability_degraded_owners()
        match = [o for o in owners if o.owner_id == "durability:idempotency"]
        assert match
        # #4339: the operator-facing reason must be redacted — the raw store
        # path (and any backend detail) stays in logs, never in health/status.
        assert str(bad_path) not in match[0].reason
        clear_durability_degraded("idempotency")

    def test_redis_backend_records_degraded(self, tmp_path):
        # #4768: selecting ``store_backend="redis"`` when no Redis backend is
        # implemented must *report* the degradation (per-replica dedup), not
        # silently pass as protected — mirroring the SQLite-failure path so the
        # operator is not misled into thinking cross-replica dedup is active.
        from praisonai_bot.bots import (
            SqliteIdempotencyStore,
            build_idempotency_store,
        )
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
        )

        clear_durability_degraded("idempotency")
        store = build_idempotency_store("redis", path=tmp_path / "idem.sqlite")
        # Durable fallback keeps ingress working (not silent per-process memory).
        assert isinstance(store, SqliteIdempotencyStore)
        owners = durability_degraded_owners()
        match = [o for o in owners if o.owner_id == "durability:idempotency"]
        assert match
        assert "per-replica" in match[0].reason
        # The redacted reason must never echo the backend file path.
        assert str(tmp_path) not in match[0].reason
        clear_durability_degraded("idempotency")

    def test_redis_backend_sqlite_failure_reports_in_memory_not_per_replica(
        self, tmp_path
    ):
        # #4768: when ``redis`` is selected AND the durable SQLite fallback also
        # fails, dedup is process-local (lost on restart). The recorded fact must
        # stay the more severe ``in-memory`` reason, not be overwritten with the
        # milder ``per-replica`` reason (which would mask the durability loss).
        from praisonai_bot.bots import build_idempotency_store
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
        )
        from praisonaiagents.gateway import InMemoryIdempotencyStore

        clear_durability_degraded("idempotency")
        # A path under a file (not a dir) makes the SQLite store fail to open.
        bad_parent = tmp_path / "afile"
        bad_parent.write_text("x")
        bad_path = bad_parent / "idem.sqlite"
        store = build_idempotency_store("redis", path=bad_path)
        # Ingress keeps working, but only per-process (memory) now.
        assert isinstance(store, InMemoryIdempotencyStore)
        owners = durability_degraded_owners()
        match = [o for o in owners if o.owner_id == "durability:idempotency"]
        assert match
        # The recorded reason must reflect the true (worse) state: in-memory,
        # not the masked per-replica downgrade.
        assert "in-memory" in match[0].reason
        assert "per-replica" not in match[0].reason
        assert str(bad_path) not in match[0].reason
        clear_durability_degraded("idempotency")

    def test_successful_build_clears_stale_degradation(self, tmp_path):
        # #4339: a same-process rebuild (e.g. a config hot-reload) that restores
        # the durable store must clear a prior degradation so health/status stop
        # reporting non-durable operation after recovery.
        from praisonai_bot.bots import (
            SqliteIdempotencyStore,
            build_idempotency_store,
        )
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
            record_durability_degraded,
        )

        clear_durability_degraded("idempotency")
        record_durability_degraded("idempotency", reason="store unavailable")
        assert any(
            o.owner_id == "durability:idempotency"
            for o in durability_degraded_owners()
        )
        store = build_idempotency_store("sqlite", path=tmp_path / "idem.sqlite")
        assert isinstance(store, SqliteIdempotencyStore)
        assert not any(
            o.owner_id == "durability:idempotency"
            for o in durability_degraded_owners()
        )
        clear_durability_degraded("idempotency")

    def test_record_and_clear_roundtrip(self):
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
            record_durability_degraded,
        )

        clear_durability_degraded("session")
        record_durability_degraded("session", reason="store unavailable")
        owners = durability_degraded_owners()
        match = [o for o in owners if o.owner_id == "durability:session"]
        assert match and match[0].owner_kind == "gateway"
        assert match[0].retry_hint == "praisonai gateway doctor --fix"
        clear_durability_degraded("session")
        assert not any(
            o.owner_id == "durability:session"
            for o in durability_degraded_owners()
        )
