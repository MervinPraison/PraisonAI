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


class TestToolDecoratorApprovalParam:
    """Test the canonical @tool(approval=...) parameter, mirroring Agent(approval=...)."""

    def test_tool_approval_param_registers(self):
        """@tool(approval="critical") registers at that level."""
        @tool(approval="critical")
        def approve_critical(env: str) -> str:
            """A critical gated tool."""
            return "deployed"

        try:
            assert approve_critical.approval == "critical"
            assert approve_critical.requires_approval == "critical"
            assert approve_critical.risk_level == "critical"
            assert is_approval_required("approve_critical") is True
            assert get_risk_level("approve_critical") == "critical"
        finally:
            remove_approval_requirement("approve_critical")

    def test_tool_approval_true_registers_high(self):
        """@tool(approval=True) mirrors requires_approval=True (default 'high')."""
        @tool(approval=True)
        def approve_true(order_id: str) -> str:
            """A gated tool."""
            return "ok"

        try:
            assert approve_true.risk_level == "high"
            assert is_approval_required("approve_true") is True
        finally:
            remove_approval_requirement("approve_true")

    def test_approval_equivalent_to_requires_approval(self):
        """approval= and requires_approval= register identically."""
        @tool(approval="high")
        def via_approval(x: str) -> str:
            """Via approval."""
            return x

        @tool(requires_approval="high")
        def via_requires(x: str) -> str:
            """Via requires_approval."""
            return x

        try:
            assert get_risk_level("via_approval") == get_risk_level("via_requires")
            assert via_approval.risk_level == via_requires.risk_level == "high"
        finally:
            remove_approval_requirement("via_approval")
            remove_approval_requirement("via_requires")

    def test_requires_approval_deprecation_warning(self):
        """The requires_approval alias still works but warns once."""
        with pytest.warns(DeprecationWarning):
            @tool(requires_approval=True)
            def deprecated_alias(x: str) -> str:
                """Uses the deprecated alias."""
                return x

        try:
            assert deprecated_alias.risk_level == "high"
            assert is_approval_required("deprecated_alias") is True
        finally:
            remove_approval_requirement("deprecated_alias")

    def test_approval_does_not_warn(self):
        """The canonical approval= param does not emit a DeprecationWarning."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)

            @tool(approval=True)
            def no_warn(x: str) -> str:
                """Canonical param, no warning."""
                return x

        try:
            assert no_warn.risk_level == "high"
        finally:
            remove_approval_requirement("no_warn")

    def test_approval_wins_over_requires_approval(self):
        """When both are set, approval= wins for the resolved value.

        The deprecated spelling still warns because the caller used it, but the
        canonical ``approval`` determines the registered risk level.
        """
        with pytest.warns(DeprecationWarning):
            @tool(approval="critical", requires_approval="low")
            def both_set(x: str) -> str:
                """Both spellings given."""
                return x

        try:
            assert both_set.risk_level == "critical"
            assert get_risk_level("both_set") == "critical"
        finally:
            remove_approval_requirement("both_set")

    def test_requires_approval_false_still_warns(self):
        """An explicit requires_approval=False is still deprecated usage.

        Regression guard: a plain ``False`` default would swallow the warning
        and let the old spelling be used silently, so an explicit ``False`` must
        still nudge callers to migrate to ``approval=``.
        """
        with pytest.warns(DeprecationWarning):
            @tool(requires_approval=False)
            def explicit_false(x: str) -> str:
                """Uses the deprecated alias explicitly with False."""
                return x

        assert explicit_false.risk_level is None
        assert is_approval_required("explicit_false") is False

    def test_omitted_alias_does_not_warn(self):
        """Omitting the deprecated alias entirely emits no warning."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)

            @tool
            def plain_tool(x: str) -> str:
                """No approval params at all."""
                return x

        assert plain_tool.risk_level is None
        assert plain_tool.requires_approval is False
