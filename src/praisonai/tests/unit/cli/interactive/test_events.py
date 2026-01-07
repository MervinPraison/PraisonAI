"""Tests for InteractiveCore events module."""
import pytest
import time
from dataclasses import asdict


class TestInteractiveEventType:
    """Tests for InteractiveEventType enum."""
    
    def test_event_types_exist(self):
        """Verify all required event types exist."""
        from praisonai.cli.interactive.events import InteractiveEventType
        
        required_types = [
            "MESSAGE_START",
            "MESSAGE_CHUNK", 
            "MESSAGE_END",
            "TOOL_START",
            "TOOL_END",
            "APPROVAL_ASKED",
            "APPROVAL_ANSWERED",
            "ERROR",
            "IDLE",
            "SESSION_CREATED",
            "SESSION_RESUMED",
        ]
        
        for event_type in required_types:
            assert hasattr(InteractiveEventType, event_type), f"Missing event type: {event_type}"
    
    def test_event_type_values_are_strings(self):
        """Event type values should be descriptive strings."""
        from praisonai.cli.interactive.events import InteractiveEventType
        
        assert InteractiveEventType.MESSAGE_START.value == "message.start"
        assert InteractiveEventType.MESSAGE_CHUNK.value == "message.chunk"
        assert InteractiveEventType.MESSAGE_END.value == "message.end"
        assert InteractiveEventType.TOOL_START.value == "tool.start"
        assert InteractiveEventType.TOOL_END.value == "tool.end"
        assert InteractiveEventType.APPROVAL_ASKED.value == "approval.asked"
        assert InteractiveEventType.APPROVAL_ANSWERED.value == "approval.answered"
        assert InteractiveEventType.ERROR.value == "error"
        assert InteractiveEventType.IDLE.value == "idle"


class TestInteractiveEvent:
    """Tests for InteractiveEvent dataclass."""
    
    def test_event_creation_minimal(self):
        """Create event with minimal required fields."""
        from praisonai.cli.interactive.events import InteractiveEvent, InteractiveEventType
        
        event = InteractiveEvent(type=InteractiveEventType.MESSAGE_START)
        
        assert event.type == InteractiveEventType.MESSAGE_START
        assert event.data == {}
        assert event.timestamp > 0
        assert event.source is None
    
    def test_event_creation_with_data(self):
        """Create event with data payload."""
        from praisonai.cli.interactive.events import InteractiveEvent, InteractiveEventType
        
        data = {"content": "Hello", "role": "assistant"}
        event = InteractiveEvent(
            type=InteractiveEventType.MESSAGE_CHUNK,
            data=data,
            source="agent"
        )
        
        assert event.type == InteractiveEventType.MESSAGE_CHUNK
        assert event.data == data
        assert event.source == "agent"
    
    def test_event_timestamp_auto_generated(self):
        """Timestamp should be auto-generated if not provided."""
        from praisonai.cli.interactive.events import InteractiveEvent, InteractiveEventType
        
        before = time.time()
        event = InteractiveEvent(type=InteractiveEventType.IDLE)
        after = time.time()
        
        assert before <= event.timestamp <= after
    
    def test_event_to_dict(self):
        """Event should be convertible to dict."""
        from praisonai.cli.interactive.events import InteractiveEvent, InteractiveEventType
        
        event = InteractiveEvent(
            type=InteractiveEventType.ERROR,
            data={"message": "Something went wrong"},
            source="system"
        )
        
        d = event.to_dict()
        
        assert d["type"] == "error"
        assert d["data"] == {"message": "Something went wrong"}
        assert d["source"] == "system"
        assert "timestamp" in d


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""
    
    def test_approval_request_creation(self):
        """Create an approval request."""
        from praisonai.cli.interactive.events import ApprovalRequest
        
        request = ApprovalRequest(
            action_type="file_write",
            description="Write to /tmp/test.txt",
            tool_name="write_file",
            parameters={"path": "/tmp/test.txt", "content": "hello"}
        )
        
        assert request.action_type == "file_write"
        assert request.description == "Write to /tmp/test.txt"
        assert request.tool_name == "write_file"
        assert request.parameters == {"path": "/tmp/test.txt", "content": "hello"}
        assert request.request_id is not None  # Auto-generated
    
    def test_approval_request_with_custom_id(self):
        """Create approval request with custom ID."""
        from praisonai.cli.interactive.events import ApprovalRequest
        
        request = ApprovalRequest(
            action_type="shell_command",
            description="Run ls -la",
            tool_name="execute_command",
            parameters={"command": "ls -la"},
            request_id="custom-123"
        )
        
        assert request.request_id == "custom-123"


class TestApprovalResponse:
    """Tests for ApprovalResponse dataclass."""
    
    def test_approval_response_once(self):
        """Create a 'once' approval response."""
        from praisonai.cli.interactive.events import ApprovalResponse, ApprovalDecision
        
        response = ApprovalResponse(
            request_id="req-123",
            decision=ApprovalDecision.ONCE
        )
        
        assert response.request_id == "req-123"
        assert response.decision == ApprovalDecision.ONCE
        assert response.remember_pattern is None
    
    def test_approval_response_always(self):
        """Create an 'always' approval response with pattern."""
        from praisonai.cli.interactive.events import ApprovalResponse, ApprovalDecision
        
        response = ApprovalResponse(
            request_id="req-456",
            decision=ApprovalDecision.ALWAYS,
            remember_pattern="file_write:/tmp/*"
        )
        
        assert response.decision == ApprovalDecision.ALWAYS
        assert response.remember_pattern == "file_write:/tmp/*"
    
    def test_approval_response_reject(self):
        """Create a 'reject' approval response."""
        from praisonai.cli.interactive.events import ApprovalResponse, ApprovalDecision
        
        response = ApprovalResponse(
            request_id="req-789",
            decision=ApprovalDecision.REJECT
        )
        
        assert response.decision == ApprovalDecision.REJECT


class TestApprovalDecision:
    """Tests for ApprovalDecision enum."""
    
    def test_all_decisions_exist(self):
        """Verify all approval decisions exist."""
        from praisonai.cli.interactive.events import ApprovalDecision
        
        assert hasattr(ApprovalDecision, "ONCE")
        assert hasattr(ApprovalDecision, "ALWAYS")
        assert hasattr(ApprovalDecision, "ALWAYS_SESSION")
        assert hasattr(ApprovalDecision, "REJECT")
    
    def test_decision_values(self):
        """Verify decision values."""
        from praisonai.cli.interactive.events import ApprovalDecision
        
        assert ApprovalDecision.ONCE.value == "once"
        assert ApprovalDecision.ALWAYS.value == "always"
        assert ApprovalDecision.ALWAYS_SESSION.value == "always_session"
        assert ApprovalDecision.REJECT.value == "reject"
