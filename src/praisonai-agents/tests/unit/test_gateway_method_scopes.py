"""Tests for the declarative gateway method -> required-scope registry.

Covers Issue #3206: default-deny on unclassified methods, core method
classification, and optional per-payload-field escalation (fail-closed).
"""

import pytest

from praisonaiagents.gateway import (
    GatewayMethodDescriptor,
    OperatorScope,
    register_gateway_method,
    resolve_required_scope,
    authorize_method,
    GatewayUnauthorized,
    GATEWAY_METHODS,
)


def test_unknown_method_defaults_to_admin():
    """Default-deny: an unclassified method requires ADMIN (fail closed)."""
    assert resolve_required_scope("totally.new.method") == OperatorScope.ADMIN
    assert resolve_required_scope("totally.new.method", {"x": 1}) == OperatorScope.ADMIN


def test_core_methods_are_classified():
    assert resolve_required_scope("agent.message") == OperatorScope.WRITE
    assert resolve_required_scope("message") == OperatorScope.WRITE
    assert resolve_required_scope("session.status") == OperatorScope.READ
    assert resolve_required_scope("approvals.resolve") == OperatorScope.APPROVALS
    assert resolve_required_scope("pairing.approve") == OperatorScope.PAIRING
    assert resolve_required_scope("channels.control") == OperatorScope.ADMIN


def test_descriptor_resolve_never_deescalates():
    desc = GatewayMethodDescriptor(
        name="x",
        required_scope=OperatorScope.WRITE,
        escalate_fields={"harmless": OperatorScope.READ},
    )
    # READ is weaker than the WRITE baseline -> stays WRITE.
    assert desc.resolve({"harmless": 1}) == OperatorScope.WRITE


def test_field_escalation_raises_scope():
    desc = GatewayMethodDescriptor(
        name="x",
        required_scope=OperatorScope.WRITE,
        escalate_fields={"config": OperatorScope.ADMIN},
    )
    assert desc.resolve({"text": "hi"}) == OperatorScope.WRITE
    assert desc.resolve({"text": "hi", "config": {}}) == OperatorScope.ADMIN


def test_strict_fields_fail_closed_on_unknown_field():
    desc = GatewayMethodDescriptor(
        name="x",
        required_scope=OperatorScope.WRITE,
        strict_fields=True,
        safe_fields={"text"},
    )
    # Only safe fields -> baseline.
    assert desc.resolve({"text": "hi"}) == OperatorScope.WRITE
    # Unknown/structural field -> escalate to ADMIN (fail closed).
    assert desc.resolve({"text": "hi", "mutate": True}) == OperatorScope.ADMIN


def test_incomparable_scopes_escalate_to_admin():
    """APPROVALS and PAIRING are siblings, not one-implies-the-other.

    Combining them (baseline APPROVALS + a field requiring PAIRING) must not
    silently collapse to either capability — it escalates to ADMIN so a
    single-scope check cannot be satisfied by holding only one of them.
    """
    desc = GatewayMethodDescriptor(
        name="x",
        required_scope=OperatorScope.APPROVALS,
        escalate_fields={"pair": OperatorScope.PAIRING},
    )
    assert desc.resolve({"other": 1}) == OperatorScope.APPROVALS
    assert desc.resolve({"pair": True}) == OperatorScope.ADMIN

    # Order-independent: PAIRING baseline + APPROVALS field also escalates.
    desc2 = GatewayMethodDescriptor(
        name="y",
        required_scope=OperatorScope.PAIRING,
        escalate_fields={"approve": OperatorScope.APPROVALS},
    )
    assert desc2.resolve({"approve": True}) == OperatorScope.ADMIN


def test_descriptor_collections_are_immutable_after_construction():
    """Mutating the collections passed in must not change resolution."""
    escalate = {"cfg": OperatorScope.ADMIN}
    safe = {"text"}
    desc = GatewayMethodDescriptor(
        name="x",
        required_scope=OperatorScope.WRITE,
        escalate_fields=escalate,
        strict_fields=True,
        safe_fields=safe,
    )
    # Mutate the originals after construction.
    escalate["injected"] = OperatorScope.READ
    safe.add("mutate")
    # Descriptor kept its own copies -> unaffected.
    assert "injected" not in desc.escalate_fields
    assert "mutate" not in desc.safe_fields
    # Unknown structural field still fails closed.
    assert desc.resolve({"text": "hi", "mutate": True}) == OperatorScope.ADMIN


def test_authorize_method_allows_when_scope_held():
    """A classified method passes when the caller holds the required scope."""
    authorize_method("message", {OperatorScope.WRITE})
    authorize_method("session.status", {OperatorScope.READ})
    # ADMIN implies all -> satisfies any classified method.
    authorize_method("channels.control", {OperatorScope.ADMIN})
    authorize_method("message", {OperatorScope.ADMIN})


