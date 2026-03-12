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


# ============================================================================
# G11: AgentTeam Routing Tests
# ============================================================================

def _make_team_app():
    """Create test app with mocked AgentTeam (agents=)."""
    from fastapi import FastAPI
    from praisonaiagents.ui.a2a import A2A
    
    # Mock an AgentTeam with .start() method
    mock_team = MagicMock()
    mock_team.name = "Test Team"
    mock_team.start = MagicMock(return_value="Team result")
    
    a2a = A2A(agents=mock_team, name="Team A2A")
    
    app = FastAPI()
    app.include_router(a2a.get_router())
    
    return app, a2a, mock_team


class TestA2AAgentTeamRouting:
    """G11: Tests for AgentTeam routing via agents= param."""
    
    def test_a2a_agents_message_send(self):
        """message/send with agents= should call team.start()."""
        from fastapi.testclient import TestClient
        
        app, a2a, mock_team = _make_team_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "team-1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Research AI"}]
                }
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert data["result"]["status"]["state"] == "completed"
        # Verify team.start() was called, not agent.chat()
        mock_team.start.assert_called_once()
    
    def test_a2a_agents_message_stream(self):
        """message/stream with agents= should work."""
        from fastapi.testclient import TestClient
        
        app, a2a, mock_team = _make_team_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/stream",
            "id": "team-s1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Stream this"}]
                }
            }
        })
        
        assert response.status_code == 200
        text = response.text
        assert "event:" in text
    
    def test_a2a_agent_takes_priority(self):
        """When both agent= and agents= provided, agent takes priority."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Priority", role="Tester", goal="Test")
        mock_team = MagicMock()
        mock_team.name = "Team"
        
        a2a = A2A(agent=agent, agents=mock_team)
        a2a.agent.chat = MagicMock(return_value="Agent wins")
        
        app = FastAPI()
        app.include_router(a2a.get_router())
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "pri-1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Who responds?"}]
                }
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        # agent.chat should be called, not team.start
        a2a.agent.chat.assert_called_once()
        mock_team.start.assert_not_called()


# ============================================================================
# G9: serve() Convenience Tests
# ============================================================================

class TestA2AServe:
    """G9: Tests for A2A.serve() convenience method."""
    
    def test_a2a_serve_method_exists(self):
        """A2A should have a serve() method."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Serve", role="Helper", goal="Help")
        a2a = A2A(agent=agent)
        
        assert hasattr(a2a, 'serve')
        assert callable(a2a.serve)
    
    def test_a2a_serve_creates_app(self):
        """serve() should create a FastAPI app and call uvicorn.run."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        agent = Agent(name="Serve", role="Helper", goal="Help")
        a2a = A2A(agent=agent)
        
        with patch("uvicorn.run") as mock_run:
            a2a.serve(host="127.0.0.1", port=9999)
            mock_run.assert_called_once()
            # Verify the app passed to uvicorn is a FastAPI instance
            call_args = mock_run.call_args
            assert call_args[1].get("host") == "127.0.0.1"
            assert call_args[1].get("port") == 9999


# ============================================================================
# G8: Auth Token Tests
# ============================================================================

def _make_auth_app(auth_token=None):
    """Create test app with optional auth_token."""
    from fastapi import FastAPI
    from praisonaiagents import Agent
    from praisonaiagents.ui.a2a import A2A
    
    agent = Agent(name="Auth Test", role="Tester", goal="Test")
    a2a = A2A(agent=agent, auth_token=auth_token)
    
    app = FastAPI()
    app.include_router(a2a.get_router())
    
    return app, a2a


class TestA2AAuth:
    """G8: Tests for auth_token support."""
    
    def test_a2a_auth_valid_token(self):
        """Valid bearer token → 200."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_auth_app(auth_token="sk-secret")
        a2a.agent.chat = MagicMock(return_value="Authed")
        client = TestClient(app)
        
        response = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": "auth-1",
                "params": {
                    "message": {
                        "messageId": "m1",
                        "role": "user",
                        "parts": [{"text": "Hello"}]
                    }
                }
            },
            headers={"Authorization": "Bearer sk-secret"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
    
    def test_a2a_auth_invalid_token(self):
        """Wrong bearer token → 401."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_auth_app(auth_token="sk-secret")
        client = TestClient(app)
        
        response = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": "auth-2",
                "params": {
                    "message": {
                        "messageId": "m1",
                        "role": "user",
                        "parts": [{"text": "Hello"}]
                    }
                }
            },
            headers={"Authorization": "Bearer wrong-token"}
        )
        
        assert response.status_code == 401
    
    def test_a2a_auth_missing_header(self):
        """No Authorization header → 401."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_auth_app(auth_token="sk-secret")
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "auth-3",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hello"}]
                }
            }
        })
        
        assert response.status_code == 401
    
    def test_a2a_no_auth_configured(self):
        """No auth_token set → open access (200)."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_auth_app(auth_token=None)
        a2a.agent.chat = MagicMock(return_value="Open")
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "no-auth-1",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "user",
                    "parts": [{"text": "Hello"}]
                }
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
    
    def test_a2a_auth_on_discovery_endpoint(self):
        """Agent card endpoint should remain open even with auth."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_auth_app(auth_token="sk-secret")
        client = TestClient(app)
        
        # Discovery endpoints should be public per A2A spec
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200


