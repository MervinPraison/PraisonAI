"""
Tests for Autonomy Mode System.

Test-Driven Development approach for autonomy/approval modes.
"""

import pytest
from unittest.mock import MagicMock

from praisonai.cli.features.autonomy_mode import (
    AutonomyMode,
    ActionType,
    ActionRequest,
    ApprovalResult,
    AutonomyPolicy,
    AutonomyManager,
    AutonomyModeHandler,
    create_file_write_action,
    create_shell_command_action,
    create_git_action,
    create_tool_call_action,
)


# ============================================================================
# AutonomyMode Tests
# ============================================================================

class TestAutonomyMode:
    """Tests for AutonomyMode enum."""
    
    def test_mode_values(self):
        """Test mode enum values."""
        assert AutonomyMode.SUGGEST.value == "suggest"
        assert AutonomyMode.AUTO_EDIT.value == "auto_edit"
        assert AutonomyMode.FULL_AUTO.value == "full_auto"
    
    def test_from_string_valid(self):
        """Test parsing valid mode strings."""
        assert AutonomyMode.from_string("suggest") == AutonomyMode.SUGGEST
        assert AutonomyMode.from_string("auto_edit") == AutonomyMode.AUTO_EDIT
        assert AutonomyMode.from_string("full_auto") == AutonomyMode.FULL_AUTO
    
    def test_from_string_with_hyphen(self):
        """Test parsing mode strings with hyphens."""
        assert AutonomyMode.from_string("auto-edit") == AutonomyMode.AUTO_EDIT
        assert AutonomyMode.from_string("full-auto") == AutonomyMode.FULL_AUTO
    
    def test_from_string_case_insensitive(self):
        """Test case insensitive parsing."""
        assert AutonomyMode.from_string("SUGGEST") == AutonomyMode.SUGGEST
        assert AutonomyMode.from_string("Auto_Edit") == AutonomyMode.AUTO_EDIT
    
    def test_from_string_invalid(self):
        """Test parsing invalid mode string."""
        with pytest.raises(ValueError, match="Unknown autonomy mode"):
            AutonomyMode.from_string("invalid_mode")


# ============================================================================
# ActionType Tests
# ============================================================================

class TestActionType:
    """Tests for ActionType enum."""
    
    def test_action_types_exist(self):
        """Test all action types exist."""
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_WRITE.value == "file_write"
        assert ActionType.FILE_DELETE.value == "file_delete"
        assert ActionType.SHELL_COMMAND.value == "shell_command"
        assert ActionType.NETWORK_REQUEST.value == "network_request"
        assert ActionType.CODE_EXECUTION.value == "code_execution"
        assert ActionType.GIT_OPERATION.value == "git_operation"
        assert ActionType.TOOL_CALL.value == "tool_call"


# ============================================================================
# ActionRequest Tests
# ============================================================================

class TestActionRequest:
    """Tests for ActionRequest dataclass."""
    
    def test_create_basic_action(self):
        """Test creating a basic action request."""
        action = ActionRequest(
            action_type=ActionType.FILE_WRITE,
            description="Write to config.py"
        )
        assert action.action_type == ActionType.FILE_WRITE
        assert action.description == "Write to config.py"
        assert action.details == {}
        assert action.risk_level == "medium"
        assert action.reversible is True
    
    def test_create_action_with_details(self):
        """Test creating action with details."""
        action = ActionRequest(
            action_type=ActionType.SHELL_COMMAND,
            description="Run tests",
            details={"command": "pytest", "cwd": "/project"},
            risk_level="low",
            reversible=False
        )
        assert action.details["command"] == "pytest"
        assert action.risk_level == "low"
        assert action.reversible is False
    
    def test_action_str(self):
        """Test action string representation."""
        action = ActionRequest(
            action_type=ActionType.FILE_WRITE,
            description="Write to file.py"
        )
        assert "file_write" in str(action)
        assert "Write to file.py" in str(action)


# ============================================================================
# ApprovalResult Tests
# ============================================================================

class TestApprovalResult:
    """Tests for ApprovalResult dataclass."""
    
    def test_approved_result(self):
        """Test approved result."""
        result = ApprovalResult(approved=True)
        assert result.approved is True
        assert result.reason is None
        assert result.remember_choice is False
    
    def test_denied_result_with_reason(self):
        """Test denied result with reason."""
        result = ApprovalResult(
            approved=False,
            reason="User denied the action"
        )
        assert result.approved is False
        assert result.reason == "User denied the action"
    
    def test_result_with_remember(self):
        """Test result with remember choice."""
        result = ApprovalResult(
            approved=True,
            remember_choice=True
        )
        assert result.remember_choice is True


