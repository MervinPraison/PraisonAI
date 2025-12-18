"""
Test AGUI Class - TDD Tests for Main Interface Class

Phase 5: AGUI Class Tests
- Test AGUI initialization with Agent
- Test AGUI initialization with PraisonAIAgents
- Test get_router returns FastAPI router
- Test validation errors
"""


class TestAGUIInitialization:
    """Test AGUI class initialization."""
    
    def test_agui_init_with_agent(self):
        """Test AGUI initialization with single Agent."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        assert agui.agent == agent
        assert agui.agents is None
    
    def test_agui_init_with_agents(self):
        """Test AGUI initialization with PraisonAIAgents."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent, Task, PraisonAIAgents
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        task = Task(description="Test task", expected_output="Result", agent=agent)
        agents = PraisonAIAgents(agents=[agent], tasks=[task])
        
        agui = AGUI(agents=agents)
        
        assert agui.agents == agents
        assert agui.agent is None
    
    def test_agui_requires_agent_or_agents(self):
        """Test AGUI raises error if neither agent nor agents provided."""
        from praisonaiagents.ui.agui import AGUI
        import pytest
        
        with pytest.raises(ValueError, match="requires an agent or agents"):
            AGUI()
    
    def test_agui_custom_prefix(self):
        """Test AGUI with custom prefix."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent, prefix="/api/v1")
        
        assert agui.prefix == "/api/v1"
    
    def test_agui_custom_tags(self):
        """Test AGUI with custom tags."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent, tags=["Custom", "Tags"])
        
        assert agui.tags == ["Custom", "Tags"]
    
    def test_agui_default_tags(self):
        """Test AGUI default tags."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        assert agui.tags == ["AGUI"]


class TestAGUIRouter:
    """Test AGUI router generation."""
    
    def test_get_router_returns_api_router(self):
        """Test get_router returns FastAPI APIRouter."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import APIRouter
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        router = agui.get_router()
        
        assert isinstance(router, APIRouter)
    
    def test_router_has_agui_endpoint(self):
        """Test router has /agui POST endpoint."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        router = agui.get_router()
        
        # Check routes
        route_paths = [route.path for route in router.routes]
        assert "/agui" in route_paths
    
    def test_router_has_status_endpoint(self):
        """Test router has /status GET endpoint."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        router = agui.get_router()
        
        # Check routes
        route_paths = [route.path for route in router.routes]
        assert "/status" in route_paths
    
    def test_router_with_prefix(self):
        """Test router respects prefix."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent, prefix="/api/v1")
        
        router = agui.get_router()
        
        assert router.prefix == "/api/v1"


class TestAGUIIntegration:
    """Test AGUI integration with FastAPI."""
    
    def test_include_router_in_fastapi(self):
        """Test including AGUI router in FastAPI app."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        from fastapi import FastAPI
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        app = FastAPI()
        app.include_router(agui.get_router())
        
        # Check app has routes
        route_paths = [route.path for route in app.routes]
        assert "/agui" in route_paths
        assert "/status" in route_paths


class TestAGUIName:
    """Test AGUI name and description."""
    
    def test_agui_name(self):
        """Test AGUI name property."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent, name="My Agent")
        
        assert agui.name == "My Agent"
    
    def test_agui_description(self):
        """Test AGUI description property."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", role="Tester", goal="Test things")
        agui = AGUI(agent=agent, description="A test agent")
        
        assert agui.description == "A test agent"
    
    def test_agui_default_name_from_agent(self):
        """Test AGUI uses agent name by default."""
        from praisonaiagents.ui.agui import AGUI
        from praisonaiagents import Agent
        
        agent = Agent(name="TestAgent", role="Tester", goal="Test things")
        agui = AGUI(agent=agent)
        
        assert agui.name == "TestAgent"
