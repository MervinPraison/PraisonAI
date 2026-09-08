"""
Tests for live-authority binding of tool approvals (issue #4949).

An approval that resolves *after* the originating turn was stopped or
superseded must be dropped fail-closed: the tool does not run and no durable
``session``/``always`` grant is persisted for an abandoned turn.

The gate is driven by the (previously inert) ``ApprovalRequest.liveness``
predicate. ``None`` liveness preserves today's behaviour (always live).
"""

from __future__ import annotations

import pytest

from praisonaiagents.agent.tool_execution import ToolExecutionMixin
from praisonaiagents.approval.protocols import ApprovalDecision, ApprovalRequest
from praisonaiagents.approval.registry import ApprovalRegistry


class _ApproveBackend:
    """A backend that always returns an ``always``-scoped approval."""

    def request_approval_sync(self, request):
        return ApprovalDecision(approved=True, scope="always", reason="ok")

    async def request_approval(self, request):
        return ApprovalDecision(approved=True, scope="always", reason="ok")


# ── _reject_if_stale ────────────────────────────────────────────────────────


class TestRejectIfStale:
    def test_none_liveness_is_never_stale(self):
        req = ApprovalRequest(
            tool_name="execute_command", arguments={}, risk_level="high"
        )
        assert ApprovalRegistry._reject_if_stale(req) is None

    def test_live_predicate_true_is_not_stale(self):
        req = ApprovalRequest(
            tool_name="execute_command", arguments={}, risk_level="high",
            liveness=lambda: True,
        )
        assert ApprovalRegistry._reject_if_stale(req) is None

    def test_dead_predicate_returns_fail_closed_denial(self):
        req = ApprovalRequest(
            tool_name="execute_command", arguments={}, risk_level="high",
            liveness=lambda: False,
        )
        decision = ApprovalRegistry._reject_if_stale(req)
        assert decision is not None
        assert decision.approved is False
        assert "live" in decision.reason.lower()

    def test_raising_predicate_is_treated_as_live(self):
        def boom():
            raise RuntimeError("boom")

        req = ApprovalRequest(
            tool_name="execute_command", arguments={}, risk_level="high",
            liveness=boom,
        )
        assert ApprovalRegistry._reject_if_stale(req) is None


# ── approve_sync ────────────────────────────────────────────────────────────


class TestApproveSyncLiveness:
    def test_stale_resolution_is_denied_and_not_persisted(self):
        registry = ApprovalRegistry()
        registry.set_backend(_ApproveBackend())

        decision = registry.approve_sync(
            agent_name="a",
            tool_name="execute_command",
            arguments={"command": "rm -rf /"},
            liveness=lambda: False,
        )

        assert decision.approved is False
        # No durable/session grant leaked for the abandoned turn.
        assert not registry._session_scoped_targets
        assert not registry.is_already_approved(
            "execute_command", {"command": "rm -rf /"}, "a"
        )

    def test_live_resolution_is_honoured(self):
        registry = ApprovalRegistry()
        registry.set_backend(_ApproveBackend())

        decision = registry.approve_sync(
            agent_name="a",
            tool_name="execute_command",
            arguments={"command": "ls"},
            liveness=lambda: True,
        )

        assert decision.approved is True

    def test_default_no_liveness_preserves_behaviour(self):
        registry = ApprovalRegistry()
        registry.set_backend(_ApproveBackend())

        decision = registry.approve_sync(
            agent_name="a",
            tool_name="execute_command",
            arguments={"command": "ls"},
        )

        assert decision.approved is True


# ── approve_async ───────────────────────────────────────────────────────────


class TestApproveAsyncLiveness:
    @pytest.mark.asyncio
    async def test_stale_resolution_is_denied_and_not_persisted(self):
        registry = ApprovalRegistry()
        registry.set_backend(_ApproveBackend())

        decision = await registry.approve_async(
            agent_name="a",
            tool_name="execute_command",
            arguments={"command": "rm -rf /"},
            liveness=lambda: False,
        )

        assert decision.approved is False
        assert not registry._session_scoped_targets
        assert not registry.is_already_approved(
            "execute_command", {"command": "rm -rf /"}, "a"
        )

    @pytest.mark.asyncio
    async def test_live_resolution_is_honoured(self):
        registry = ApprovalRegistry()
        registry.set_backend(_ApproveBackend())

        decision = await registry.approve_async(
            agent_name="a",
            tool_name="execute_command",
            arguments={"command": "ls"},
            liveness=lambda: True,
        )

        assert decision.approved is True


# ── _current_turn_liveness (effective per-turn authority) ────────────────────


class _StubToken:
    """Stand-in for the ``_TurnCancelToken`` a ``chat``/``achat`` turn owns."""

    def __init__(self, cancelled: bool = False):
        self._cancelled = cancelled

    def is_set(self) -> bool:
        return self._cancelled


class _FakeEvent:
    def __init__(self, is_set: bool = False):
        self._set = is_set

    def is_set(self) -> bool:
        return self._set


class _FakeController:
    def __init__(self, event):
        self.event = event


class _LivenessAgent(ToolExecutionMixin):
    """Minimal carrier exposing the attrs ``_current_turn_liveness`` reads."""

    def __init__(self, token=None, controller=None):
        self._active_turn_token = token
        self.interrupt_controller = controller


class TestCurrentTurnLiveness:
    """The predicate must observe the *effective* per-turn cancel authority.

    Regression for the Greptile P1: an explicit ``cancel_token=`` selected by
    ``chat``/``achat`` is not the agent-level ``interrupt_controller``. The
    liveness predicate must follow the registered per-turn token so a ``/stop``
    on that token is seen at the approval-resolution boundary.
    """

    def test_prefers_active_token_and_reports_stale_when_cancelled(self):
        agent = _LivenessAgent(token=_StubToken(cancelled=True))
        predicate = agent._current_turn_liveness()
        assert predicate is not None
        assert predicate() is False  # turn no longer live

    def test_active_token_live_reports_live(self):
        agent = _LivenessAgent(token=_StubToken(cancelled=False))
        predicate = agent._current_turn_liveness()
        assert predicate is not None
        assert predicate() is True

    def test_active_token_takes_precedence_over_controller(self):
        # Explicit token cancelled, controller still live → must report stale.
        agent = _LivenessAgent(
            token=_StubToken(cancelled=True),
            controller=_FakeController(_FakeEvent(is_set=False)),
        )
        predicate = agent._current_turn_liveness()
        assert predicate() is False

    def test_falls_back_to_controller_event_when_no_token(self):
        agent = _LivenessAgent(
            token=None, controller=_FakeController(_FakeEvent(is_set=True))
        )
        predicate = agent._current_turn_liveness()
        assert predicate is not None
        assert predicate() is False

    def test_none_when_no_token_and_no_controller(self):
        agent = _LivenessAgent(token=None, controller=None)
        assert agent._current_turn_liveness() is None
