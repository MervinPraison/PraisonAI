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
        assert coord.is_benched("shared-key") is True
        assert pb.is_available is True  # not yet synced
        # get_next_profile syncs the fleet-wide bench onto B's local profile.
        assert mgr_b.get_next_profile() is pb  # only profile, returned as best effort
        assert pb.status == ProviderStatus.RATE_LIMITED
        assert pb.is_available is False

    def test_recovery_clears_shared_bench(self):
        coord = LocalQuotaCoordinator()
        mgr = FailoverManager(coordinator=coord)
        p = AuthProfile(name="k1", provider="openai", api_key="k")
        mgr.add_profile(p)

        mgr.mark_failure(p, "429", is_rate_limit=True)
        assert coord.is_benched("k1") is True

        mgr.mark_success(p)
        assert coord.is_benched("k1") is False

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
