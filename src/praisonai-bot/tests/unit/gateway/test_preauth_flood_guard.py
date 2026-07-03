"""
Unit tests for Issue #2620 gateway edge protections:

* PreauthConnectionBudget — per-source-IP budget of concurrent unauthenticated
  WebSocket connections.
* UnauthorizedFloodGuard — per-connection guard that closes a socket after N
  unauthorized frames and log-samples the rest.
* AuthRateLimiter overflow fail-closed hardening — reject new keys closed when
  the key map is saturated while preserving existing lockouts.
"""

import time

import pytest

try:
    from praisonai.praisonai.gateway.rate_limiter import (
        AuthRateLimiter,
        PreauthConnectionBudget,
        UnauthorizedFloodGuard,
    )
except ImportError:  # pragma: no cover - import path fallback
    from praisonai_bot.gateway.rate_limiter import (  # type: ignore
        AuthRateLimiter,
        PreauthConnectionBudget,
        UnauthorizedFloodGuard,
    )


class TestPreauthConnectionBudget:
    def test_acquire_up_to_limit_then_reject(self):
        budget = PreauthConnectionBudget(max_per_ip=3)
        assert budget.acquire("1.2.3.4") is True
        assert budget.acquire("1.2.3.4") is True
        assert budget.acquire("1.2.3.4") is True
        assert budget.acquire("1.2.3.4") is False
        assert budget.active("1.2.3.4") == 3

    def test_release_frees_slot(self):
        budget = PreauthConnectionBudget(max_per_ip=1)
        assert budget.acquire("1.2.3.4") is True
        assert budget.acquire("1.2.3.4") is False
        budget.release("1.2.3.4")
        assert budget.active("1.2.3.4") == 0
        assert budget.acquire("1.2.3.4") is True

    def test_per_ip_isolation(self):
        budget = PreauthConnectionBudget(max_per_ip=1)
        assert budget.acquire("1.1.1.1") is True
        assert budget.acquire("2.2.2.2") is True
        assert budget.acquire("1.1.1.1") is False

    def test_unresolved_ips_share_one_bucket(self):
        budget = PreauthConnectionBudget(max_per_ip=2)
        assert budget.acquire("unknown") is True
        assert budget.acquire("") is True
        assert budget.acquire("unknown") is False

    def test_zero_disables_budget(self):
        budget = PreauthConnectionBudget(max_per_ip=0)
        for _ in range(100):
            assert budget.acquire("1.2.3.4") is True
        assert budget.active("1.2.3.4") == 0

    def test_release_never_goes_negative(self):
        budget = PreauthConnectionBudget(max_per_ip=2)
        budget.release("1.2.3.4")
        budget.release("1.2.3.4")
        assert budget.active("1.2.3.4") == 0


class TestUnauthorizedFloodGuard:
    def test_closes_after_limit(self):
        guard = UnauthorizedFloodGuard(max_unauthorized=3)
        assert guard.note_unauthorized() is False
        assert guard.note_unauthorized() is False
        assert guard.note_unauthorized() is True
        assert guard.count == 3

    def test_zero_disables_guard(self):
        guard = UnauthorizedFloodGuard(max_unauthorized=0)
        for _ in range(50):
            assert guard.note_unauthorized() is False

    def test_log_sampling_first_then_every_nth(self):
        guard = UnauthorizedFloodGuard(max_unauthorized=100, log_every=5)
        logged = []
        for _ in range(11):
            guard.note_unauthorized()
            if guard.should_log():
                logged.append(guard.count)
        # First frame, then every 5th: 1, 5, 10
        assert logged == [1, 5, 10]

    def test_suppressed_count(self):
        guard = UnauthorizedFloodGuard(max_unauthorized=100, log_every=5)
        for _ in range(5):
            guard.note_unauthorized()
            guard.should_log()
        # Frames 1 and 5 logged -> 3 suppressed (2, 3, 4)
        assert guard.suppressed == 3


class TestRateLimiterOverflowFailClosed:
    def test_new_keys_rejected_when_saturated(self):
        limiter = AuthRateLimiter(
            max_attempts=100, window_seconds=1000, max_keys=2
        )
        # Fill up two distinct keys (buckets).
        assert limiter.allow("ep", "a") is True
        assert limiter.allow("ep", "b") is True
        # Map is now saturated; a fresh key must be rejected closed.
        assert limiter.allow("ep", "c") is False
        # Existing keys still allowed.
        assert limiter.allow("ep", "a") is True

    def test_existing_lockout_preserved_under_flood(self):
        limiter = AuthRateLimiter(
            max_attempts=1,
            window_seconds=1000,
            lockout_seconds=1000,
            max_keys=2,
        )
        # Lock out "victim".
        assert limiter.allow("ep", "victim") is True
        assert limiter.allow("ep", "victim") is False  # triggers lockout
        # Flood with fresh IPs; they must not evict the lockout.
        for i in range(20):
            limiter.allow("ep", f"attacker-{i}")
        # Victim is still locked out.
        assert limiter.allow("ep", "victim") is False

    def test_expired_lockout_recovers_under_saturation(self):
        # A client with an *expired* lockout must be able to reconnect and clear
        # its stale lockout entry even while the key map is saturated, rather
        # than being trapped by the overflow fail-closed check.
        limiter = AuthRateLimiter(
            max_attempts=1,
            window_seconds=1000,
            lockout_seconds=1000,
            max_keys=2,
        )
        # Lock out "returning".
        assert limiter.allow("ep", "returning") is True
        assert limiter.allow("ep", "returning") is False  # triggers lockout
        # Saturate the map with another key so overflow protection is active.
        assert limiter.allow("ep", "other") is True
        # Force the "returning" lockout to have already expired (deterministic;
        # avoids sleeping / wall-clock flakiness).
        limiter._lockouts[("ep", "returning")] = time.time() - 1.0
        # The returning client's lockout has expired: it must be admitted and its
        # stale lockout entry cleared, not blocked by the overflow guard.
        assert limiter.allow("ep", "returning") is True
        assert ("ep", "returning") not in limiter._lockouts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
