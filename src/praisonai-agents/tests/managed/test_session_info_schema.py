"""
Test unified retrieve_session schema between Anthropic and Local backends.

Ensures both backends return the same dict structure with all required fields.
"""

import pytest
from typing import Dict, Any, Optional
from unittest.mock import Mock, MagicMock


class TestSessionInfoSchema:
    """Test that all managed backends return consistent session info schema."""
    
    def test_session_info_dataclass_creation(self):
        """SessionInfo should create with defaults and convert to dict properly."""
        # Test we can import the dataclass
        from praisonai.integrations._session_info import SessionInfo, UsageInfo
        
        # Test default creation
        info = SessionInfo()
        assert info.id == ""
        assert info.status == "unknown"
        assert info.title == ""
        assert isinstance(info.usage, UsageInfo)
        assert info.usage.input_tokens == 0
        assert info.usage.output_tokens == 0
        
        # Test dict conversion
        data = info.to_dict()
        assert data == {
            "id": "",
            "status": "unknown", 
            "title": "",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        
    def test_session_info_with_data(self):
        """SessionInfo should handle real data properly."""
        from praisonai.integrations._session_info import SessionInfo, UsageInfo
        
        info = SessionInfo(
            id="sess_123",
            status="idle",
            title="Test Session",
            usage=UsageInfo(input_tokens=150, output_tokens=75),
        )
        
        data = info.to_dict()
        assert data == {
            "id": "sess_123",
            "status": "idle",
            "title": "Test Session", 
            "usage": {"input_tokens": 150, "output_tokens": 75},
        }
        
    def test_session_info_from_dict_conversion(self):
        """SessionInfo.from_dict should handle incomplete data gracefully."""
        from praisonai.integrations._session_info import SessionInfo
        
        # Test with complete data
        complete_data = {
            "id": "sess_456",
            "status": "running",
            "title": "Research Session",
            "usage": {"input_tokens": 200, "output_tokens": 100},
        }
        info = SessionInfo.from_dict(complete_data)
        assert info.id == "sess_456"
        assert info.status == "running"
        assert info.title == "Research Session"
        assert info.usage.input_tokens == 200
        assert info.usage.output_tokens == 100
        
        # Test with minimal data (like old format)
        minimal_data = {"id": "sess_789", "status": "idle"}
        info = SessionInfo.from_dict(minimal_data)
        assert info.id == "sess_789"
        assert info.status == "idle"
        assert info.title == ""  # Default
        assert info.usage.input_tokens == 0  # Default
        assert info.usage.output_tokens == 0  # Default
        
        # Test with None/empty data
        info = SessionInfo.from_dict(None)
        assert info.to_dict() == {
            "id": "",
            "status": "unknown",
            "title": "",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }


class TestManagedBackendSchemaEquality:
    """Test that both Anthropic and Local backends return identical schema."""
    
    def _mock_anthropic_session(self, has_usage: bool = True, has_title: bool = False):
        """Create a mock Anthropic session object."""
        mock_session = Mock()
        mock_session.id = "anthropic_sess_123"
        mock_session.status = "idle"
        
        if has_title:
            mock_session.title = "Anthropic Session"
        else:
            # Simulate missing title attribute
            del mock_session.title
            
        if has_usage:
            mock_usage = Mock()
            mock_usage.input_tokens = 100
            mock_usage.output_tokens = 50
            mock_session.usage = mock_usage
        else:
            # Simulate missing usage
            mock_session.usage = None
            
        return mock_session
    
    def test_anthropic_backend_schema(self):
        """AnthropicManagedAgent.retrieve_session should return unified schema."""
        from praisonai.integrations.managed_agents import AnthropicManagedAgent
        
        # Create backend with mocked client
        backend = AnthropicManagedAgent()
        backend._session_id = "test_session"
        
        # Mock the client and session
        mock_client = Mock()
        mock_session = self._mock_anthropic_session(has_usage=True, has_title=False)
        mock_client.beta.sessions.retrieve.return_value = mock_session
        backend._client = mock_client
        
        # Call retrieve_session
        result = backend.retrieve_session()
        
        # Verify unified schema
        assert isinstance(result, dict)
        assert "id" in result
        assert "status" in result 
        assert "title" in result
        assert "usage" in result
        assert isinstance(result["usage"], dict)
        assert "input_tokens" in result["usage"]
        assert "output_tokens" in result["usage"]
        
        # Verify actual values
        assert result["id"] == "anthropic_sess_123"
        assert result["status"] == "idle"
        assert result["title"] == ""  # Default since no title
        assert result["usage"]["input_tokens"] == 100
        assert result["usage"]["output_tokens"] == 50
        
    def test_local_backend_schema(self):
        """LocalManagedAgent.retrieve_session should return unified schema."""
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        # Create backend with session
        backend = LocalManagedAgent()
        backend._session_id = "local_sess_456"
        backend.total_input_tokens = 200
        backend.total_output_tokens = 150
        
        # Call retrieve_session
        result = backend.retrieve_session()
        
        # Verify unified schema
        assert isinstance(result, dict)
        assert "id" in result
        assert "status" in result
        assert "title" in result
        assert "usage" in result
        assert isinstance(result["usage"], dict)
        assert "input_tokens" in result["usage"]
        assert "output_tokens" in result["usage"]
        
        # Verify actual values
        assert result["id"] == "local_sess_456"
        assert result["status"] == "idle"
        assert result["title"] == ""  # Local doesn't have titles
        assert result["usage"]["input_tokens"] == 200
        assert result["usage"]["output_tokens"] == 150
        
    def test_schema_equality_between_backends(self):
        """Both backends should return dicts with identical structure."""
        from praisonai.integrations.managed_agents import AnthropicManagedAgent
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        # Setup Anthropic backend
        anthropic_backend = AnthropicManagedAgent()
        anthropic_backend._session_id = "anthropic_session"
        mock_client = Mock()
        mock_session = self._mock_anthropic_session(has_usage=True)
        mock_client.beta.sessions.retrieve.return_value = mock_session
        anthropic_backend._client = mock_client
        
        # Setup Local backend
        local_backend = LocalManagedAgent()
        local_backend._session_id = "local_session"
        local_backend.total_input_tokens = 100
        local_backend.total_output_tokens = 50
        
        # Get results
        anthropic_result = anthropic_backend.retrieve_session()
        local_result = local_backend.retrieve_session()
        
        # Both should have same keys
        assert set(anthropic_result.keys()) == set(local_result.keys())
        assert set(anthropic_result.keys()) == {"id", "status", "title", "usage"}
        
        # Both usage dicts should have same keys
        assert set(anthropic_result["usage"].keys()) == set(local_result["usage"].keys())
        assert set(anthropic_result["usage"].keys()) == {"input_tokens", "output_tokens"}
        
        # All values should be correct types
        for result in [anthropic_result, local_result]:
            assert isinstance(result["id"], str)
            assert isinstance(result["status"], str)
            assert isinstance(result["title"], str)
            assert isinstance(result["usage"], dict)
            assert isinstance(result["usage"]["input_tokens"], int)
            assert isinstance(result["usage"]["output_tokens"], int)
            
    def test_empty_session_handling(self):
        """Both backends should handle empty sessions consistently."""
        from praisonai.integrations.managed_agents import AnthropicManagedAgent
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        # Test Anthropic with no session
        anthropic_backend = AnthropicManagedAgent()
        anthropic_backend._session_id = None
        anthropic_result = anthropic_backend.retrieve_session()
        
        # Test Local with no session  
        local_backend = LocalManagedAgent()
        local_backend._session_id = None
        local_result = local_backend.retrieve_session()
        
        # Both should return same structure with defaults
        expected_keys = {"id", "status", "title", "usage"}
        assert set(anthropic_result.keys()) == expected_keys
        assert set(local_result.keys()) == expected_keys
        
        # Anthropic returns complete defaults
        assert anthropic_result["id"] == ""
        assert anthropic_result["status"] == "unknown"
        assert anthropic_result["title"] == ""
        assert anthropic_result["usage"]["input_tokens"] == 0
        assert anthropic_result["usage"]["output_tokens"] == 0
        
        # Local returns slightly different status
        assert local_result["id"] == ""
        assert local_result["status"] == "none"  # Different but still consistent format
        assert local_result["title"] == ""
        assert local_result["usage"]["input_tokens"] == 0
        assert local_result["usage"]["output_tokens"] == 0
        
    def test_backward_compatibility(self):
        """Old code accessing dict keys should still work."""
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        backend = LocalManagedAgent()
        backend._session_id = "compat_test"
        backend.total_input_tokens = 300
        backend.total_output_tokens = 200
        
        result = backend.retrieve_session()
        
        # Old code patterns should still work
        session_id = result["id"]  # ✅ Still works
        session_status = result["status"]  # ✅ Still works  
        input_tokens = result["usage"]["input_tokens"]  # ✅ Still works
        output_tokens = result["usage"]["output_tokens"]  # ✅ Still works
        
        # New fields are also available
        session_title = result["title"]  # ✅ New field (empty for local)
        
        assert session_id == "compat_test"
        assert session_status == "idle"
        assert input_tokens == 300
        assert output_tokens == 200
        assert session_title == ""