# ============================================================================
# AutonomyPolicy Tests
# ============================================================================

class TestAutonomyPolicy:
    """Tests for AutonomyPolicy."""
    
    def test_suggest_mode_policy(self):
        """Test policy for suggest mode."""
        policy = AutonomyPolicy.for_mode(AutonomyMode.SUGGEST)
        
        assert policy.mode == AutonomyMode.SUGGEST
        assert ActionType.FILE_READ in policy.auto_approve
        assert ActionType.FILE_WRITE in policy.require_approval
        assert ActionType.SHELL_COMMAND in policy.require_approval
        assert policy.show_preview is True
    
    def test_auto_edit_mode_policy(self):
        """Test policy for auto-edit mode."""
        policy = AutonomyPolicy.for_mode(AutonomyMode.AUTO_EDIT)
        
        assert policy.mode == AutonomyMode.AUTO_EDIT
        assert ActionType.FILE_READ in policy.auto_approve
        assert ActionType.FILE_WRITE in policy.auto_approve
        assert ActionType.SHELL_COMMAND in policy.require_approval
        assert ActionType.FILE_DELETE in policy.require_approval
    
    def test_full_auto_mode_policy(self):
        """Test policy for full-auto mode."""
        policy = AutonomyPolicy.for_mode(AutonomyMode.FULL_AUTO)
        
        assert policy.mode == AutonomyMode.FULL_AUTO
        assert ActionType.FILE_WRITE in policy.auto_approve
        assert ActionType.SHELL_COMMAND in policy.auto_approve
        assert ActionType.FILE_DELETE in policy.auto_approve
        assert len(policy.require_approval) == 0
        assert policy.max_auto_actions == 100
    
    def test_custom_policy(self):
        """Test creating custom policy."""
        policy = AutonomyPolicy(
            mode=AutonomyMode.SUGGEST,
            auto_approve={ActionType.FILE_READ, ActionType.TOOL_CALL},
            blocked={ActionType.FILE_DELETE},
            trusted_paths={"/safe/path"}
        )
        
        assert ActionType.TOOL_CALL in policy.auto_approve
        assert ActionType.FILE_DELETE in policy.blocked
        assert "/safe/path" in policy.trusted_paths


# ============================================================================
# AutonomyManager Tests
# ============================================================================

