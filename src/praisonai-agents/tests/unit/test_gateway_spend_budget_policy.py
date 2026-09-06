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


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        WindowedSpendBudgetPolicy(limit_usd="abc")
    with pytest.raises(ValueError):
        WindowedSpendBudgetPolicy(limit_usd=1.0, window_seconds=0)
