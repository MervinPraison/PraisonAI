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
        # #4768/#5154: when ``redis`` is selected but no Redis is reachable (no
        # client, as here), it must not silently downgrade to per-process memory.
        # It falls back to the *durable* SQLite store (still cross-restart dedup,
        # and cross-replica with a shared file).
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


class _FakeRedis:
    """Minimal in-memory stand-in for the sync ``redis.Redis`` client (#5154).

    Supports the subset ``RedisIdempotencyStore`` uses: ``set(nx=,px=)``,
    ``get``, ``delete``, ``eval`` (for the compare-and-del *release* Lua and the
    owner-checked *record* Lua), and ``ping``. TTLs are ignored (tests exercise
    claim semantics, not expiry). The two Lua scripts are distinguished by their
    arg count: release passes 1 arg (token), record passes 3 (token, recorded,
    ttl_ms).
    """

    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def set(self, key, value, nx=False, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)
        return 1

    def eval(self, script, numkeys, key, *args):
        if len(args) >= 3:
            # Owner-checked record: set ``recorded`` only if key is our token,
            # already ``recorded``, or gone; never overwrite another owner.
            token, recorded, _ttl = args[0], args[1], args[2]
            current = self.store.get(key)
            if current is None or current == token or current == recorded:
                self.store[key] = recorded
                return 1
            return 0
        # Compare-and-del release.
        token = args[0]
        if self.store.get(key) == token:
            self.store.pop(key, None)
            return 1
        return 0


class _FailingRedis(_FakeRedis):
    """A client that was reachable at build (``ping`` ok) but drops at runtime:
    every data op raises, exercising the runtime fail-open path (#5154)."""

    def set(self, *a, **k):
        raise ConnectionError("redis down")

    def get(self, *a, **k):
        raise ConnectionError("redis down")

    def delete(self, *a, **k):
        raise ConnectionError("redis down")

    def eval(self, *a, **k):
        raise ConnectionError("redis down")

    def pipeline(self, *a, **k):
        raise ConnectionError("redis down")


class _RecoverableRedis(_FakeRedis):
    """A client whose data ops fail while ``down`` is set, then succeed again.

    Models a transient runtime Redis outage that later recovers, exercising the
    degraded-then-recovered path (Greptile P2): the store must clear its
    degraded fact once a subsequent op succeeds.
    """

    def __init__(self):
        super().__init__()
        self.down = True

    def _guard(self):
        if self.down:
            raise ConnectionError("redis down")

    def set(self, key, value, nx=False, px=None):
        self._guard()
        return super().set(key, value, nx=nx, px=px)

    def get(self, key):
        self._guard()
        return super().get(key)

    def delete(self, key):
        self._guard()
        return super().delete(key)

    def eval(self, script, numkeys, key, *args):
        self._guard()
        return super().eval(script, numkeys, key, *args)


def _watch_error():
    """Raise the exact ``WatchError`` type the store catches.

    The store resolves ``redis.WatchError`` when redis is installed, else a
    private sentinel. Reusing its resolver here guarantees the fake pipeline's
    abort is caught by the store's retry loop regardless of whether the redis
    package is present in the test environment."""
    from praisonai_bot.bots._idempotency import _watch_error_type

    return _watch_error_type()()


class _NoEvalPipe:
    """A watched-transaction pipeline over a shared dict, atomic on ``execute``.

    Emulates ``redis-py``'s ``WATCH``/``MULTI``/``EXEC``: if the watched key's
    value changed between ``watch`` and ``execute`` the transaction aborts with
    ``WatchError`` (here modelled by the injected ``on_before_exec`` hook that a
    test uses to simulate a concurrent reclaim).
    """

    def __init__(self, backend):
        self._backend = backend
        self._queued = []
        self._watched_val = None
        self._watch_key = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def watch(self, key):
        self._watch_key = key
        self._watched_val = self._backend.store.get(key)

    def unwatch(self):
        self._watch_key = None

    def get(self, key):
        return self._backend.store.get(key)

    def multi(self):
        self._queued = []

    def set(self, key, value, px=None):
        self._queued.append(("set", key, value))

    def delete(self, key):
        self._queued.append(("delete", key))

    def execute(self):
        hook = self._backend._on_before_exec
        if hook is not None:
            hook()
        # Optimistic check: abort if the watched value changed under us.
        if self._backend.store.get(self._watch_key) != self._watched_val:
            raise _watch_error()
        for op in self._queued:
            if op[0] == "set":
                self._backend.store[op[1]] = op[2]
            elif op[0] == "delete":
                self._backend.store.pop(op[1], None)
        self._queued = []
        return []


