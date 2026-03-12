"""
Tests for A2A Class and JSON-RPC Endpoints

TDD: Tests written first, then implementation.
"""

from unittest.mock import MagicMock, patch


# ============================================================================
# Existing Tests — A2A Class
# ============================================================================

class TestA2AClass:
    """Tests for A2A main class."""
    
    def test_a2a_creation_with_agent(self):
        """Test creating A2A with single agent."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Test", role="Tester", goal="Test")
        a2a = A2A(agent=agent)
        
        assert a2a.agent is not None
        assert a2a.name == "Test"
    
    def test_a2a_creation_with_custom_name(self):
        """Test creating A2A with custom name."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Test", role="Tester", goal="Test")
        a2a = A2A(agent=agent, name="Custom Name")
        
        assert a2a.name == "Custom Name"
    
    def test_a2a_requires_agent(self):
        """Test A2A requires agent or agents."""
        from praisonaiagents.ui.a2a import A2A
        import pytest
        
        with pytest.raises(ValueError):
            A2A()
    
    def test_a2a_get_agent_card(self):
        """Test getting Agent Card from A2A."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Card Test", role="Tester", goal="Test")
        a2a = A2A(agent=agent, url="http://localhost:8000/a2a")
        
        card = a2a.get_agent_card()
        
        assert card.name == "Card Test"
        assert card.url == "http://localhost:8000/a2a"
    
    def test_a2a_get_router(self):
        """Test getting FastAPI router from A2A."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Router Test", role="Tester", goal="Test")
        a2a = A2A(agent=agent)
        
        router = a2a.get_router()
        
        assert router is not None
        # Check router has routes
        assert len(router.routes) > 0


class TestA2ARouter:
    """Tests for A2A FastAPI router endpoints."""
    
    def test_agent_card_endpoint(self):
        """Test /.well-known/agent.json endpoint."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Endpoint Test", role="Tester", goal="Test")
        a2a = A2A(agent=agent, url="http://localhost:8000/a2a")
        
        app = FastAPI()
        app.include_router(a2a.get_router())
        
        client = TestClient(app)
        response = client.get("/.well-known/agent.json")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Endpoint Test"
    
    def test_status_endpoint(self):
        """Test /status endpoint."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Status Test", role="Tester", goal="Test")
        a2a = A2A(agent=agent)
        
        app = FastAPI()
        app.include_router(a2a.get_router())
        
        client = TestClient(app)
        response = client.get("/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestA2AWithTools:
    """Tests for A2A with agent tools."""
    
    def test_a2a_agent_card_includes_skills(self):
        """Test Agent Card includes skills from tools."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        def my_tool(x: str) -> str:
            """A test tool."""
            return x
        
        agent = Agent(
            name="Tool Agent",
            role="Helper",
            goal="Help",
            tools=[my_tool]
        )
        a2a = A2A(agent=agent, url="http://localhost:8000/a2a")
        
        card = a2a.get_agent_card()
        
        assert card.skills is not None
        assert len(card.skills) >= 1


# ============================================================================
# NEW: JSON-RPC Endpoint Tests
# ============================================================================

def _make_app():
    """Create a test FastAPI app with mocked agent."""
    from fastapi import FastAPI
    from praisonaiagents import Agent
    from praisonaiagents.ui.a2a import A2A
    
    agent = Agent(name="JSON-RPC Test", role="Tester", goal="Test")
    a2a = A2A(agent=agent, url="http://localhost:8000/a2a")
    
    app = FastAPI()
    app.include_router(a2a.get_router())
    
    return app, a2a


class TestA2AJsonRpc:
    """Tests for A2A JSON-RPC endpoint (POST /a2a)."""
    
    def test_post_a2a_invalid_jsonrpc(self):
        """Missing jsonrpc field → -32600 Invalid Request."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "method": "message/send",
            "id": "1",
            "params": {}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32600
    
    def test_post_a2a_unknown_method(self):
        """Unknown method → -32601 Method not found."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "unknown/method",
            "id": "1",
            "params": {}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601
    
    def test_post_a2a_message_send(self):
        """Valid message/send → Task result with completed status."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        # Mock agent.chat to avoid LLM call
        a2a.agent.chat = MagicMock(return_value="Hello from agent!")
        
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "req-1",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "user",
                    "parts": [{"text": "Hello"}]
                }
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "req-1"
        assert "result" in data
        result = data["result"]
        assert "id" in result
        assert result["status"]["state"] == "completed"
        assert result["artifacts"] is not None
        assert len(result["artifacts"]) > 0
    
    def test_post_a2a_message_send_creates_task_in_store(self):
        """message/send should create a task in TaskStore."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(return_value="OK")
        
        client = TestClient(app)
        
        # Store should be empty initially
        assert len(a2a.task_store.list_tasks()) == 0
        
        client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hi"}]
                }
            }
        })
        
        # Store should have one task
        assert len(a2a.task_store.list_tasks()) == 1
    
    def test_post_a2a_message_send_agent_error(self):
        """Agent throws → -32603 Internal error."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(side_effect=RuntimeError("LLM failed"))
        
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "err-1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hi"}]
                }
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        # Should return a task in failed state, not a JSON-RPC error
        assert "result" in data
        assert data["result"]["status"]["state"] == "failed"
    
    def test_post_a2a_tasks_get(self):
        """tasks/get → returns existing task."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(return_value="Done")
        
        client = TestClient(app)
        
        # First, create a task via message/send
        send_resp = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hi"}]
                }
            }
        })
        task_id = send_resp.json()["result"]["id"]
        
        # Now get the task
        get_resp = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "id": "2",
            "params": {"id": task_id}
        })
        
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "result" in data
        assert data["result"]["id"] == task_id
    
    def test_post_a2a_tasks_get_not_found(self):
        """tasks/get with nonexistent id → -32000 Task not found."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "id": "1",
            "params": {"id": "nonexistent"}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32000
    
    def test_post_a2a_tasks_cancel(self):
        """tasks/cancel → cancels existing task."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(return_value="Done")
        
        client = TestClient(app)
        
        # Create a task
        send_resp = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hi"}]
                }
            }
        })
        task_id = send_resp.json()["result"]["id"]
        
        # Cancel it
        cancel_resp = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/cancel",
            "id": "2",
            "params": {"id": task_id}
        })
        
        assert cancel_resp.status_code == 200
        data = cancel_resp.json()
        assert "result" in data
        assert data["result"]["status"]["state"] == "cancelled"
    
    def test_post_a2a_message_stream(self):
        """message/stream → returns SSE streaming response."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(return_value="Streamed response")
        
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/stream",
            "id": "stream-1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hello stream"}]
                }
            }
        })
        
        assert response.status_code == 200
        # SSE response should contain event data
        text = response.text
        assert "event:" in text
        assert "data:" in text
    
    def test_post_a2a_missing_params(self):
        """message/send without params.message → -32602 Invalid params."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "1",
            "params": {}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32602
