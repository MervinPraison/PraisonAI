"""Unit tests for n8n agent invoke API endpoint."""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock


class TestAgentInvokeAPI:
    """Test the agent invoke API endpoint for n8n integration."""
    
    def test_import_agent_invoke(self):
        """Test that agent invoke module can be imported."""
        try:
            from praisonai.api.agent_invoke import (
                register_agent, 
                get_agent, 
                unregister_agent,
                list_registered_agents,
                invoke_agent_standalone
            )
            assert callable(register_agent)
            assert callable(get_agent)
            assert callable(unregister_agent)
            assert callable(list_registered_agents)
            assert callable(invoke_agent_standalone)
        except ImportError as e:
            pytest.fail(f"Failed to import agent invoke module: {e}")
    
    def test_agent_registry_operations(self):
        """Test agent registration and retrieval."""
        from praisonai.api.agent_invoke import (
            register_agent, 
            get_agent, 
            unregister_agent,
            list_registered_agents
        )
        
        # Create mock agent
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.start.return_value = "Test response"
        
        # Test registration
        register_agent("test-agent", mock_agent)
        assert get_agent("test-agent") == mock_agent
        assert "test-agent" in list_registered_agents()
        
        # Test retrieval
        retrieved_agent = get_agent("test-agent")
        assert retrieved_agent == mock_agent
        
        # Test unregistration
        success = unregister_agent("test-agent")
        assert success is True
        assert get_agent("test-agent") is None
        assert "test-agent" not in list_registered_agents()
        
        # Test unregistering non-existent agent
        success = unregister_agent("non-existent")
        assert success is False
    
    @pytest.mark.asyncio
    async def test_invoke_agent_standalone_sync(self):
        """Test standalone agent invocation with sync agent."""
        from praisonai.api.agent_invoke import (
            register_agent,
            invoke_agent_standalone,
            unregister_agent
        )
        
        # Create mock sync agent
        mock_agent = Mock()
        mock_agent.start.return_value = "Hello from sync agent!"
        
        # Register agent
        register_agent("sync-agent", mock_agent)
        
        try:
            # Test invocation
            result = await invoke_agent_standalone(
                agent_id="sync-agent",
                message="Hello agent",
                session_id="test-session"
            )
            
            assert result["status"] == "success"
            assert result["result"] == "Hello from sync agent!"
            assert result["session_id"] == "test-session"
            assert result["agent_id"] == "sync-agent"
            
            # Verify agent was called correctly
            mock_agent.start.assert_called_once_with("Hello agent")
            
        finally:
            unregister_agent("sync-agent")
    
    @pytest.mark.asyncio
    async def test_invoke_agent_standalone_async(self):
        """Test standalone agent invocation with async agent."""
        from praisonai.api.agent_invoke import (
            register_agent,
            invoke_agent_standalone,
            unregister_agent
        )
        
        # Create mock async agent
        mock_agent = Mock()
        mock_agent.astart = AsyncMock(return_value="Hello from async agent!")
        
        # Register agent
        register_agent("async-agent", mock_agent)
        
        try:
            # Test invocation
            result = await invoke_agent_standalone(
                agent_id="async-agent",
                message="Hello async agent",
                session_id="async-session"
            )
            
            assert result["status"] == "success"
            assert result["result"] == "Hello from async agent!"
            assert result["session_id"] == "async-session"
            assert result["agent_id"] == "async-agent"
            
            # Verify agent was called correctly
            mock_agent.astart.assert_called_once_with("Hello async agent")
            
        finally:
            unregister_agent("async-agent")
    
    @pytest.mark.asyncio
    async def test_invoke_agent_standalone_not_found(self):
        """Test standalone invocation with non-existent agent."""
        from praisonai.api.agent_invoke import invoke_agent_standalone
        
        result = await invoke_agent_standalone(
            agent_id="non-existent",
            message="Hello"
        )
        
        assert result["status"] == "error"
        assert "not found" in result["error"]
        assert "available_agents" in result
    
    @pytest.mark.asyncio
    async def test_invoke_agent_standalone_error(self):
        """Test standalone invocation with agent that raises an exception."""
        from praisonai.api.agent_invoke import (
            register_agent,
            invoke_agent_standalone,
            unregister_agent
        )
        
        # Create mock agent that raises an exception
        mock_agent = Mock()
        mock_agent.start.side_effect = Exception("Agent error")
        
        # Register agent
        register_agent("error-agent", mock_agent)
        
        try:
            # Test invocation
            result = await invoke_agent_standalone(
                agent_id="error-agent",
                message="Hello"
            )
            
            assert result["status"] == "error"
            assert "Agent error" in result["error"]
            assert result["agent_id"] == "error-agent"
            
        finally:
            unregister_agent("error-agent")


