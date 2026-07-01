"""Unit tests for gateway rate-limit admission (Issue #2532).

Covers the pure, core-side decision predicate of SlidingWindowRateLimitPolicy
and conformance with the RateLimitPolicyProtocol, matching the shape of the
sibling gateway policy protocols (send / idle / drain / concurrency).
"""

import dataclasses

import pytest

from praisonaiagents.gateway import (
    RateLimitDecision,
    RateLimitPolicy,
    RateLimitPolicyProtocol,
    SlidingWindowRateLimitPolicy,
)


def test_protocol_conformance():
    policy = SlidingWindowRateLimitPolicy(max_requests=5, window_seconds=60)
    assert isinstance(policy, RateLimitPolicyProtocol)


def test_backward_compat_alias():
    assert RateLimitPolicy is RateLimitPolicyProtocol


def test_disabled_allows_everything():
    policy = SlidingWindowRateLimitPolicy()  # max_requests == 0
    assert policy.enabled is False
    for i in range(100):
        decision = policy.check(identity="u", scope="auth", now=float(i))
        assert decision.allowed is True
        assert decision.retry_after_seconds is None


def test_allows_below_ceiling():
    policy = SlidingWindowRateLimitPolicy(max_requests=3, window_seconds=60)
    assert policy.check(identity="u", scope="auth", now=0.0).allowed is True
    assert policy.check(identity="u", scope="auth", now=1.0).allowed is True
    assert policy.check(identity="u", scope="auth", now=2.0).allowed is True


def test_limits_over_ceiling_within_window():
    policy = SlidingWindowRateLimitPolicy(max_requests=2, window_seconds=60)
    assert policy.check(identity="u", scope="auth", now=0.0).allowed is True
    assert policy.check(identity="u", scope="auth", now=1.0).allowed is True
    decision = policy.check(identity="u", scope="auth", now=2.0)
    assert decision.allowed is False
    assert decision.retry_after_seconds is not None
    assert decision.retry_after_seconds > 0


def test_window_resets_after_expiry():
    policy = SlidingWindowRateLimitPolicy(max_requests=1, window_seconds=10)
    assert policy.check(identity="u", scope="auth", now=0.0).allowed is True
    assert policy.check(identity="u", scope="auth", now=1.0).allowed is False
    # Past the window: fresh allowance.
    assert policy.check(identity="u", scope="auth", now=11.0).allowed is True


def test_lockout_holds_until_expiry():
    policy = SlidingWindowRateLimitPolicy(
        max_requests=1, window_seconds=10, lockout_seconds=100
    )
    assert policy.check(identity="u", scope="auth", now=0.0).allowed is True
    limited = policy.check(identity="u", scope="auth", now=1.0)
    assert limited.allowed is False
    assert limited.retry_after_seconds == pytest.approx(100.0)
    # Still locked out even after the base window would have expired.
    still = policy.check(identity="u", scope="auth", now=50.0)
    assert still.allowed is False
    assert still.retry_after_seconds == pytest.approx(51.0)
    # After lockout elapses, allowed again.
    assert policy.check(identity="u", scope="auth", now=101.0).allowed is True


def test_keys_are_isolated_by_identity_and_scope():
    policy = SlidingWindowRateLimitPolicy(max_requests=1, window_seconds=60)
    assert policy.check(identity="a", scope="auth", now=0.0).allowed is True
    # Different identity, same scope: independent budget.
    assert policy.check(identity="b", scope="auth", now=0.0).allowed is True
    # Same identity, different scope: independent budget.
    assert policy.check(identity="a", scope="approve", now=0.0).allowed is True
    # Same identity + scope again: now limited.
    assert policy.check(identity="a", scope="auth", now=1.0).allowed is False


def test_stays_denied_after_ceiling_without_lockout():
    # Regression: with lockout_seconds == 0 (the default), a denial must NOT
    # reset the window, otherwise the next check starts fresh and is allowed
    # immediately, letting ~N/(N+1) of traffic through per window.
    policy = SlidingWindowRateLimitPolicy(max_requests=2, window_seconds=60)
    assert policy.check(identity="u", scope="auth", now=0.0).allowed is True
    assert policy.check(identity="u", scope="auth", now=1.0).allowed is True
    # Over the ceiling: denied.
    assert policy.check(identity="u", scope="auth", now=2.0).allowed is False
    # The very next request within the window must still be denied.
    assert policy.check(identity="u", scope="auth", now=3.0).allowed is False
    assert policy.check(identity="u", scope="auth", now=4.0).allowed is False
    # Only after the window elapses is a fresh request allowed.
    assert policy.check(identity="u", scope="auth", now=61.0).allowed is True


def test_decision_is_frozen():
    decision = RateLimitDecision(allowed=False, retry_after_seconds=1.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.allowed = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_requests": -1},
        {"max_requests": "x"},
        {"window_seconds": 0},
        {"window_seconds": -5},
        {"lockout_seconds": -1},
    ],
)
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValueError):
        SlidingWindowRateLimitPolicy(**kwargs)
