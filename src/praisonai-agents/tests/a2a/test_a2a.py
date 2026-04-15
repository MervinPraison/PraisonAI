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

def _make_app(**kwargs):
    """Create a test FastAPI app with mocked agent."""
    from fastapi import FastAPI
    from praisonaiagents import Agent
    from praisonaiagents.ui.a2a import A2A
    
    agent = Agent(name="JSON-RPC Test", role="Tester", goal="Test")
    a2a = A2A(agent=agent, url="http://localhost:8000/a2a", **kwargs)
    
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


# ============================================================================
# GAP 1: tasks/list Tests
# ============================================================================

class TestA2ATasksList:
    """GAP 1: Tests for tasks/list JSON-RPC method."""
    
    def test_tasks_list_empty(self):
        """tasks/list with no tasks → empty list."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/list",
            "id": "list-1",
            "params": {}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "list-1"
        assert data["result"] == []
    
    def test_tasks_list_returns_tasks(self):
        """tasks/list after creating tasks → returns all tasks."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(return_value="OK")
        client = TestClient(app)
        
        # Create two tasks
        for i in range(2):
            client.post("/a2a", json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": f"send-{i}",
                "params": {
                    "message": {
                        "messageId": f"m{i}",
                        "role": "user",
                        "parts": [{"text": f"Task {i}"}]
                    }
                }
            })
        
        # List all tasks
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/list",
            "id": "list-2",
            "params": {}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) == 2
    
    def test_tasks_list_filter_by_context_id(self):
        """tasks/list with contextId filter → returns only matching tasks."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app()
        a2a.agent.chat = MagicMock(return_value="OK")
        client = TestClient(app)
        
        # Create task with contextId
        client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "send-ctx",
            "params": {
                "message": {
                    "messageId": "m-ctx",
                    "role": "user",
                    "parts": [{"text": "With context"}],
                    "contextId": "ctx-123"
                }
            }
        })
        
        # Create task without contextId
        client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": "send-no-ctx",
            "params": {
                "message": {
                    "messageId": "m-no-ctx",
                    "role": "user",
                    "parts": [{"text": "No context"}]
                }
            }
        })
        
        # List with context filter
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/list",
            "id": "list-ctx",
            "params": {"contextId": "ctx-123"}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) == 1
        assert data["result"][0]["contextId"] == "ctx-123"


# ============================================================================
# GAP 2: SecurityScheme Tests
# ============================================================================

class TestA2ASecurityScheme:
    """GAP 2: Tests for SecurityScheme types on AgentCard."""
    
    def test_security_scheme_types_exist(self):
        """SecurityScheme Pydantic models can be imported and instantiated."""
        from praisonaiagents.ui.a2a.types import (
            SecurityScheme, APIKeySecurityScheme, HTTPAuthSecurityScheme,
            OAuth2SecurityScheme, OpenIdConnectSecurityScheme,
            MutualTLSSecurityScheme, OAuthFlows,
        )
        
        # API Key
        api_key = APIKeySecurityScheme(name="X-API-Key", location="header")
        assert api_key.name == "X-API-Key"
        assert api_key.location == "header"
        
        # HTTP Bearer
        http = HTTPAuthSecurityScheme(scheme="bearer", bearer_format="JWT")
        assert http.scheme == "bearer"
        assert http.bearer_format == "JWT"
        
        # OAuth2
        flows = OAuthFlows(authorization_code={"authorizationUrl": "https://example.com/auth", "tokenUrl": "https://example.com/token", "scopes": {}})
        oauth2 = OAuth2SecurityScheme(flows=flows)
        assert oauth2.flows.authorization_code is not None
        
        # OpenID Connect
        oidc = OpenIdConnectSecurityScheme(open_id_connect_url="https://example.com/.well-known/openid-configuration")
        assert oidc.open_id_connect_url == "https://example.com/.well-known/openid-configuration"
        
        # Mutual TLS
        mtls = MutualTLSSecurityScheme(description="mTLS auth")
        assert mtls.description == "mTLS auth"
        
        # Wrap in SecurityScheme
        scheme = SecurityScheme(http=http)
        assert scheme.http is not None
        assert scheme.api_key is None
    
    def test_agent_card_with_security_schemes(self):
        """AgentCard can include securitySchemes and security fields."""
        from praisonaiagents.ui.a2a.types import (
            AgentCard, AgentCapabilities, SecurityScheme, HTTPAuthSecurityScheme,
        )
        
        card = AgentCard(
            name="Test",
            url="http://localhost:8000",
            version="1.0.0",
            capabilities=AgentCapabilities(streaming=True),
            security_schemes={
                "bearer": SecurityScheme(
                    http=HTTPAuthSecurityScheme(scheme="bearer")
                )
            },
            security=[{"bearer": []}],
        )
        
        dumped = card.model_dump(by_alias=True, exclude_none=True)
        assert "securitySchemes" in dumped
        assert "bearer" in dumped["securitySchemes"]
        assert dumped["security"] == [{"bearer": []}]
    
    def test_auth_token_auto_populates_security(self):
        """A2A with auth_token → agent card advertises Bearer security."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app(auth_token="secret-token")
        client = TestClient(app)
        
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        data = response.json()
        
        assert "securitySchemes" in data
        assert "bearer" in data["securitySchemes"]
        assert data["securitySchemes"]["bearer"]["http"]["scheme"] == "bearer"
        assert data["security"] == [{"bearer": []}]
    
    def test_no_auth_no_security_schemes(self):
        """A2A without auth_token → no securitySchemes in agent card."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.get("/.well-known/agent.json")
        data = response.json()
        
        assert "securitySchemes" not in data


# ============================================================================
# GAP 3: GetExtendedAgentCard Tests
# ============================================================================

class TestA2AExtendedCard:
    """GAP 3: Tests for agent/getExtendedCard JSON-RPC method."""
    
    def test_get_extended_card_default(self):
        """agent/getExtendedCard without callback returns base card."""
        from fastapi.testclient import TestClient
        
        app, a2a = _make_app(auth_token="secret")
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "agent/getExtendedCard",
            "id": "ext-1",
            "params": {}
        }, headers={"Authorization": "Bearer secret"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["result"]["name"] == "JSON-RPC Test"
        assert data["result"]["capabilities"]["extendedAgentCard"] is True
    
    def test_get_extended_card_with_callback(self):
        """agent/getExtendedCard with callback returns customized card."""
        from fastapi.testclient import TestClient
        from praisonaiagents.ui.a2a.types import AgentCard, AgentSkill
        
        def extend_card(base_card):
            return base_card.model_copy(update={
                "skills": [AgentSkill(id="secret-skill", name="Secret", description="Hidden skill", tags=["hidden"])]
            })
        
        app, a2a = _make_app(auth_token="secret", extended_agent_card_callback=extend_card)
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "agent/getExtendedCard",
            "id": "ext-2",
            "params": {}
        }, headers={"Authorization": "Bearer secret"})
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]["skills"]) == 1
        assert data["result"]["skills"][0]["id"] == "secret-skill"
    
    def test_extended_card_requires_auth(self):
        """agent/getExtendedCard without auth → 401."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app(auth_token="secret")
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "agent/getExtendedCard",
            "id": "ext-3",
            "params": {}
        })
        
        assert response.status_code == 401
    
    def test_capabilities_advertises_extended_card(self):
        """AgentCard capabilities.extendedAgentCard=True when auth configured."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app(auth_token="secret")
        client = TestClient(app)
        
        response = client.get("/.well-known/agent.json")
        data = response.json()
        assert data["capabilities"]["extendedAgentCard"] is True


# ============================================================================
# GAP 4: A2AClient Tests
# ============================================================================

class TestA2AClient:
    """GAP 4: Tests for A2AClient."""
    
    def test_client_import(self):
        """A2AClient can be imported."""
        from praisonaiagents.ui.a2a.client import A2AClient
        client = A2AClient("http://localhost:9999")
        assert client.base_url == "http://localhost:9999"
        assert client.auth_token is None
    
    def test_client_with_auth(self):
        """A2AClient stores auth_token."""
        from praisonaiagents.ui.a2a.client import A2AClient
        client = A2AClient("http://localhost:9999", auth_token="tok")
        assert client.auth_token == "tok"
    
    def test_client_get_agent_card(self):
        """A2AClient.get_agent_card() fetches and parses card."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from praisonaiagents.ui.a2a.client import A2AClient
        
        card_data = {
            "name": "Test Agent",
            "url": "http://localhost:8000/a2a",
            "version": "1.0.0",
            "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": False},
        }
        
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value=card_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.closed = False
        
        client = A2AClient("http://localhost:8000")
        client._session = mock_session
        
        async def run():
            card = await client.get_agent_card()
            assert card.name == "Test Agent"
            assert card.version == "1.0.0"
        
        asyncio.get_event_loop().run_until_complete(run())
    
    def test_client_send_message(self):
        """A2AClient.send_message() sends JSON-RPC request."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from praisonaiagents.ui.a2a.client import A2AClient
        
        result_data = {
            "jsonrpc": "2.0",
            "id": "123",
            "result": {"id": "task-1", "status": {"state": "completed"}},
        }
        
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value=result_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.closed = False
        
        client = A2AClient("http://localhost:8000")
        client._session = mock_session
        
        async def run():
            result = await client.send_message("Hello!")
            assert result["result"]["id"] == "task-1"
            # Verify post was called with correct method
            call_kwargs = mock_session.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["method"] == "message/send"
        
        asyncio.get_event_loop().run_until_complete(run())
    
    def test_client_list_tasks(self):
        """A2AClient.list_tasks() sends correct JSON-RPC."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from praisonaiagents.ui.a2a.client import A2AClient
        
        result_data = {"jsonrpc": "2.0", "id": "x", "result": []}
        
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value=result_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.closed = False
        
        client = A2AClient("http://localhost:8000")
        client._session = mock_session
        
        async def run():
            result = await client.list_tasks(context_id="ctx-1")
            assert result["result"] == []
            call_kwargs = mock_session.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["method"] == "tasks/list"
            assert payload["params"]["contextId"] == "ctx-1"
        
        asyncio.get_event_loop().run_until_complete(run())