class TestAutonomyManager:
    """Tests for AutonomyManager."""
    
    def test_create_manager_default(self):
        """Test creating manager with defaults."""
        manager = AutonomyManager()
        
        assert manager.mode == AutonomyMode.SUGGEST
        assert manager.policy is not None
    
    def test_create_manager_with_mode(self):
        """Test creating manager with specific mode."""
        manager = AutonomyManager(mode=AutonomyMode.FULL_AUTO)
        
        assert manager.mode == AutonomyMode.FULL_AUTO
    
    def test_set_mode(self):
        """Test changing mode."""
        manager = AutonomyManager(mode=AutonomyMode.SUGGEST)
        manager.set_mode(AutonomyMode.AUTO_EDIT)
        
        assert manager.mode == AutonomyMode.AUTO_EDIT
    
    def test_auto_approve_file_read(self):
        """Test auto-approval of file read in suggest mode."""
        manager = AutonomyManager(mode=AutonomyMode.SUGGEST)
        
        action = ActionRequest(
            action_type=ActionType.FILE_READ,
            description="Read config.py"
        )
        
        result = manager.request_approval(action)
        
        assert result.approved is True
        assert "Auto-approved" in result.reason
    
    def test_require_approval_file_write_suggest(self):
        """Test file write requires approval in suggest mode."""
        # Mock the approval callback
        mock_callback = MagicMock(return_value=ApprovalResult(approved=True))
        manager = AutonomyManager(
            mode=AutonomyMode.SUGGEST,
            approval_callback=mock_callback
        )
        
        action = ActionRequest(
            action_type=ActionType.FILE_WRITE,
            description="Write to config.py"
        )
        
        result = manager.request_approval(action)
        
        assert result.approved is True
        mock_callback.assert_called_once()
    
    def test_auto_approve_file_write_auto_edit(self):
        """Test file write is auto-approved in auto-edit mode."""
        manager = AutonomyManager(mode=AutonomyMode.AUTO_EDIT)
        
        action = ActionRequest(
            action_type=ActionType.FILE_WRITE,
            description="Write to config.py"
        )
        
        result = manager.request_approval(action)
        
        assert result.approved is True
        assert "Auto-approved" in result.reason
    
    def test_auto_approve_everything_full_auto(self):
        """Test everything is auto-approved in full-auto mode."""
        manager = AutonomyManager(mode=AutonomyMode.FULL_AUTO)
        
        actions = [
            ActionRequest(ActionType.FILE_WRITE, "Write file"),
            ActionRequest(ActionType.SHELL_COMMAND, "Run command"),
            ActionRequest(ActionType.FILE_DELETE, "Delete file"),
        ]
        
        for action in actions:
            result = manager.request_approval(action)
            assert result.approved is True
    
    def test_blocked_action(self):
        """Test blocked action is denied."""
        policy = AutonomyPolicy(
            mode=AutonomyMode.SUGGEST,
            blocked={ActionType.FILE_DELETE}
        )
        manager = AutonomyManager(mode=AutonomyMode.SUGGEST, policy=policy)
        
        action = ActionRequest(
            action_type=ActionType.FILE_DELETE,
            description="Delete important file"
        )
        
        result = manager.request_approval(action)
        
        assert result.approved is False
        assert "blocked" in result.reason.lower()
    
    def test_remember_approval(self):
        """Test remembered approval decisions."""
        mock_callback = MagicMock(return_value=ApprovalResult(
            approved=True,
            remember_choice=True
        ))
        manager = AutonomyManager(
            mode=AutonomyMode.SUGGEST,
            approval_callback=mock_callback
        )
        
        action = ActionRequest(
            action_type=ActionType.FILE_WRITE,
            description="Write to config.py",
            details={"path": "/project/config.py"}
        )
        
        # First request - should call callback
        result1 = manager.request_approval(action)
        assert result1.approved is True
        assert mock_callback.call_count == 1
        
        # Second request - should use remembered choice
        result2 = manager.request_approval(action)
        assert result2.approved is True
        assert mock_callback.call_count == 1  # Not called again
    
    def test_max_auto_actions(self):
        """Test max auto actions limit."""
        mock_callback = MagicMock(return_value=ApprovalResult(approved=True))
        policy = AutonomyPolicy(
            mode=AutonomyMode.SUGGEST,
            auto_approve={ActionType.FILE_READ},
            max_auto_actions=3
        )
        manager = AutonomyManager(
            mode=AutonomyMode.SUGGEST,
            policy=policy,
            approval_callback=mock_callback
        )
        
        action = ActionRequest(ActionType.FILE_READ, "Read file")
        
        # First 3 should be auto-approved
        for _ in range(3):
            result = manager.request_approval(action)
            assert result.approved is True
        
        # 4th should require approval (callback called)
        result = manager.request_approval(action)
        assert mock_callback.call_count == 1
    
    def test_get_stats(self):
        """Test getting approval statistics."""
        manager = AutonomyManager(mode=AutonomyMode.FULL_AUTO)
        
        # Perform some actions
        manager.request_approval(ActionRequest(ActionType.FILE_READ, "Read"))
        manager.request_approval(ActionRequest(ActionType.FILE_WRITE, "Write"))
        
        stats = manager.get_stats()
        
        assert stats["total_actions"] == 2
        assert stats["auto_approved"] == 2
        assert stats["denied"] == 0
    
    def test_reset_stats(self):
        """Test resetting statistics."""
        manager = AutonomyManager(mode=AutonomyMode.FULL_AUTO)
        
        manager.request_approval(ActionRequest(ActionType.FILE_READ, "Read"))
        manager.reset_stats()
        
        stats = manager.get_stats()
        assert stats["total_actions"] == 0
    
    def test_clear_remembered(self):
        """Test clearing remembered approvals."""
        mock_callback = MagicMock(return_value=ApprovalResult(
            approved=True,
            remember_choice=True
        ))
        manager = AutonomyManager(
            mode=AutonomyMode.SUGGEST,
            approval_callback=mock_callback
        )
        
        action = ActionRequest(ActionType.FILE_WRITE, "Write", details={"path": "/a"})
        
        # Remember approval
        manager.request_approval(action)
        assert mock_callback.call_count == 1
        
        # Clear remembered
        manager.clear_remembered()
        
        # Should call callback again
        manager.request_approval(action)
        assert mock_callback.call_count == 2


# ============================================================================
# AutonomyModeHandler Tests
# ============================================================================