class _NoEvalRedis(_FakeRedis):
    """A client without ``eval`` but with a watched-transaction ``pipeline``.

    Exercises the non-Lua fallback path in ``record``/``release``: the fallback
    must remain atomic (owner-checked compare-and-set / -del) via WATCH/MULTI.
    """

    def __init__(self):
        super().__init__()
        self._on_before_exec = None

    def eval(self, *a, **k):
        raise RuntimeError("EVAL not supported")

    def pipeline(self):
        return _NoEvalPipe(self)


class TestRedisIdempotencyStore:
    """Issue #5154: cluster-wide exactly-once inbound admission."""

    def test_reserve_record_dedup(self):
        from praisonai_bot.bots import RedisIdempotencyStore

        s = RedisIdempotencyStore(_FakeRedis())
        assert s.reserve("k") is True
        assert s.reserve("k") is False  # in-flight (SET NX fails)
        s.record("k")
        assert s.reserve("k") is False  # recorded

    def test_release_allows_retry(self):
        from praisonai_bot.bots import RedisIdempotencyStore

        s = RedisIdempotencyStore(_FakeRedis())
        assert s.reserve("k") is True
        s.release("k")
        assert s.reserve("k") is True  # failed delivery may retry

    def test_cross_replica_dedup_shares_one_backend(self):
        # Two replicas (two store instances) sharing one Redis: the second
        # replica's reserve for the same key is rejected -> admitted exactly once.
        from praisonai_bot.bots import RedisIdempotencyStore

        backend = _FakeRedis()
        replica_a = RedisIdempotencyStore(backend)
        replica_b = RedisIdempotencyStore(backend)
        assert replica_a.reserve("dup") is True
        assert replica_b.reserve("dup") is False

    def test_release_only_drops_own_claim(self):
        # A replica must not release another replica's live claim: replica B's
        # release is a no-op because the stored owner token is replica A's.
        from praisonai_bot.bots import RedisIdempotencyStore

        backend = _FakeRedis()
        replica_a = RedisIdempotencyStore(backend)
        replica_b = RedisIdempotencyStore(backend)
        assert replica_a.reserve("k") is True
        replica_b.release("k")  # not the owner -> no-op
        assert replica_b.reserve("k") is False  # still held by A

    def test_satisfies_protocol(self):
        from praisonaiagents.gateway import IdempotencyStoreProtocol
        from praisonai_bot.bots import RedisIdempotencyStore

        assert isinstance(
            RedisIdempotencyStore(_FakeRedis()), IdempotencyStoreProtocol
        )

    def test_build_uses_redis_store_when_client_available(self, monkeypatch):
        # ``store_backend='redis'`` builds the real cluster-wide store when a
        # Redis client can be constructed (no fallback / degradation).
        import praisonai_bot.bots._idempotency as idem
        from praisonai_bot.bots import RedisIdempotencyStore, build_idempotency_store
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
        )

        clear_durability_degraded("idempotency")
        monkeypatch.setattr(
            idem, "_build_redis_client", lambda cfg, url: _FakeRedis()
        )
        store = build_idempotency_store("redis")
        assert isinstance(store, RedisIdempotencyStore)
        assert not any(
            o.owner_id == "durability:idempotency"
            for o in durability_degraded_owners()
        )
        clear_durability_degraded("idempotency")

    def test_record_does_not_overwrite_reclaimed_claim(self):
        # Stale-owner race (Greptile P1): replica A's inflight lease expired and
        # replica B reclaimed the key. A's late ``record`` must NOT clobber B's
        # live claim — otherwise both replicas were admitted for one delivery.
        from praisonai_bot.bots import RedisIdempotencyStore

        backend = _FakeRedis()
        replica_a = RedisIdempotencyStore(backend)
        replica_b = RedisIdempotencyStore(backend)

        assert replica_a.reserve("k") is True
        # Simulate A's lease expiring and B reclaiming the key.
        backend.store.pop(replica_a._redis_key("k"))
        assert replica_b.reserve("k") is True  # B now owns the claim
        b_key = replica_b._redis_key("k")
        b_owns = backend.store[b_key]

        # A's late record must be a no-op — B's token still owns the key.
        replica_a.record("k")
        assert backend.store[b_key] == b_owns  # unchanged, B still owns it

        # A well-behaved record by the current owner still commits.
        replica_b.record("k")
        assert backend.store[b_key] == RedisIdempotencyStore._RECORDED

    def test_reserve_fails_open_on_runtime_redis_outage(self):
        # A runtime Redis drop must not 500 the hook path: reserve fails open
        # (admits) and records a degraded fact rather than raising.
        from praisonai_bot.bots import RedisIdempotencyStore
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
        )

        clear_durability_degraded("idempotency")
        s = RedisIdempotencyStore(_FailingRedis())
        assert s.reserve("k") is True  # fail-open admit, no exception
        assert any(
            o.owner_id == "durability:idempotency"
            for o in durability_degraded_owners()
        )
        clear_durability_degraded("idempotency")

    def test_record_and_release_swallow_runtime_redis_outage(self):
        # record/release must not propagate a runtime Redis error into the hook
        # path; the orphaned claim self-heals via the inflight lease.
        from praisonai_bot.bots import RedisIdempotencyStore
        from praisonai_bot.bots._session import clear_durability_degraded

        clear_durability_degraded("idempotency")
        s = RedisIdempotencyStore(_FailingRedis())
        s.record("k")  # must not raise
        s.release("k")  # must not raise
        clear_durability_degraded("idempotency")

    def test_runtime_degradation_clears_after_recovery(self):
        # Greptile P2: a runtime outage marks degraded, but once Redis recovers a
        # subsequent successful op must clear the degraded fact so gateway
        # status/doctor stop reporting best-effort dedup (and a later outage
        # re-warns).
        from praisonai_bot.bots import RedisIdempotencyStore
        from praisonai_bot.bots._session import (
            clear_durability_degraded,
            durability_degraded_owners,
        )

        clear_durability_degraded("idempotency")
        backend = _RecoverableRedis()
        s = RedisIdempotencyStore(backend)

        # Outage: reserve fails open and records the degraded fact.
        assert s.reserve("k") is True
        assert any(
            o.owner_id == "durability:idempotency"
            for o in durability_degraded_owners()
        )

        # Redis recovers; the next successful reserve clears the degradation.
        backend.down = False
        assert s.reserve("k2") is True
        assert not any(
            o.owner_id == "durability:idempotency"
            for o in durability_degraded_owners()
        )
        clear_durability_degraded("idempotency")

    def test_noeval_record_fallback_is_atomic_owner_checked(self):
        # Greptile P1 (fallback): a client without EVAL uses the WATCH/MULTI
        # fallback. If another replica reclaims the key mid-commit (simulated via
        # the pre-exec hook), the transaction aborts and re-decides instead of
        # clobbering the new owner.
        from praisonai_bot.bots import RedisIdempotencyStore

        backend = _NoEvalRedis()
        replica_a = RedisIdempotencyStore(backend)
        replica_b = RedisIdempotencyStore(backend)

        assert replica_a.reserve("k") is True
        a_key = replica_a._redis_key("k")

        # On A's first commit attempt, B reclaims the key (its own token),
        # forcing the watched transaction to abort; A must then no-op.
        def _reclaim_once():
            backend.store[a_key] = replica_b._token
            backend._on_before_exec = None  # only interfere once

        backend._on_before_exec = _reclaim_once
        replica_a.record("k")

        # B's live claim is intact — A did not overwrite it with ``recorded``.
        assert backend.store[a_key] == replica_b._token

    def test_noeval_record_fallback_commits_when_owner(self):
        # The non-Lua fallback still commits normally when we remain the owner.
        from praisonai_bot.bots import RedisIdempotencyStore

        backend = _NoEvalRedis()
        s = RedisIdempotencyStore(backend)
        assert s.reserve("k") is True
        s.record("k")
        assert backend.store[s._redis_key("k")] == RedisIdempotencyStore._RECORDED

    def test_noeval_release_fallback_only_drops_own_claim(self):
        # The non-Lua release fallback must be owner-checked too: replica B's
        # release is a no-op while A owns the key.
        from praisonai_bot.bots import RedisIdempotencyStore

        backend = _NoEvalRedis()
        replica_a = RedisIdempotencyStore(backend)
        replica_b = RedisIdempotencyStore(backend)
        assert replica_a.reserve("k") is True
        replica_b.release("k")  # not owner -> no-op
        assert replica_b.reserve("k") is False  # still held by A
        replica_a.release("k")  # owner -> drops
        assert replica_b.reserve("k") is True
