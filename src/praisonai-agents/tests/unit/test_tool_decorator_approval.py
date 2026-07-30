"""
Tests for @tool(requires_approval=...) decorator functionality.
"""
import pytest

from praisonaiagents import tool
from praisonaiagents.approval import (
    get_approval_registry,
    is_approval_required,
    get_risk_level,
    remove_approval_requirement,
)


class TestToolDecoratorRequiresApproval:
    """Test @tool decorator with requires_approval parameter."""

    def test_requires_approval_true_registers_high(self):
        """@tool(requires_approval=True) registers the tool at 'high' risk."""
        @tool(requires_approval=True)
        def gated_true(order_id: str) -> str:
            """A gated tool."""
            return "ok"

        try:
            assert gated_true.requires_approval is True
            assert gated_true.risk_level == "high"
            assert is_approval_required("gated_true") is True
            assert get_risk_level("gated_true") == "high"
        finally:
            remove_approval_requirement("gated_true")

    def test_requires_approval_string_sets_risk_level(self):
        """A string maps to the given risk level."""
        @tool(requires_approval="critical")
        def gated_critical(env: str) -> str:
            """A critical gated tool."""
            return "deployed"

        try:
            assert gated_critical.risk_level == "critical"
            assert is_approval_required("gated_critical") is True
            assert get_risk_level("gated_critical") == "critical"
        finally:
            remove_approval_requirement("gated_critical")

    def test_unset_does_not_register(self):
        """Unset (default) leaves approval behaviour unchanged."""
        @tool
        def not_gated(query: str) -> str:
            """An ungated tool."""
            return query

        assert not_gated.requires_approval is False
        assert not_gated.risk_level is None
        assert is_approval_required("not_gated") is False

    def test_custom_name_registers_by_tool_name(self):
        """Registration uses the resolved tool name, not the function name."""
        @tool(name="danger_op", requires_approval=True)
        def some_func(x: str) -> str:
            """A renamed gated tool."""
            return x

        try:
            assert is_approval_required("danger_op") is True
            assert is_approval_required("some_func") is False
        finally:
            remove_approval_requirement("danger_op")

    def test_invalid_risk_level_string_rejected(self):
        """A misspelled risk level raises rather than silently registering.

        Guards against ``requires_approval="critial"`` slipping through as a
        non-critical tool when critical-only checks compare against "critical".
        """
        with pytest.raises(ValueError):
            @tool(requires_approval="critial")
            def typo_level(x: str) -> str:
                """Bad level."""
                return x

        assert is_approval_required("typo_level") is False

    def test_registration_failure_fails_closed(self, monkeypatch):
        """If approval registration raises, no ungated tool is exposed."""
        import praisonaiagents.approval as approval_mod

        def boom(*_args, **_kwargs):
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr(approval_mod, "add_approval_requirement", boom)

        with pytest.raises(RuntimeError):
            @tool(requires_approval=True)
            def fails_closed(x: str) -> str:
                """Should not be exposed if registration fails."""
                return x

        assert is_approval_required("fails_closed") is False
