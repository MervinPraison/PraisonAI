"""
Test unified session info schema between managed agent backends.

Verifies that both AnthropicManagedAgent and LocalManagedAgent return
consistent session information with the same schema.
"""

import pytest
from unittest.mock import patch, Mock


def test_session_info_schema_consistency():
    """Test that both managed agents return identical session schema."""
    from praisonai.integrations.managed_agents import ManagedAgent
    from praisonai.integrations.managed_local import LocalManagedAgent
    from praisonai.integrations._session_info import SessionInfo
    
    # Create both backends
    managed = ManagedAgent()
    local = LocalManagedAgent()
    
    # Mock session data for both
    managed._session_id = "test_session_anthropic"
    local._session_id = "test_session_local"
    
    # Get session info from both
    with patch.object(managed, '_get_client') as mock_client:
        # Mock Anthropic API response
        mock_session = Mock()
        mock_session.id = "test_session_anthropic"
        mock_session.status = "active"
        mock_session.title = "Test Session"
        mock_usage = Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_session.usage = mock_usage
        
        mock_client.return_value.beta.sessions.retrieve.return_value = mock_session
        
        managed_info = managed.retrieve_session()
    
    local_info = local.retrieve_session()
    
    # Both should have exact same keys
    assert set(managed_info.keys()) == set(local_info.keys())
    
    # Required keys should be present
    required_keys = ["id", "status", "title", "usage"]
    for key in required_keys:
        assert key in managed_info
        assert key in local_info
    
    # Usage should have consistent structure
    usage_keys = ["input_tokens", "output_tokens"]
    for key in usage_keys:
        assert key in managed_info["usage"]
        assert key in local_info["usage"]
        assert isinstance(managed_info["usage"][key], int)
        assert isinstance(local_info["usage"][key], int)


def test_session_info_dataclass():
    """Test SessionInfo dataclass functionality."""
    from praisonai.integrations._session_info import SessionInfo, SessionUsage
    
    # Test default construction
    info = SessionInfo()
    assert info.id == ""
    assert info.status == "unknown"
    assert info.title == ""
    assert info.usage.input_tokens == 0
    assert info.usage.output_tokens == 0
    
    # Test with data
    usage = SessionUsage(input_tokens=100, output_tokens=50)
    info = SessionInfo(
        id="test_session",
        status="active", 
        title="Test Session",
        usage=usage
    )
    
    # Test to_dict
    data = info.to_dict()
    expected = {
        "id": "test_session",
        "status": "active",
        "title": "Test Session", 
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        }
    }
    assert data == expected
    
    # Test from_dict
    reconstructed = SessionInfo.from_dict(data)
    assert reconstructed.id == info.id
    assert reconstructed.status == info.status
    assert reconstructed.title == info.title
    assert reconstructed.usage.input_tokens == info.usage.input_tokens
    assert reconstructed.usage.output_tokens == info.usage.output_tokens


def test_session_info_backward_compatibility():
    """Test that SessionInfo handles missing fields gracefully."""
    from praisonai.integrations._session_info import SessionInfo
    
    # Test partial data (old format)
    partial_data = {
        "id": "test_session",
        "status": "active"
        # Missing title and usage
    }
    
    info = SessionInfo.from_dict(partial_data)
    assert info.id == "test_session"
    assert info.status == "active"
    assert info.title == ""  # Default
    assert info.usage.input_tokens == 0  # Default
    assert info.usage.output_tokens == 0  # Default
    
    # Test empty data
    info = SessionInfo.from_dict({})
    data = info.to_dict()
    
    # Should have all required keys with defaults
    required_keys = ["id", "status", "title", "usage"]
    for key in required_keys:
        assert key in data


def test_managed_backend_protocol_re_export():
    """Test that ManagedBackendProtocol can be imported from managed module."""
    # Test lazy import works
    from praisonaiagents.managed import ManagedBackendProtocol
    assert ManagedBackendProtocol is not None
    
    # Test it's the same as the original
    from praisonaiagents.agent.protocols import ManagedBackendProtocol as OriginalProtocol
    assert ManagedBackendProtocol is OriginalProtocol