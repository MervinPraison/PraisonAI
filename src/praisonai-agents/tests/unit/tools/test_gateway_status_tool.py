"""
Tests for the agent-facing gateway_status tool (Issue #3688).

Covers the lightweight, read-only built-in that resolves the active gateway
status source from the per-turn session context and reports live self-state.
"""

import json

from praisonaiagents.tools import gateway_status
from praisonaiagents.gateway import (
    GatewayStatusProtocol,
    GatewayStatus,
)
from praisonaiagents.session.context import (
    register_gateway_status,
    get_gateway_status,
    clear_gateway_status,
)


class FakeStatusSource:
    """Minimal GatewayStatusProtocol implementation for tests."""

    def __init__(self, status):
        self._status = status

    def snapshot(self):
        return self._status


def test_source_satisfies_protocol():
    src = FakeStatusSource(GatewayStatus())
    assert isinstance(src, GatewayStatusProtocol)


def test_no_gateway_fails_cleanly():
    # Nothing registered -> graceful message, not an exception.
    result = gateway_status()
    assert "No active gateway" in result


def test_status_reports_snapshot():
    status = GatewayStatus(
        run="busy",
        queued=2,
        active_sessions=7,
        sessions_by_channel={"telegram": 5, "slack": 2},
        delivery={"outbox_depth": 0, "dlq": 1, "dead_targets": ["slack:C123"]},
        degraded=[{"owner": "channel:telegram", "reason": "credential_unavailable"}],
    )
    token = register_gateway_status(FakeStatusSource(status))
    try:
        out = gateway_status()
    finally:
        clear_gateway_status(token)

    payload = json.loads(out)
    assert payload["run"] == "busy"
    assert payload["queued"] == 2
    assert payload["active_sessions"] == 7
    assert payload["sessions_by_channel"] == {"telegram": 5, "slack": 2}
    assert payload["delivery"]["dlq"] == 1
    assert payload["delivery"]["dead_targets"] == ["slack:C123"]
    assert payload["degraded"][0]["owner"] == "channel:telegram"


def test_default_status_is_serializable():
    token = register_gateway_status(FakeStatusSource(GatewayStatus()))
    try:
        payload = json.loads(gateway_status())
    finally:
        clear_gateway_status(token)
    assert payload["run"] == "idle"
    assert payload["active_sessions"] == 0
    assert payload["degraded"] == []


def test_register_and_clear_restores_previous():
    assert get_gateway_status() is None
    token = register_gateway_status(FakeStatusSource(GatewayStatus()))
    assert get_gateway_status() is not None
    clear_gateway_status(token)
    assert get_gateway_status() is None


def test_snapshot_error_is_reported_not_raised():
    class Broken:
        def snapshot(self):
            raise RuntimeError("boom")

    token = register_gateway_status(Broken())
    try:
        out = gateway_status()
    finally:
        clear_gateway_status(token)
    assert "Error reading gateway status" in out
