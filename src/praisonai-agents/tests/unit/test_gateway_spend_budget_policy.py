"""Unit tests for gateway spend-budget admission (Issue #4894).

Covers the pure, core-side decision predicate of WindowedSpendBudgetPolicy and
conformance with the SpendBudgetPolicyProtocol, mirroring the sibling
RateLimitPolicyProtocol shape.
"""

import pytest

from praisonaiagents.gateway import (
    RateLimitDecision,
    SpendBudgetPolicy,
    SpendBudgetPolicyProtocol,
    WindowedSpendBudgetPolicy,
)


def test_protocol_conformance():
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0)
    assert isinstance(policy, SpendBudgetPolicyProtocol)


def test_backward_compat_alias():
    assert SpendBudgetPolicy is SpendBudgetPolicyProtocol


def test_disabled_allows_everything():
    policy = WindowedSpendBudgetPolicy()  # limit_usd == 0
    assert policy.enabled is False
    for spent in (0.0, 100.0, 1e6):
        decision = policy.check(
            identity="u", scope="tg", spent_usd=spent, now=0.0
        )
        assert decision.allowed is True
        assert decision.retry_after_seconds is None


def test_allows_below_limit():
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0)
    assert policy.enabled is True
    d = policy.check(identity="u", scope="tg", spent_usd=1.99, now=0.0)
    assert d.allowed is True
    assert d.retry_after_seconds is None


def test_rejects_at_or_above_limit():
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0, window_seconds=3600)
    d = policy.check(identity="u", scope="tg", spent_usd=2.0, now=0.0)
    assert d.allowed is False
    assert d.retry_after_seconds == 3600

    d2 = policy.check(identity="u", scope="tg", spent_usd=5.0, now=0.0)
    assert d2.allowed is False


def test_returns_frozen_decision():
    policy = WindowedSpendBudgetPolicy(limit_usd=1.0)
    d = policy.check(identity="u", scope="tg", spent_usd=2.0, now=0.0)
    assert isinstance(d, RateLimitDecision)


def test_window_start_helper():
    policy = WindowedSpendBudgetPolicy(limit_usd=1.0, window_seconds=100.0)
    assert policy.window_start(1000.0) == 900.0


def test_non_numeric_spent_treated_as_zero():
    policy = WindowedSpendBudgetPolicy(limit_usd=1.0)
    d = policy.check(identity="u", scope="tg", spent_usd=None, now=0.0)
    assert d.allowed is True


def test_pending_cost_reserves_budget():
    # Prior spend is under the cap, but the pending turn's estimated cost would
    # overshoot it: admission must reject to enforce a hard cap.
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0)
    d = policy.check(
        identity="u", scope="tg", spent_usd=1.99, now=0.0, pending_usd=0.5
    )
    assert d.allowed is False


def test_pending_cost_allows_when_headroom():
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0)
    d = policy.check(
        identity="u", scope="tg", spent_usd=1.0, now=0.0, pending_usd=0.5
    )
    assert d.allowed is True


def test_negative_or_non_numeric_pending_ignored():
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0)
    assert policy.check(
        identity="u", scope="tg", spent_usd=1.0, now=0.0, pending_usd=-5.0
    ).allowed is True
    assert policy.check(
        identity="u", scope="tg", spent_usd=1.0, now=0.0, pending_usd="x"
    ).allowed is True


def test_retry_after_uses_oldest_spend_ts():
    # window=3600, oldest charge at t=1000, now=1200 -> retry when the oldest
    # charge ages out: 1000 + 3600 - 1200 = 3400.
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0, window_seconds=3600)
    d = policy.check(
        identity="u",
        scope="tg",
        spent_usd=2.0,
        now=1200.0,
        oldest_spend_ts=1000.0,
    )
    assert d.allowed is False
    assert d.retry_after_seconds == pytest.approx(3400.0)


def test_retry_after_clamped_and_expired():
    policy = WindowedSpendBudgetPolicy(limit_usd=2.0, window_seconds=3600)
    # oldest charge already older than the window -> retry immediately.
    d = policy.check(
        identity="u",
        scope="tg",
        spent_usd=2.0,
        now=10_000.0,
        oldest_spend_ts=1000.0,
    )
    assert d.retry_after_seconds == pytest.approx(0.0)
    # No oldest ts supplied -> safe upper bound (full window).
    d2 = policy.check(identity="u", scope="tg", spent_usd=2.0, now=0.0)
    assert d2.retry_after_seconds == pytest.approx(3600.0)


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        WindowedSpendBudgetPolicy(limit_usd="abc")
    with pytest.raises(ValueError):
        WindowedSpendBudgetPolicy(limit_usd=1.0, window_seconds=0)