# ============================================================================
# GAP 5: return_immediately Tests
# ============================================================================

class TestA2AReturnImmediately:
    """GAP 5: Tests for return_immediately on message/send."""
    
    def test_return_immediately_returns_submitted(self):
        """message/send with return_immediately=true returns task in submitted state."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        
        app, a2a = _make_app()
        client = TestClient(app)
        
        with patch.object(a2a.agent, 'chat', return_value="Done"):
            response = client.post("/a2a", json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": "ri-1",
                "params": {
                    "message": {
                        "messageId": "m1",
                        "role": "user",
                        "parts": [{"text": "Hello"}]
                    },
                    "configuration": {
                        "returnImmediately": True
                    }
                }
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["status"]["state"] == "submitted"
    
    def test_return_immediately_false_waits(self):
        """message/send with return_immediately=false (default) returns completed task."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        
        app, a2a = _make_app()
        client = TestClient(app)
        
        with patch.object(a2a.agent, 'chat', return_value="Hello back"):
            response = client.post("/a2a", json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": "ri-2",
                "params": {
                    "message": {
                        "messageId": "m2",
                        "role": "user",
                        "parts": [{"text": "Hello"}]
                    }
                }
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["status"]["state"] == "completed"


# ============================================================================
# GAP 6: Push Notification Hooks Tests
# ============================================================================

class TestA2APushNotificationHooks:
    """GAP 6: Tests for push notification protocol hooks."""
    
    def test_push_notification_types_exist(self):
        """TaskPushNotificationConfig and AuthenticationInfo can be imported."""
        from praisonaiagents.ui.a2a.types import (
            TaskPushNotificationConfig, AuthenticationInfo,
        )
        
        auth = AuthenticationInfo(scheme="Bearer", credentials="tok123")
        assert auth.scheme == "Bearer"
        
        config = TaskPushNotificationConfig(
            url="https://example.com/notify",
            token="abc",
            authentication=auth,
        )
        assert config.url == "https://example.com/notify"
        dumped = config.model_dump(by_alias=True, exclude_none=True)
        assert "url" in dumped
    
    def test_push_notification_not_supported(self):
        """Push notification methods return error when not supported."""
        from fastapi.testclient import TestClient
        
        app, _ = _make_app()
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/pushNotificationConfig/set",
            "id": "pn-1",
            "params": {"taskId": "t1", "url": "https://example.com/hook"}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "not supported" in data["error"]["message"].lower()
    
    def test_push_notification_extensible(self):
        """A2A subclass can override _handle_push_notification."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from fastapi.responses import JSONResponse
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        
        class CustomA2A(A2A):
            def _handle_push_notification(self, request_id, method, params):
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"registered": True},
                })
        
        agent = Agent(name="PNTest", role="Tester", goal="Test")
        a2a = CustomA2A(agent=agent, url="http://localhost:8000/a2a")
        app = FastAPI()
        app.include_router(a2a.get_router())
        client = TestClient(app)
        
        response = client.post("/a2a", json={
            "jsonrpc": "2.0",
            "method": "tasks/pushNotificationConfig/set",
            "id": "pn-2",
            "params": {"taskId": "t1", "url": "https://example.com/hook"}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["registered"] is True
