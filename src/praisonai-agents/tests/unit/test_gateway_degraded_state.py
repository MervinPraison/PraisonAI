"""Unit tests for the unified degraded-capability registry (Issue #3518).

Covers the core-side, process-local registry that any gateway owner records
into (channel / provider / capability / route / gateway) so ``health()`` /
``gateway status`` / ``gateway doctor`` can surface *every* degraded owner with
a consistent, redacted shape and an actionable next step — not just channels.
"""

import pytest

from praisonaiagents.gateway import (
    DEGRADED_STATES,
    OWNER_KINDS,
    DegradedCapabilityProtocol,
    DegradedCapabilityRegistry,
    DegradedOwner,
)


def test_owner_is_frozen_and_serialises():
    owner = DegradedOwner(
        owner_kind="provider",
        owner_id="openai",
        state="cold",
        reason="auth rejected (401)",
        retry_hint="re-set OPENAI_API_KEY",
    )
    with pytest.raises(Exception):
        owner.owner_id = "other"  # frozen dataclass
    assert owner.to_dict() == {
        "owner_kind": "provider",
        "owner_id": "openai",
        "state": "cold",
        "reason": "auth rejected (401)",
        "retry_hint": "re-set OPENAI_API_KEY",
    }


def test_registry_satisfies_protocol():
    assert isinstance(DegradedCapabilityRegistry(), DegradedCapabilityProtocol)


def test_mark_then_list():
    reg = DegradedCapabilityRegistry()
    reg.mark(DegradedOwner("provider", "openai", "cold", "auth rejected", "fix"))
    reg.mark(DegradedOwner("capability", "mcp:notion", "stale", "secret unresolved", "fix"))
    ids = {o.owner_id for o in reg.list_degraded()}
    assert ids == {"openai", "mcp:notion"}


def test_mark_is_idempotent_per_key():
    reg = DegradedCapabilityRegistry()
    reg.mark(DegradedOwner("provider", "openai", "cold", "reason A", "fix"))
    reg.mark(DegradedOwner("provider", "openai", "stale", "reason B", "fix2"))
    degraded = reg.list_degraded()
    assert len(degraded) == 1
    assert degraded[0].state == "stale"
    assert degraded[0].reason == "reason B"


def test_clear_on_recovery_is_idempotent():
    reg = DegradedCapabilityRegistry()
    reg.mark(DegradedOwner("channel", "telegram:main", "cold", "credential unavailable", "fix"))
    reg.clear("channel", "telegram:main")
    reg.clear("channel", "telegram:main")  # idempotent, no error
    assert reg.list_degraded() == []


def test_list_is_stable_sorted():
    reg = DegradedCapabilityRegistry()
    reg.mark(DegradedOwner("route", "r2", "cold", "x", ""))
    reg.mark(DegradedOwner("channel", "c1", "cold", "x", ""))
    reg.mark(DegradedOwner("provider", "p1", "cold", "x", ""))
    ordered = [(o.owner_kind, o.owner_id) for o in reg.list_degraded()]
    assert ordered == sorted(ordered)


def test_to_list_returns_dicts():
    reg = DegradedCapabilityRegistry()
    reg.mark(DegradedOwner("provider", "openai", "cold", "auth rejected", "fix"))
    rows = reg.to_list()
    assert rows == [
        {
            "owner_kind": "provider",
            "owner_id": "openai",
            "state": "cold",
            "reason": "auth rejected",
            "retry_hint": "fix",
        }
    ]


def test_closed_vocabularies_exposed():
    assert set(OWNER_KINDS) == {"channel", "provider", "capability", "route", "gateway"}
    assert set(DEGRADED_STATES) == {"cold", "stale"}


def test_owner_rejects_unknown_owner_kind():
    with pytest.raises(ValueError):
        DegradedOwner("not-a-kind", "x", "cold", "reason", "")


def test_owner_rejects_unknown_state():
    with pytest.raises(ValueError):
        DegradedOwner("provider", "openai", "not-a-state", "reason", "")


def test_owner_accepts_every_declared_vocabulary_value():
    for kind in OWNER_KINDS:
        for state in DEGRADED_STATES:
            owner = DegradedOwner(kind, "id", state, "reason", "")
            assert owner.owner_kind == kind
            assert owner.state == state