def test_authorize_method_denies_when_scope_missing():
    """A caller lacking the required scope is denied with the required scope."""
    with pytest.raises(GatewayUnauthorized) as exc:
        authorize_method("message", {OperatorScope.READ})
    assert exc.value.method == "message"
    assert exc.value.required == OperatorScope.WRITE


def test_authorize_method_default_denies_unknown_method():
    """An unclassified method is ADMIN-only by omission (fail closed)."""
    scopes = {OperatorScope.READ, OperatorScope.WRITE, OperatorScope.APPROVALS}
    with pytest.raises(GatewayUnauthorized) as exc:
        authorize_method("totally.new.unwired.method", scopes)
    assert exc.value.required == OperatorScope.ADMIN
    # Only ADMIN can reach it until it is classified.
    authorize_method("totally.new.unwired.method", {OperatorScope.ADMIN})


def test_authorize_method_gates_plugin_registered_method():
    """A plugin method registered via the registry is gated automatically."""
    name = "test.plugin.authz.5166"
    try:
        register_gateway_method(name, scope=OperatorScope.APPROVALS, owner="plugin")
        # WRITE alone does not satisfy an APPROVALS method.
        with pytest.raises(GatewayUnauthorized):
            authorize_method(name, {OperatorScope.WRITE})
        # The declared scope does.
        authorize_method(name, {OperatorScope.APPROVALS})
        # ADMIN implies it too.
        authorize_method(name, {OperatorScope.ADMIN})
    finally:
        GATEWAY_METHODS.pop(name, None)


def test_authorize_method_honours_field_escalation():
    """authorize_method resolves per-field escalation via the descriptor."""
    name = "test.plugin.escalate.5166"
    try:
        register_gateway_method(
            name,
            scope=OperatorScope.WRITE,
            escalate_fields={"config": OperatorScope.ADMIN},
            owner="plugin",
        )
        # Baseline field set -> WRITE suffices.
        authorize_method(name, {OperatorScope.WRITE}, {"text": "hi"})
        # Escalating field present -> now needs ADMIN.
        with pytest.raises(GatewayUnauthorized) as exc:
            authorize_method(name, {OperatorScope.WRITE}, {"config": {}})
        assert exc.value.required == OperatorScope.ADMIN
    finally:
        GATEWAY_METHODS.pop(name, None)


def test_authorize_method_read_lifecycle_allows_any_operator():
    """READ-classified lifecycle is reachable by any provisioned operator.

    READ is the baseline observe/lifecycle scope: an operator holding any
    actionable scope (WRITE/APPROVALS/PAIRING) can still complete
    hello/join/leave/status — matching pre-guard behaviour, where those frames
    carried no per-endpoint scope check. Regression guard for #5166 (a
    WRITE-only client must not be locked out of the session lifecycle).
    """
    for method in ("hello", "join", "leave", "session.status"):
        assert resolve_required_scope(method) == OperatorScope.READ
        authorize_method(method, {OperatorScope.WRITE})
        authorize_method(method, {OperatorScope.APPROVALS})
        authorize_method(method, {OperatorScope.PAIRING})
        authorize_method(method, {OperatorScope.READ})
    # An empty scope set still cannot reach even the READ baseline.
    with pytest.raises(GatewayUnauthorized):
        authorize_method("hello", set())


def test_authorize_method_read_does_not_leak_to_write():
    """The READ baseline does not grant WRITE/ADMIN surface."""
    with pytest.raises(GatewayUnauthorized) as exc:
        authorize_method("message", {OperatorScope.READ})
    assert exc.value.required == OperatorScope.WRITE
    with pytest.raises(GatewayUnauthorized):
        authorize_method("channels.control", {OperatorScope.READ})


def test_authorize_method_non_string_method_fails_closed():
    """A malformed (non-string/unhashable) method fails closed, not TypeError.

    A valid JSON frame such as ``{"type": []}`` must not raise ``TypeError``
    out of the guard (which would tear down the connection). It is treated as
    unclassified -> ADMIN, yielding a deterministic denial. Regression guard
    for #5166 P2.
    """
    for bad in ([], {}, 123, None):
        assert resolve_required_scope(bad) == OperatorScope.ADMIN  # type: ignore[arg-type]
        with pytest.raises(GatewayUnauthorized) as exc:
            authorize_method(bad, {OperatorScope.WRITE})  # type: ignore[arg-type]
        assert exc.value.required == OperatorScope.ADMIN


def test_register_gateway_method_and_resolve():
    name = "test.plugin.method.3206"
    try:
        register_gateway_method(name, scope=OperatorScope.APPROVALS, owner="plugin")
        assert resolve_required_scope(name) == OperatorScope.APPROVALS
        # Duplicate registration without replace raises.
        with pytest.raises(ValueError):
            register_gateway_method(name, scope=OperatorScope.READ)
        # replace=True overrides.
        register_gateway_method(name, scope=OperatorScope.READ, replace=True)
        assert resolve_required_scope(name) == OperatorScope.READ
    finally:
        GATEWAY_METHODS.pop(name, None)
