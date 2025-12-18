"""
Tests for Main A2A Class

TDD: Write tests first, then implement A2A class.
"""


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
