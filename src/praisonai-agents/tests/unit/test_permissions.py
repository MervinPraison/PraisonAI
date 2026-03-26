"""Tests for Permission Tiers (F3).

Tests the approval="safe"/"read_only"/"full" permission presets that provide
declarative tool access control via the existing approval= Agent param.
"""

import os
import pytest
from unittest.mock import patch, MagicMock


def _mock_registry_approve_sync(*args, **kwargs):
    """Mock approve_sync that auto-approves (no console prompt)."""
    from praisonaiagents.approval.protocols import ApprovalDecision
    return ApprovalDecision(approved=True, reason="mocked")


class TestPermissionPresets:
    """Test PERMISSION_PRESETS in approval/registry.py."""

    def test_presets_exist(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS
        assert "safe" in PERMISSION_PRESETS
        assert "read_only" in PERMISSION_PRESETS
        assert "full" in PERMISSION_PRESETS

    def test_safe_preset_is_frozenset(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS
        assert isinstance(PERMISSION_PRESETS["safe"], frozenset)

    def test_safe_blocks_execute_command(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS
        assert "execute_command" in PERMISSION_PRESETS["safe"]

    def test_safe_blocks_delete_file(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS
        assert "delete_file" in PERMISSION_PRESETS["safe"]

    def test_safe_blocks_all_dangerous(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS, DEFAULT_DANGEROUS_TOOLS
        for tool_name in DEFAULT_DANGEROUS_TOOLS:
            assert tool_name in PERMISSION_PRESETS["safe"], f"{tool_name} not in safe preset"

    def test_read_only_is_superset_of_safe(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS
        assert PERMISSION_PRESETS["safe"].issubset(PERMISSION_PRESETS["read_only"])

    def test_full_is_empty(self):
        from praisonaiagents.approval.registry import PERMISSION_PRESETS
        assert len(PERMISSION_PRESETS["full"]) == 0


class TestAgentPermissionInit:
    """Test that Agent correctly resolves permission presets from approval= param."""

    def test_no_approval_no_denials(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert agent._perm_deny == frozenset()
        assert agent._perm_allow is None

    def test_approval_safe_sets_deny(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval="safe")
        assert len(agent._perm_deny) > 0
        assert "execute_command" in agent._perm_deny

    def test_approval_read_only_sets_deny(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval="read_only")
        assert "execute_command" in agent._perm_deny
        assert "write_file" in agent._perm_deny

    def test_approval_full_empty_deny(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval="full")
        assert agent._perm_deny == frozenset()

    def test_approval_true_still_works(self):
        """Backward compat: approval=True should still create AutoApproveBackend."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval=True)
        assert agent._approval_backend is not None
        assert agent._perm_deny == frozenset()

    def test_approval_false_still_works(self):
        """Backward compat: approval=False should still disable."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval=False)
        assert agent._approval_backend is None
        assert agent._perm_deny == frozenset()

    def test_approval_none_still_works(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval=None)
        assert agent._approval_backend is None


class TestPermissionCheck:
    """Test _check_tool_approval_sync permission fast-path."""

    def test_safe_blocks_execute_command(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval="safe")
        result = agent._check_tool_approval_sync("execute_command", {"command": "ls"})
        assert isinstance(result, dict)
        assert "permission_denied" in result
        assert result["permission_denied"] is True

    def test_safe_blocks_delete_file(self):
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test", approval="safe")
        result = agent._check_tool_approval_sync("delete_file", {"path": "/tmp/x"})
        assert result.get("permission_denied") is True

    def test_safe_allows_read_file(self):
        """read_file is NOT in the dangerous tools list, so it should pass."""
        from praisonaiagents import Agent
        mock_registry = MagicMock()
        mock_registry.approve_sync.return_value = MagicMock(
            approved=True, reason="mock", modified_args=None
        )
        mock_registry.mark_approved = MagicMock()
        with patch("praisonaiagents.approval.get_approval_registry", return_value=mock_registry):
            agent = Agent(name="test", instructions="test", approval="safe")
            result = agent._check_tool_approval_sync("read_file", {"path": "/tmp/x"})
            assert result is None or (isinstance(result, tuple) and len(result) == 2)

    def test_full_allows_dangerous_tool(self):
        """approval='full' should not deny execute_command via permission tier."""
        from praisonaiagents import Agent
        mock_registry = MagicMock()
        mock_registry.approve_sync.return_value = MagicMock(
            approved=True, reason="mock", modified_args=None
        )
        mock_registry.mark_approved = MagicMock()
        with patch("praisonaiagents.approval.get_approval_registry", return_value=mock_registry):
            agent = Agent(name="test", instructions="test", approval="full")
            result = agent._check_tool_approval_sync("execute_command", {"command": "ls"})
            assert result is None or (isinstance(result, tuple) and len(result) == 2)

    def test_no_approval_allows_non_dangerous(self):
        """Without approval= param, non-dangerous tools pass through."""
        from praisonaiagents import Agent
        mock_registry = MagicMock()
        mock_registry.approve_sync.return_value = MagicMock(
            approved=True, reason="mock", modified_args=None
        )
        mock_registry.mark_approved = MagicMock()
        with patch("praisonaiagents.approval.get_approval_registry", return_value=mock_registry):
            agent = Agent(name="test", instructions="test")
            result = agent._check_tool_approval_sync("my_custom_tool", {})
            assert result is None or (isinstance(result, tuple) and len(result) == 2)


class TestPermissionZeroOverhead:
    """Verify zero overhead when no permission preset is set."""

    def test_empty_frozenset_falsy(self):
        """Empty frozenset is falsy, so 'if self._perm_deny' skips the check."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert not agent._perm_deny  # frozenset() is falsy

    def test_none_perm_allow_skips(self):
        """None _perm_allow means 'if self._perm_allow is not None' skips."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert agent._perm_allow is None
