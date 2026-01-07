"""Tests for approval/permission flow."""
import pytest
from unittest.mock import Mock, patch


class TestApprovalPatternMatching:
    """Tests for approval pattern matching."""
    
    def test_pattern_matches_exact_action(self):
        """Pattern matches exact action type."""
        from praisonai.cli.interactive.events import ApprovalRequest
        
        request = ApprovalRequest(
            action_type="file_read",
            description="Read file",
            tool_name="read_file",
            parameters={"path": "/tmp/test.txt"}
        )
        
        assert request.matches_pattern("file_read") is True
        assert request.matches_pattern("file_write") is False
    
    def test_pattern_matches_wildcard_path(self):
        """Pattern with wildcard path matches any path."""
        from praisonai.cli.interactive.events import ApprovalRequest
        
        request = ApprovalRequest(
            action_type="file_write",
            description="Write file",
            tool_name="write_file",
            parameters={"path": "/tmp/test.txt"}
        )
        
        assert request.matches_pattern("file_write:*") is True
        assert request.matches_pattern("file_write:/tmp/*") is True
        assert request.matches_pattern("file_write:/var/*") is False
    
    def test_pattern_matches_glob(self):
        """Pattern with glob matches correctly."""
        from praisonai.cli.interactive.events import ApprovalRequest
        
        request = ApprovalRequest(
            action_type="shell_command",
            description="Run ls",
            tool_name="execute_command",
            parameters={"command": "ls -la"}
        )
        
        assert request.matches_pattern("shell_command:ls*") is True
        assert request.matches_pattern("shell_command:rm*") is False


class TestApprovalDecisionFlow:
    """Tests for approval decision flow."""
    
    def test_auto_mode_approves_all(self):
        """Auto mode approves all requests."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        from praisonai.cli.interactive.events import ApprovalRequest, ApprovalDecision
        
        config = InteractiveConfig(approval_mode="auto")
        core = InteractiveCore(config=config)
        
        request = ApprovalRequest(
            action_type="file_write",
            description="Write dangerous file",
            tool_name="write_file",
            parameters={"path": "/etc/passwd"}
        )
        
        decision = core.check_permission(request)
        assert decision == ApprovalDecision.ONCE
    
    def test_reject_mode_rejects_all(self):
        """Reject mode rejects all requests."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        from praisonai.cli.interactive.events import ApprovalRequest, ApprovalDecision
        
        config = InteractiveConfig(approval_mode="reject")
        core = InteractiveCore(config=config)
        
        request = ApprovalRequest(
            action_type="file_read",
            description="Read file",
            tool_name="read_file",
            parameters={"path": "/tmp/safe.txt"}
        )
        
        decision = core.check_permission(request)
        assert decision == ApprovalDecision.REJECT
    
    def test_prompt_mode_returns_none(self):
        """Prompt mode returns None (needs user input)."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        from praisonai.cli.interactive.events import ApprovalRequest
        
        config = InteractiveConfig(approval_mode="prompt")
        core = InteractiveCore(config=config)
        
        request = ApprovalRequest(
            action_type="file_write",
            description="Write file",
            tool_name="write_file",
            parameters={"path": "/tmp/test.txt"}
        )
        
        decision = core.check_permission(request)
        assert decision is None  # Needs user input
    
    def test_persistent_pattern_auto_approves(self):
        """Persistent approval pattern auto-approves matching requests."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        from praisonai.cli.interactive.events import ApprovalRequest, ApprovalDecision
        
        config = InteractiveConfig(approval_mode="prompt")
        core = InteractiveCore(config=config)
        
        # Add persistent pattern
        core.add_approval_pattern("file_read:*", persistent=False)
        
        request = ApprovalRequest(
            action_type="file_read",
            description="Read file",
            tool_name="read_file",
            parameters={"path": "/any/file.txt"}
        )
        
        decision = core.check_permission(request)
        assert decision in (ApprovalDecision.ALWAYS, ApprovalDecision.ALWAYS_SESSION)


class TestApprovalEvents:
    """Tests for approval event emission."""
    
    def test_approval_asked_event_emitted(self):
        """APPROVAL_ASKED event is emitted."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import (
            InteractiveEventType, ApprovalRequest
        )
        
        core = InteractiveCore()
        events = []
        core.subscribe(lambda e: events.append(e))
        
        request = ApprovalRequest(
            action_type="file_write",
            description="Write file",
            tool_name="write_file",
            parameters={"path": "/tmp/test.txt"}
        )
        
        core._emit_approval_request(request)
        
        assert len(events) == 1
        assert events[0].type == InteractiveEventType.APPROVAL_ASKED
        assert events[0].data["request_id"] == request.request_id
    
    def test_approval_answered_event_emitted(self):
        """APPROVAL_ANSWERED event is emitted."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import (
            InteractiveEventType, ApprovalResponse, ApprovalDecision
        )
        
        core = InteractiveCore()
        events = []
        core.subscribe(lambda e: events.append(e))
        
        response = ApprovalResponse(
            request_id="req-123",
            decision=ApprovalDecision.ONCE
        )
        
        core._emit_approval_response(response)
        
        assert len(events) == 1
        assert events[0].type == InteractiveEventType.APPROVAL_ANSWERED
        assert events[0].data["decision"] == "once"


class TestPersistentApprovals:
    """Tests for persistent approval storage."""
    
    def test_add_persistent_pattern(self):
        """Add persistent approval pattern."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        # Clear existing patterns
        core._approval_patterns.clear()
        
        core.add_approval_pattern("file_read:/tmp/*", persistent=False)
        
        assert "file_read:/tmp/*" in core._session_approvals
    
    def test_session_pattern_not_persisted(self):
        """Session-only patterns are not persisted."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        core.add_approval_pattern("file_write:/tmp/*", persistent=False)
        
        # Should be in session approvals, not persistent
        assert "file_write:/tmp/*" in core._session_approvals
        assert "file_write:/tmp/*" not in core._approval_patterns
