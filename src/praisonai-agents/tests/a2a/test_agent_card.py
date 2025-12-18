"""
Tests for A2A Agent Card Generation

TDD: Write tests first, then implement agent_card module.
"""

import json


class TestAgentCardGeneration:
    """Tests for generating Agent Card from PraisonAI Agent."""
    
    def test_generate_agent_card_basic(self):
        """Test generating Agent Card from basic Agent."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(
            name="Test Agent",
            role="Test Role",
            goal="Test Goal"
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        assert card.name == "Test Agent"
        assert card.url == "http://localhost:8000/a2a"
        assert card.version == "1.0.0"
    
    def test_generate_agent_card_with_description(self):
        """Test Agent Card includes description from role."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(
            name="Research Agent",
            role="Research Analyst",
            goal="Research topics thoroughly"
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        assert card.description is not None
        assert "Research" in card.description
    
    def test_generate_agent_card_with_instructions(self):
        """Test Agent Card from Agent with instructions."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(
            instructions="You are a helpful assistant that answers questions."
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        assert card.name is not None
        assert card.description is not None
    
    def test_generate_agent_card_capabilities(self):
        """Test Agent Card has correct capabilities."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(name="Test", role="Tester", goal="Test")
        
        card = generate_agent_card(
            agent, 
            url="http://localhost:8000/a2a",
            streaming=True
        )
        
        assert card.capabilities.streaming is True


class TestSkillsExtraction:
    """Tests for extracting skills from Agent tools."""
    
    def test_extract_skills_from_function(self):
        """Test extracting skill from a function tool."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        def search_web(query: str) -> str:
            """Search the web for information."""
            return f"Results for: {query}"
        
        agent = Agent(
            name="Search Agent",
            role="Searcher",
            goal="Search the web",
            tools=[search_web]
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        assert card.skills is not None
        assert len(card.skills) >= 1
        
        skill_names = [s.name for s in card.skills]
        assert "search_web" in skill_names
    
    def test_extract_skills_with_description(self):
        """Test skill description comes from function docstring."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        def calculate(expression: str) -> str:
            """Calculate a mathematical expression."""
            return str(eval(expression))
        
        agent = Agent(
            name="Calculator",
            role="Math Helper",
            goal="Do math",
            tools=[calculate]
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        calc_skill = next((s for s in card.skills if s.name == "calculate"), None)
        assert calc_skill is not None
        assert "mathematical" in calc_skill.description.lower()
    
    def test_extract_skills_multiple_tools(self):
        """Test extracting skills from multiple tools."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        def tool_one(x: str) -> str:
            """First tool."""
            return x
        
        def tool_two(y: str) -> str:
            """Second tool."""
            return y
        
        agent = Agent(
            name="Multi Tool Agent",
            role="Helper",
            goal="Help",
            tools=[tool_one, tool_two]
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        assert len(card.skills) >= 2
    
    def test_no_skills_when_no_tools(self):
        """Test Agent Card with no tools has empty skills."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(
            name="Simple Agent",
            role="Helper",
            goal="Help"
        )
        
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        # Skills should be None or empty list
        assert card.skills is None or len(card.skills) == 0


class TestAgentCardSerialization:
    """Tests for Agent Card JSON serialization."""
    
    def test_agent_card_to_json(self):
        """Test Agent Card can be serialized to JSON."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(name="Test", role="Tester", goal="Test")
        card = generate_agent_card(agent, url="http://localhost:8000/a2a")
        
        json_str = card.model_dump_json()
        data = json.loads(json_str)
        
        assert "name" in data
        assert "url" in data
        assert "capabilities" in data
    
    def test_agent_card_camel_case_keys(self):
        """Test Agent Card JSON uses camelCase keys."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a.agent_card import generate_agent_card
        
        agent = Agent(name="Test", role="Tester", goal="Test")
        card = generate_agent_card(
            agent, 
            url="http://localhost:8000/a2a",
            streaming=True
        )
        
        # Use by_alias to get camelCase
        data = card.model_dump(by_alias=True)
        
        # Check capabilities uses camelCase
        assert "pushNotifications" in data["capabilities"]
