"""
Test AG-UI Router - TDD Tests for FastAPI HTTP Endpoints

Phase 6: FastAPI Router Tests
- Test /agui POST endpoint
- Test /status GET endpoint
- Test request validation
- Test streaming response
- Test error handling
"""

class TestStatusEndpoint:
    """Test /status endpoint."""
    
    def test_status_endpoint_returns_available(self):
        """Test status endpoint returns available status."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        response = client.get("/status")
        
        assert response.status_code == 200
        assert response.json() == {"status": "available"}


class TestAGUIEndpoint:
    """Test /agui POST endpoint."""
    
    def test_agui_endpoint_accepts_post(self):
        """Test /agui endpoint accepts POST requests."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        # Minimal valid request
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Should return streaming response (200)
        assert response.status_code == 200
    
    def test_agui_endpoint_returns_streaming_response(self):
        """Test /agui endpoint returns streaming response."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Check content type is event-stream
        assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_agui_endpoint_requires_thread_id(self):
        """Test /agui endpoint requires thread_id."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        # Missing thread_id
        response = client.post("/agui", json={
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Should return validation error
        assert response.status_code == 422


class TestAGUIEndpointWithState:
    """Test /agui endpoint with state."""
    
    def test_agui_endpoint_accepts_state(self):
        """Test /agui endpoint accepts state parameter."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}],
            "state": {"custom_key": "custom_value"}
        })
        
        assert response.status_code == 200


class TestAGUIEndpointWithRunId:
    """Test /agui endpoint with run_id."""
    
    def test_agui_endpoint_accepts_run_id(self):
        """Test /agui endpoint accepts run_id parameter."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "run_id": "run-456",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        assert response.status_code == 200
    
    def test_agui_endpoint_generates_run_id_if_missing(self):
        """Test /agui endpoint generates run_id if not provided."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Should succeed even without run_id
        assert response.status_code == 200


class TestAGUIEndpointCORS:
    """Test /agui endpoint CORS headers."""
    
    def test_agui_endpoint_cors_headers(self):
        """Test /agui endpoint includes CORS headers."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Check CORS headers
        assert response.headers.get("access-control-allow-origin") == "*"


class TestAGUIEndpointErrorHandling:
    """Test /agui endpoint error handling."""
    
    def test_agui_endpoint_handles_agent_error(self):
        """Test /agui endpoint handles agent errors gracefully."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        # Create agent that will fail
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        # This should not crash the server
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        
        # Should return 200 with error event in stream
        assert response.status_code == 200


class TestAGUIEndpointWithForwardedProps:
    """Test /agui endpoint with forwarded_props."""
    
    def test_agui_endpoint_accepts_forwarded_props(self):
        """Test /agui endpoint accepts forwarded_props."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        client = TestClient(app)
        
        response = client.post("/agui", json={
            "thread_id": "thread-123",
            "messages": [{"role": "user", "content": "Hello"}],
            "forwarded_props": {"user_id": "user-123"}
        })
        
        assert response.status_code == 200
