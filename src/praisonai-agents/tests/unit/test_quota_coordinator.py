"""
Unit tests for provider-quota coordination (cross-replica credential cooldowns).

Covers:
- LocalQuotaCoordinator TTL/bench semantics.
- QuotaCoordinatorConfig round-trip and build helper.
- FailoverManager sharing benches through a coordinator so a key benched by
  one "replica" (manager) is skipped by another sharing the same coordinator.
- Backward-compatible default (no coordinator supplied) behaves as before.
"""

import time

from praisonaiagents.llm.quota import (
    LocalQuotaCoordinator,
    QuotaCoordinatorConfig,
    QuotaCoordinatorProtocol,
    build_quota_coordinator,
)
from praisonaiagents.llm.failover import (
    AuthProfile,
    FailoverConfig,
    FailoverManager,
    ProviderStatus,
)


class TestLocalQuotaCoordinator:
    def test_satisfies_protocol(self):
        coord = LocalQuotaCoordinator()
        assert isinstance(coord, QuotaCoordinatorProtocol)

    def test_bench_and_is_benched(self):
        coord = LocalQuotaCoordinator()
        now = 1000.0
        coord.bench("key-a", until=now + 60, reason="429")
        assert coord.is_benched("key-a", now=now) is True
        assert coord.benched_until("key-a", now=now) == now + 60

    def test_bench_expires(self):
        coord = LocalQuotaCoordinator()
        now = 1000.0
        coord.bench("key-a", until=now + 10, reason="429")
        assert coord.is_benched("key-a", now=now + 5) is True
        # After TTL, self-clears.
        assert coord.is_benched("key-a", now=now + 20) is False
        assert coord.benched_until("key-a", now=now + 20) is None

    def test_bench_keeps_longest(self):
        coord = LocalQuotaCoordinator()
        now = 1000.0
        coord.bench("key-a", until=now + 30)
        coord.bench("key-a", until=now + 10)  # shorter, ignored
        assert coord.benched_until("key-a", now=now) == now + 30

    def test_clear(self):
        coord = LocalQuotaCoordinator()
        now = 1000.0
        coord.bench("key-a", until=now + 60)
        coord.clear("key-a")
        assert coord.is_benched("key-a", now=now) is False

    def test_unknown_key(self):
        coord = LocalQuotaCoordinator()
        assert coord.is_benched("missing") is False
        assert coord.benched_until("missing") is None


class TestQuotaCoordinatorConfig:
    def test_defaults_local(self):
        cfg = QuotaCoordinatorConfig()
        assert cfg.backend == "local"
        assert cfg.url is None

    def test_round_trip(self):
        cfg = QuotaCoordinatorConfig(backend="redis", url="redis://x")
        assert QuotaCoordinatorConfig.from_dict(cfg.to_dict()) == cfg

    def test_build_defaults_local(self):
        coord = build_quota_coordinator()
        assert isinstance(coord, LocalQuotaCoordinator)

    def test_build_unknown_backend_falls_open_to_local(self):
        coord = build_quota_coordinator(QuotaCoordinatorConfig(backend="redis"))
        assert isinstance(coord, LocalQuotaCoordinator)


