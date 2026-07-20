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
