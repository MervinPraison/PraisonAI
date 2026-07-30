"""Unit tests for the durable-queue dead-letter decision (Issue #3519).

Covers the pure, core-side ``AttemptAndAgeDeadLetterPolicy`` and its
conformance with ``DeadLetterPolicyProtocol``, matching the shape of the
sibling gateway policy protocols (send / rate-limit / idle / drain).

The core invariant: a recoverable/transient failure is dead-lettered only
once it is BOTH attempt-exhausted AND genuinely old, so a brief channel
outage no longer permanently drops deliverable messages.
"""

import pytest

from praisonaiagents.gateway import (
    AttemptAndAgeDeadLetterPolicy,
    DeadLetterDecision,
    DeadLetterPolicyProtocol,
    PERMANENT_ERROR_CLASSES,
)


HOUR = 3600.0


def test_protocol_conformance():
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * HOUR)
    assert isinstance(policy, DeadLetterPolicyProtocol)


def test_transient_outage_not_dead_lettered_when_young():
    """Attempts exhausted quickly but the entry is minutes old -> retry."""
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * HOUR)
    now = 1_000_000.0
    decision = policy.should_dead_letter(
        attempts=5,
        first_seen_epoch=now - 45,  # ~45s of outage burned five attempts
        now_epoch=now,
        error_class="recoverable",
    )
    assert decision.dead_letter is False
    assert decision.reason == "retry"


def test_poison_message_dead_lettered_when_old_and_exhausted():
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * HOUR)
    now = 1_000_000.0
    decision = policy.should_dead_letter(
        attempts=5,
        first_seen_epoch=now - 7 * HOUR,
        now_epoch=now,
        error_class="recoverable",
    )
    assert decision.dead_letter is True
    assert decision.reason == "attempts_and_age"


def test_old_but_not_exhausted_is_not_dead_lettered():
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * HOUR)
    now = 1_000_000.0
    decision = policy.should_dead_letter(
        attempts=2,
        first_seen_epoch=now - 24 * HOUR,
        now_epoch=now,
        error_class="recoverable",
    )
    assert decision.dead_letter is False


@pytest.mark.parametrize("error_class", PERMANENT_ERROR_CLASSES)
def test_permanent_error_short_circuits_regardless_of_age(error_class):
    """Revoked credentials / permanent targets dead-letter immediately."""
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * HOUR)
    now = 1_000_000.0
    decision = policy.should_dead_letter(
        attempts=1,
        first_seen_epoch=now - 1,  # brand new, one attempt
        now_epoch=now,
        error_class=error_class,
    )
    assert decision.dead_letter is True
    assert decision.reason == "permanent_error"


def test_min_age_zero_restores_legacy_attempt_only_behaviour():
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=0)
    now = 1_000_000.0
    # Exhausted + brand new -> dead-letter, exactly like the old attempt-only gate.
    assert policy.should_dead_letter(
        attempts=5, first_seen_epoch=now, now_epoch=now, error_class="recoverable"
    ).dead_letter is True
    # Not yet exhausted -> retry.
    assert policy.should_dead_letter(
        attempts=4, first_seen_epoch=now, now_epoch=now, error_class="recoverable"
    ).dead_letter is False


def test_missing_first_seen_is_treated_as_just_now():
    """A malformed row with no first-seen stamp is never aged out early."""
    policy = AttemptAndAgeDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * HOUR)
    decision = policy.should_dead_letter(
        attempts=99,
        first_seen_epoch=0.0,
        now_epoch=1_000_000.0,
        error_class="recoverable",
    )
    assert decision.dead_letter is False


def test_decision_is_frozen_dataclass():
    decision = DeadLetterDecision(dead_letter=True, reason="x")
    with pytest.raises(Exception):
        decision.dead_letter = False  # type: ignore[misc]


def test_invalid_constructor_args_raise():
    with pytest.raises(ValueError):
        AttemptAndAgeDeadLetterPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        AttemptAndAgeDeadLetterPolicy(min_age_seconds=-1)