class TestFailoverCoordinatorWiring:
    def test_default_no_coordinator_unchanged(self):
        # No coordinator supplied -> a local one is created; behaviour identical.
        mgr = FailoverManager()
        p = AuthProfile(name="p1", provider="openai", api_key="k")
        mgr.add_profile(p)
        assert mgr.get_next_profile() is p

    def test_bench_shared_across_managers(self):
        # Two managers = two "replicas" sharing one coordinator.
        coord = LocalQuotaCoordinator()
        cfg = FailoverConfig(cooldown_on_rate_limit=60.0)

        mgr_a = FailoverManager(config=cfg, coordinator=coord)
        mgr_b = FailoverManager(config=cfg, coordinator=coord)

        pa = AuthProfile(name="shared-key", provider="openai", api_key="k")
        pb = AuthProfile(name="shared-key", provider="openai", api_key="k")
        mgr_a.add_profile(pa)
        mgr_b.add_profile(pb)

        # Replica A benches the key on a 429.
        mgr_a.mark_failure(pa, "429", is_rate_limit=True)

        # Replica B, which never saw the failure, must now skip the same key.
        # Benches are keyed by the stable credential_id, not the profile label.
        cred_id = pa.credential_id
        assert cred_id == pb.credential_id
        assert coord.is_benched(cred_id) is True
        assert pb.is_available is True  # not yet synced
        # get_next_profile syncs the fleet-wide bench onto B's local profile.
        assert mgr_b.get_next_profile() is pb  # only profile, returned as best effort
        assert pb.status == ProviderStatus.RATE_LIMITED
        assert pb.is_available is False

    def test_same_name_distinct_keys_do_not_collide(self):
        # Two different credentials that share a display name ("default") must
        # NOT bench each other: identity is derived from the key, not the label.
        coord = LocalQuotaCoordinator()
        cfg = FailoverConfig(cooldown_on_rate_limit=60.0)
        mgr = FailoverManager(config=cfg, coordinator=coord)

        p1 = AuthProfile(name="default", provider="openai", api_key="key-1", priority=0)
        p2 = AuthProfile(name="default", provider="openai", api_key="key-2", priority=1)
        mgr.add_profile(p1)
        mgr.add_profile(p2)

        assert p1.credential_id != p2.credential_id

        mgr.mark_failure(p1, "429", is_rate_limit=True)
        # Benching credential 1 must leave credential 2 available.
        assert coord.is_benched(p1.credential_id) is True
        assert coord.is_benched(p2.credential_id) is False
        assert mgr.get_next_profile() is p2

    def test_stale_success_does_not_clear_newer_bench(self):
        # A stale in-flight success must not clear a newer bench recorded by a
        # concurrent failure with a later expiry.
        coord = LocalQuotaCoordinator()
        cfg = FailoverConfig(cooldown_on_rate_limit=60.0)
        mgr = FailoverManager(config=cfg, coordinator=coord)
        p = AuthProfile(name="k1", provider="openai", api_key="k")
        mgr.add_profile(p)

        # Simulate the profile recovering from an OLD short cooldown while a
        # NEWER, longer bench is present in the coordinator (set by a concurrent
        # failure on another request/replica).
        p.mark_rate_limited(1.0)  # recovered_from ~ now+1
        newer = time.time() + 300
        coord.bench(p.credential_id, until=newer)

        mgr.mark_success(p)
        # The newer bench must survive the stale success.
        assert coord.is_benched(p.credential_id) is True

    def test_success_clears_own_bench(self):
        # A genuine recovery (no newer bench) still clears the shared bench.
        coord = LocalQuotaCoordinator()
        mgr = FailoverManager(coordinator=coord)
        p = AuthProfile(name="k1", provider="openai", api_key="k")
        mgr.add_profile(p)

        mgr.mark_failure(p, "429", is_rate_limit=True)
        assert coord.is_benched(p.credential_id) is True
        mgr.mark_success(p)
        assert coord.is_benched(p.credential_id) is False

    def test_reset_all_clears_default_coordinator_bench(self):
        mgr = FailoverManager()
        primary = AuthProfile(name="primary", provider="openai", api_key="k1")
        backup = AuthProfile(
            name="backup", provider="openai", api_key="k2", priority=1
        )
        mgr.add_profile(primary)
        mgr.add_profile(backup)
        mgr.mark_failure(primary, "429", is_rate_limit=True)
        assert mgr.get_next_profile() is backup

        mgr.reset_all()

        assert mgr.get_next_profile() is primary
        assert primary.is_available

    def test_reset_all_clears_shared_bench_for_other_manager(self):
        coord = LocalQuotaCoordinator()
        mgr_a = FailoverManager(coordinator=coord)
        mgr_b = FailoverManager(coordinator=coord)
        primary_a = AuthProfile(name="primary-a", provider="openai", api_key="k")
        primary_b = AuthProfile(name="primary-b", provider="openai", api_key="k")
        backup_b = AuthProfile(
            name="backup-b", provider="openai", api_key="backup", priority=1
        )
        mgr_a.add_profile(primary_a)
        mgr_b.add_profile(primary_b)
        mgr_b.add_profile(backup_b)
        mgr_a.mark_failure(primary_a, "429", is_rate_limit=True)

        mgr_a.reset_all()

        assert not coord.is_benched(primary_a.credential_id)
        assert mgr_b.get_next_profile() is primary_b

    def test_reset_all_clear_failure_does_not_stop_local_resets(self):
        class BrokenClearCoordinator(LocalQuotaCoordinator):
            def clear(self, cred_id):
                raise RuntimeError("backend down")

        mgr = FailoverManager(coordinator=BrokenClearCoordinator())
        primary = AuthProfile(name="primary", provider="openai", api_key="k1")
        backup = AuthProfile(name="backup", provider="openai", api_key="k2")
        mgr.add_profile(primary)
        mgr.add_profile(backup)
        mgr.mark_failure(primary, "429", is_rate_limit=True)
        mgr.mark_failure(backup, "service unavailable")

        mgr.reset_all()

        assert primary.status == ProviderStatus.AVAILABLE
        assert backup.status == ProviderStatus.AVAILABLE
        assert primary.cooldown_until is None
        assert backup.cooldown_until is None

    def test_recovery_clears_shared_bench(self):
        coord = LocalQuotaCoordinator()
        mgr = FailoverManager(coordinator=coord)
        p = AuthProfile(name="k1", provider="openai", api_key="k")
        mgr.add_profile(p)

        mgr.mark_failure(p, "429", is_rate_limit=True)
        assert coord.is_benched(p.credential_id) is True

        mgr.mark_success(p)
        assert coord.is_benched(p.credential_id) is False

    def test_coordinator_failure_is_fail_open(self):
        class BrokenCoordinator:
            def bench(self, *a, **k):
                raise RuntimeError("backend down")

            def is_benched(self, *a, **k):
                raise RuntimeError("backend down")

            def benched_until(self, *a, **k):
                raise RuntimeError("backend down")

            def clear(self, *a, **k):
                raise RuntimeError("backend down")

        mgr = FailoverManager(coordinator=BrokenCoordinator())
        p = AuthProfile(name="k1", provider="openai", api_key="k")
        mgr.add_profile(p)

        # Must not raise despite the broken backend; local cooldown still applies.
        mgr.mark_failure(p, "429", is_rate_limit=True)
        assert p.status == ProviderStatus.RATE_LIMITED
        # get_next_profile also degrades gracefully.
        assert mgr.get_next_profile() is p
