"""Tests for browser protocol message types."""

import pytest
import json

from praisonai.browser.protocol import (
    WSMessage,
    ObservationMessage,
    ActionMessage,
    StartSessionMessage,
    StopSessionMessage,
    StatusMessage,
    ErrorMessage,
    parse_message,
)


class TestWSMessage:
    """Tests for base WSMessage class."""
    
    def test_to_json(self):
        """Test JSON serialization."""
        msg = WSMessage(type="test", session_id="abc123")
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["type"] == "test"
        assert data["session_id"] == "abc123"
    
    def test_from_json(self):
        """Test JSON deserialization."""
        json_str = '{"type": "test", "session_id": "xyz789"}'
        msg = WSMessage.from_json(json_str)
        assert msg.type == "test"
        assert msg.session_id == "xyz789"


class TestObservationMessage:
    """Tests for ObservationMessage."""
    
    def test_create_observation(self):
        """Test observation message creation."""
        obs = ObservationMessage(
            session_id="sess123",
            task="Find restaurants",
            url="https://example.com",
            title="Example",
            elements=[{"selector": "#btn", "tag": "button", "text": "Click"}],
            step_number=1,
        )
        assert obs.type == "observation"
        assert obs.task == "Find restaurants"
        assert len(obs.elements) == 1
        assert obs.step_number == 1
    
    def test_observation_to_json(self):
        """Test observation serialization."""
        obs = ObservationMessage(
            session_id="sess123",
            task="Test task",
            url="https://test.com",
            title="Test",
            step_number=5,
        )
        json_str = obs.to_json()
        data = json.loads(json_str)
        assert data["type"] == "observation"
        assert data["step_number"] == 5


class TestActionMessage:
    """Tests for ActionMessage."""
    
    def test_create_click_action(self):
        """Test click action creation."""
        action = ActionMessage(
            session_id="sess123",
            action="click",
            selector="#submit-btn",
            thought="Clicking submit button",
        )
        assert action.type == "action"
        assert action.action == "click"
        assert action.selector == "#submit-btn"
    
    def test_create_type_action(self):
        """Test type action creation."""
        action = ActionMessage(
            session_id="sess123",
            action="type",
            selector="#search",
            text="query text",
        )
        assert action.action == "type"
        assert action.text == "query text"
    
    def test_done_action(self):
        """Test done action."""
        action = ActionMessage(
            session_id="sess123",
            action="done",
            done=True,
            thought="Task completed successfully",
        )
        assert action.done is True


class TestStartSessionMessage:
    """Tests for StartSessionMessage."""
    
    def test_create_start_session(self):
        """Test start session message."""
        msg = StartSessionMessage(
            session_id="",
            goal="Navigate to Google",
            model="gpt-4o",
        )
        assert msg.type == "start_session"
        assert msg.goal == "Navigate to Google"
        assert msg.model == "gpt-4o"


class TestParseMessage:
    """Tests for message parsing."""
    
    def test_parse_observation(self):
        """Test parsing observation message."""
        data = json.dumps({
            "type": "observation",
            "session_id": "test123",
            "task": "Test",
            "url": "https://test.com",
            "title": "Test",
            "elements": [],
            "console_logs": [],
            "step_number": 1,
        })
        msg = parse_message(data)
        assert isinstance(msg, ObservationMessage)
        assert msg.step_number == 1
    
    def test_parse_action(self):
        """Test parsing action message."""
        data = json.dumps({
            "type": "action",
            "session_id": "test123",
            "action": "click",
            "selector": "#btn",
        })
        msg = parse_message(data)
        assert isinstance(msg, ActionMessage)
        assert msg.action == "click"
    
    def test_parse_start_session(self):
        """Test parsing start session message."""
        data = json.dumps({
            "type": "start_session",
            "session_id": "",
            "goal": "Test goal",
        })
        msg = parse_message(data)
        assert isinstance(msg, StartSessionMessage)
    
    def test_parse_status(self):
        """Test parsing status message."""
        data = json.dumps({
            "type": "status",
            "session_id": "test123",
            "status": "running",
            "message": "Session started",
        })
        msg = parse_message(data)
        assert isinstance(msg, StatusMessage)
        assert msg.status == "running"
    
    def test_parse_error(self):
        """Test parsing error message."""
        data = json.dumps({
            "type": "error",
            "session_id": "",
            "error": "Something went wrong",
            "code": "INTERNAL_ERROR",
        })
        msg = parse_message(data)
        assert isinstance(msg, ErrorMessage)
        assert msg.error == "Something went wrong"
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns error message."""
        msg = parse_message("not valid json")
        assert isinstance(msg, ErrorMessage)
        assert msg.code == "PARSE_ERROR"
    
    def test_parse_unknown_type(self):
        """Test parsing unknown message type."""
        data = json.dumps({"type": "unknown_type"})
        msg = parse_message(data)
        assert isinstance(msg, WSMessage)
        assert msg.type == "unknown_type"