class TestAutonomyModeHandler:
    """Tests for AutonomyModeHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = AutonomyModeHandler()
        assert handler.feature_name == "autonomy_mode"
    
    def test_initialize_default(self):
        """Test initializing with defaults."""
        handler = AutonomyModeHandler()
        manager = handler.initialize()
        
        assert manager is not None
        assert manager.mode == AutonomyMode.SUGGEST
    
    def test_initialize_with_mode(self):
        """Test initializing with specific mode."""
        handler = AutonomyModeHandler()
        manager = handler.initialize(mode="full_auto")
        
        assert manager.mode == AutonomyMode.FULL_AUTO
    
    def test_initialize_invalid_mode(self):
        """Test initializing with invalid mode falls back to suggest."""
        handler = AutonomyModeHandler()
        manager = handler.initialize(mode="invalid_mode")
        
        assert manager.mode == AutonomyMode.SUGGEST
    
    def test_get_manager(self):
        """Test getting manager."""
        handler = AutonomyModeHandler()
        
        assert handler.get_manager() is None
        
        handler.initialize()
        assert handler.get_manager() is not None
    
    def test_request_approval(self):
        """Test requesting approval through handler."""
        handler = AutonomyModeHandler()
        handler.initialize(mode="full_auto")
        
        action = ActionRequest(ActionType.FILE_WRITE, "Write file")
        result = handler.request_approval(action)
        
        assert result.approved is True
    
    def test_set_mode(self):
        """Test setting mode through handler."""
        handler = AutonomyModeHandler()
        handler.initialize(mode="suggest")
        
        handler.set_mode("auto_edit")
        
        assert handler.get_mode() == "auto_edit"
    
    def test_get_mode(self):
        """Test getting mode through handler."""
        handler = AutonomyModeHandler()
        
        # Before initialization
        assert handler.get_mode() == "suggest"
        
        handler.initialize(mode="full_auto")
        assert handler.get_mode() == "full_auto"


# ============================================================================
# Convenience Function Tests
# ============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_create_file_write_action(self):
        """Test creating file write action."""
        action = create_file_write_action("/path/to/file.py", "content preview")
        
        assert action.action_type == ActionType.FILE_WRITE
        assert "/path/to/file.py" in action.description
        assert action.details["path"] == "/path/to/file.py"
        assert action.risk_level == "medium"
        assert action.reversible is True
    
    def test_create_shell_command_action(self):
        """Test creating shell command action."""
        action = create_shell_command_action("pytest tests/", "/project")
        
        assert action.action_type == ActionType.SHELL_COMMAND
        assert action.details["command"] == "pytest tests/"
        assert action.details["cwd"] == "/project"
        assert action.risk_level == "medium"
        assert action.reversible is False
    
    def test_create_shell_command_dangerous(self):
        """Test dangerous shell command has high risk."""
        action = create_shell_command_action("rm -rf /")
        
        assert action.risk_level == "high"
    
    def test_create_git_action(self):
        """Test creating git action."""
        action = create_git_action("commit", {"message": "Fix bug"})
        
        assert action.action_type == ActionType.GIT_OPERATION
        assert "commit" in action.description
        assert action.details["message"] == "Fix bug"
    
    def test_create_git_action_status_low_risk(self):
        """Test git status has low risk."""
        action = create_git_action("status")
        
        assert action.risk_level == "low"
    
    def test_create_tool_call_action(self):
        """Test creating tool call action."""
        action = create_tool_call_action("web_search", {"query": "python"})
        
        assert action.action_type == ActionType.TOOL_CALL
        assert action.details["tool"] == "web_search"
        assert action.details["args"]["query"] == "python"


# ============================================================================
# Integration Tests
# ============================================================================

class TestAutonomyModeIntegration:
    """Integration tests for autonomy mode."""
    
    def test_full_workflow_suggest_mode(self):
        """Test full workflow in suggest mode."""
        approvals = []
        
        def track_approval(action):
            approvals.append(action)
            return ApprovalResult(approved=True)
        
        handler = AutonomyModeHandler()
        handler.initialize(mode="suggest", approval_callback=track_approval)
        
        # File read should be auto-approved
        read_action = ActionRequest(ActionType.FILE_READ, "Read file")
        result = handler.request_approval(read_action)
        assert result.approved is True
        assert len(approvals) == 0  # No callback for auto-approved
        
        # File write should require approval
        write_action = ActionRequest(ActionType.FILE_WRITE, "Write file")
        result = handler.request_approval(write_action)
        assert result.approved is True
        assert len(approvals) == 1  # Callback was called
    
    def test_mode_transition(self):
        """Test transitioning between modes."""
        handler = AutonomyModeHandler()
        handler.initialize(mode="suggest")
        
        # In suggest mode, file write requires approval
        mock_callback = MagicMock(return_value=ApprovalResult(approved=True))
        handler._manager.approval_callback = mock_callback
        
        write_action = ActionRequest(ActionType.FILE_WRITE, "Write")
        handler.request_approval(write_action)
        assert mock_callback.call_count == 1
        
        # Switch to auto-edit mode
        handler.set_mode("auto_edit")
        mock_callback.reset_mock()
        
        # Now file write should be auto-approved
        handler.request_approval(write_action)
        assert mock_callback.call_count == 0  # Not called