# ============================================================================
# G13: Part Conversion Tests
# ============================================================================

class TestA2APartConversion:
    """G13: Tests for url/data part handling in _parse_message and conversion."""
    
    def test_parse_message_with_url_part(self):
        """Parts with 'url' field should be parsed."""
        from praisonaiagents.ui.a2a.a2a import _parse_message
        
        msg = _parse_message({
            "messageId": "m1",
            "role": "user",
            "parts": [
                {"url": "https://example.com/img.png", "mediaType": "image/png"}
            ]
        })
        
        assert len(msg.parts) == 1
    
    def test_parse_message_with_data_part(self):
        """Parts with 'data' field should be parsed."""
        from praisonaiagents.ui.a2a.a2a import _parse_message
        
        msg = _parse_message({
            "messageId": "m1",
            "role": "user",
            "parts": [
                {"data": {"key": "value"}}
            ]
        })
        
        assert len(msg.parts) == 1
    
    def test_parse_message_mixed_parts(self):
        """Mixed text + url + data parts should all be parsed."""
        from praisonaiagents.ui.a2a.a2a import _parse_message
        
        msg = _parse_message({
            "messageId": "m1",
            "role": "user",
            "parts": [
                {"text": "Hello"},
                {"url": "https://example.com/doc.pdf", "mediaType": "application/pdf"},
                {"data": {"x": 1}}
            ]
        })
        
        assert len(msg.parts) == 3
    
    def test_conversion_url_part_to_openai(self):
        """FilePart with url should convert to OpenAI image_url format."""
        from praisonaiagents.ui.a2a.conversion import a2a_to_praisonai_messages
        from praisonaiagents.ui.a2a.types import Message, FilePart, Role
        
        msg = Message(
            message_id="m1",
            role=Role.USER,
            parts=[FilePart(file_uri="https://example.com/img.png", media_type="image/png")],
        )
        
        result = a2a_to_praisonai_messages([msg])
        assert len(result) == 1
        content = result[0]["content"]
        # Should contain image_url reference
        assert isinstance(content, list)
        assert any(p.get("type") == "image_url" for p in content)
    
    def test_conversion_data_part_to_openai(self):
        """DataPart should convert to text with JSON content."""
        from praisonaiagents.ui.a2a.conversion import a2a_to_praisonai_messages
        from praisonaiagents.ui.a2a.types import Message, DataPart, Role
        
        msg = Message(
            message_id="m1",
            role=Role.USER,
            parts=[DataPart(data={"key": "value"})],
        )
        
        result = a2a_to_praisonai_messages([msg])
        assert len(result) == 1
        content = result[0]["content"]
        assert isinstance(content, list)
        assert any("key" in str(p) for p in content)
    
    def test_extract_user_input_with_url_parts(self):
        """extract_user_input should handle non-text parts gracefully."""
        from praisonaiagents.ui.a2a.conversion import extract_user_input
        from praisonaiagents.ui.a2a.types import Message, FilePart, TextPart, Role
        
        msg = Message(
            message_id="m1",
            role=Role.USER,
            parts=[
                TextPart(text="Please analyze"),
                FilePart(file_uri="https://example.com/img.png"),
            ],
        )
        
        result = extract_user_input([msg])
        assert "analyze" in result