@pytest.mark.skipif(not pytest.importorskip("fastapi", minversion="0.68.0"), reason="FastAPI not available")
class TestAgentInvokeFastAPI:
    """Test the FastAPI agent invoke endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client for the agent invoke API."""
        try:
            from fastapi.testclient import TestClient
            from praisonai.api.agent_invoke import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            return TestClient(app)
        except (ImportError, RuntimeError):
            pytest.skip("FastAPI test dependencies not available")
    
    def test_list_agents_endpoint(self, client):
        """Test the list agents endpoint."""
        from praisonai.api.agent_invoke import register_agent, unregister_agent
        
        # Register test agent
        mock_agent = Mock()
        register_agent("test-agent", mock_agent)
        
        try:
            # Test endpoint
            response = client.get("/api/v1/agents")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "success"
            assert "test-agent" in data["agents"]
            assert data["count"] >= 1
            
        finally:
            unregister_agent("test-agent")
    
    def test_get_agent_info_endpoint(self, client):
        """Test the get agent info endpoint."""
        from praisonai.api.agent_invoke import register_agent, unregister_agent
        
        # Create mock agent with attributes
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        mock_agent.instructions = "You are a test agent for unit testing."
        mock_agent.tools = [Mock(), Mock()]  # Two mock tools
        
        register_agent("info-agent", mock_agent)
        
        try:
            # Test endpoint
            response = client.get("/api/v1/agents/info-agent")
            assert response.status_code == 200
            
            data = response.json()
            assert data["agent_id"] == "info-agent"
            assert data["name"] == "Test Agent"
            assert data["status"] == "registered"
            assert "instructions" in data
            assert "tools" in data
            
        finally:
            unregister_agent("info-agent")
    
    def test_get_agent_info_not_found(self, client):
        """Test get agent info for non-existent agent."""
        response = client.get("/api/v1/agents/non-existent")
        assert response.status_code == 404
        
        data = response.json()
        assert "not found" in data["detail"]
    
    def test_invoke_agent_endpoint_sync(self, client):
        """Test the invoke agent endpoint with sync agent."""
        from praisonai.api.agent_invoke import register_agent, unregister_agent
        
        # Create mock sync agent
        mock_agent = Mock()
        mock_agent.start.return_value = "Hello from endpoint!"
        
        register_agent("endpoint-agent", mock_agent)
        
        try:
            # Test endpoint
            response = client.post(
                "/api/v1/agents/endpoint-agent/invoke",
                json={
                    "message": "Hello endpoint",
                    "session_id": "endpoint-session"
                }
            )
            
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "success"
            assert data["result"] == "Hello from endpoint!"
            assert data["session_id"] == "endpoint-session"
            assert "metadata" in data
            
            # Verify agent was called
            mock_agent.start.assert_called_once_with("Hello endpoint")
            
        finally:
            unregister_agent("endpoint-agent")
    
    def test_invoke_agent_endpoint_not_found(self, client):
        """Test invoke endpoint with non-existent agent."""
        response = client.post(
            "/api/v1/agents/non-existent/invoke",
            json={"message": "Hello"}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]
    
    def test_invoke_agent_endpoint_missing_message(self, client):
        """Test invoke endpoint with missing message."""
        from praisonai.api.agent_invoke import register_agent, unregister_agent
        
        mock_agent = Mock()
        register_agent("message-test", mock_agent)
        
        try:
            # Test with missing message field
            response = client.post(
                "/api/v1/agents/message-test/invoke",
                json={}
            )
            
            assert response.status_code == 422  # Validation error
            
        finally:
            unregister_agent("message-test")
    
    def test_unregister_agent_endpoint(self, client):
        """Test the unregister agent endpoint."""
        from praisonai.api.agent_invoke import register_agent
        
        # Register agent
        mock_agent = Mock()
        register_agent("unregister-test", mock_agent)
        
        # Test unregistration
        response = client.delete("/api/v1/agents/unregister-test")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "unregistered successfully" in data["message"]
        
        # Test unregistering again (should fail)
        response = client.delete("/api/v1/agents/unregister-test")
        assert response.status_code == 404


def test_agent_invoke_smoke_test():
    """Smoke test to verify agent invoke module can be imported and used."""
    try:
        from praisonai.api.agent_invoke import (
            register_agent,
            get_agent,
            list_registered_agents,
            AgentInvokeRequest,
            AgentInvokeResponse,
            ErrorResponse
        )
        
        # Test that classes can be instantiated
        if AgentInvokeRequest is not object:  # Only if Pydantic is available
            request = AgentInvokeRequest(message="test")
            assert request.message == "test"
            assert request.session_id is None
        
        # Test basic registry functions
        assert callable(register_agent)
        assert callable(get_agent)
        assert isinstance(list_registered_agents(), list)
        
    except Exception as e:
        pytest.fail(f"Agent invoke smoke test failed: {e}")


if __name__ == "__main__":
    # Run smoke test when executed directly
    test_agent_invoke_smoke_test()
    print("✅ Agent invoke API smoke test passed")
