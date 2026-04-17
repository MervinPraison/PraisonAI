"""
Tests for unified SessionInfo schema across managed agent backends.

Ensures that AnthropicManagedAgent and LocalManagedAgent return consistent
retrieve_session() schemas as specified in issue #1429.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any

# Test SessionInfo dataclass directly
def test_session_info_defaults():
    """Test SessionInfo provides proper defaults for all fields."""
    # Import from the wrapper package where SessionInfo is defined
    from praisonai.integrations._session_info import SessionInfo
    
    # Test default instance
    info = SessionInfo()
    assert info.id == ""
    assert info.status == "unknown"
    assert info.title == ""
    assert info.usage == {"input_tokens": 0, "output_tokens": 0}
    
    # Test to_dict() returns expected structure
    result = info.to_dict()
    expected = {
        "id": "",
        "status": "unknown", 
        "title": "",
        "usage": {"input_tokens": 0, "output_tokens": 0}
    }
    assert result == expected


def test_session_info_partial_usage():
    """Test SessionInfo handles partial usage dictionaries properly."""
    from praisonai.integrations._session_info import SessionInfo
    
    # Test partial usage (missing output_tokens)
    info = SessionInfo(usage={"input_tokens": 100})
    assert info.usage["input_tokens"] == 100
    assert info.usage["output_tokens"] == 0
    
    # Test partial usage (missing input_tokens) 
    info = SessionInfo(usage={"output_tokens": 200})
    assert info.usage["input_tokens"] == 0
    assert info.usage["output_tokens"] == 200

    # Test empty usage dict gets both defaults
    info = SessionInfo(usage={})
    assert info.usage["input_tokens"] == 0
    assert info.usage["output_tokens"] == 0


def test_session_info_complete():
    """Test SessionInfo with all fields provided."""
    from praisonai.integrations._session_info import SessionInfo
    
    info = SessionInfo(
        id="session-123",
        status="idle",
        title="Test Session",
        usage={"input_tokens": 150, "output_tokens": 75}
    )
    
    result = info.to_dict()
    expected = {
        "id": "session-123",
        "status": "idle",
        "title": "Test Session",
        "usage": {"input_tokens": 150, "output_tokens": 75}
    }
    assert result == expected


# Test schema consistency between backends
@patch('praisonai.integrations.managed_agents.AnthropicManagedAgent._get_client')
def test_anthropic_retrieve_session_schema(mock_get_client):
    """Test AnthropicManagedAgent.retrieve_session returns unified schema."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    # Mock Anthropic client response
    mock_session = Mock()
    mock_session.id = "anthropic-session-123"
    mock_session.status = "idle"
    mock_session.title = "Anthropic Session"
    
    mock_usage = Mock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_session.usage = mock_usage
    
    mock_client = Mock()
    mock_client.beta.sessions.retrieve.return_value = mock_session
    mock_get_client.return_value = mock_client
    
    # Create agent and test retrieve_session
    agent = AnthropicManagedAgent()
    agent._session_id = "anthropic-session-123"
    
    result = agent.retrieve_session()
    
    # Verify schema structure
    assert isinstance(result, dict)
    assert "id" in result
    assert "status" in result  
    assert "title" in result
    assert "usage" in result
    
    # Verify field values
    assert result["id"] == "anthropic-session-123"
    assert result["status"] == "idle"
    assert result["title"] == "Anthropic Session"
    assert result["usage"] == {"input_tokens": 100, "output_tokens": 50}


def test_local_retrieve_session_schema():
    """Test LocalManagedAgent.retrieve_session returns unified schema."""
    from praisonai.integrations.managed_local import LocalManagedAgent
    
    # Create local agent with session
    agent = LocalManagedAgent()
    agent._session_id = "local-session-456"
    agent.total_input_tokens = 200
    agent.total_output_tokens = 100
    
    result = agent.retrieve_session()
    
    # Verify schema structure
    assert isinstance(result, dict)
    assert "id" in result
    assert "status" in result
    assert "title" in result
    assert "usage" in result
    
    # Verify field values
    assert result["id"] == "local-session-456"
    assert result["status"] == "idle"
    assert result["title"] == ""
    assert result["usage"] == {"input_tokens": 200, "output_tokens": 100}


def test_schema_equality_between_backends():
    """Test that both backends return schemas with identical structure."""
    from praisonai.integrations.managed_local import LocalManagedAgent
    
    # Test LocalManagedAgent (easier to set up)
    local_agent = LocalManagedAgent()
    local_agent._session_id = "test-session"
    local_agent.total_input_tokens = 0
    local_agent.total_output_tokens = 0
    
    local_result = local_agent.retrieve_session()
    
    # Both should have identical keys
    expected_keys = {"id", "status", "title", "usage"}
    assert set(local_result.keys()) == expected_keys
    
    # Usage should be a dict with input_tokens and output_tokens
    assert isinstance(local_result["usage"], dict)
    assert "input_tokens" in local_result["usage"]
    assert "output_tokens" in local_result["usage"]
    
    # All values should be present (no None values)
    assert local_result["id"] is not None
    assert local_result["status"] is not None
    assert local_result["title"] is not None
    assert local_result["usage"] is not None


def test_empty_session_anthropic():
    """Test AnthropicManagedAgent.retrieve_session with no session."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    agent = AnthropicManagedAgent()
    agent._session_id = None
    
    result = agent.retrieve_session()
    
    # Should return SessionInfo defaults
    expected = {
        "id": "",
        "status": "unknown",
        "title": "",
        "usage": {"input_tokens": 0, "output_tokens": 0}
    }
    assert result == expected


def test_empty_session_local():
    """Test LocalManagedAgent.retrieve_session with no session.""" 
    from praisonai.integrations.managed_local import LocalManagedAgent
    
    agent = LocalManagedAgent()
    agent._session_id = ""
    agent.total_input_tokens = 0
    agent.total_output_tokens = 0
    
    result = agent.retrieve_session()
    
    # Should return unified schema with "unknown" status (matching Anthropic)
    assert result["id"] == ""
    assert result["status"] == "unknown"
    assert result["title"] == ""
    assert result["usage"] == {"input_tokens": 0, "output_tokens": 0}


def test_empty_session_local_none_id():
    """Test LocalManagedAgent.retrieve_session normalizes None session id to empty string."""
    from praisonai.integrations.managed_local import LocalManagedAgent

    agent = LocalManagedAgent()
    agent._session_id = None
    agent.total_input_tokens = 0
    agent.total_output_tokens = 0

    result = agent.retrieve_session()

    assert result["id"] == ""
    assert result["status"] == "none"


if __name__ == "__main__":
    pytest.main([__file__])
