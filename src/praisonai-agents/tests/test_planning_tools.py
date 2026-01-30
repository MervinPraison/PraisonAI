"""
Test-Driven Development tests for Planning Mode with Tools Support.

This module contains tests for:
- PlanningAgent with tools parameter
- PlanningAgent with reasoning mode
- Agents with planning_tools parameter
- Research-enabled planning
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch, AsyncMock


# =============================================================================
# SECTION 1: PlanningAgent Tools Parameter Tests
# =============================================================================

class TestPlanningAgentToolsParameter:
    """Tests for PlanningAgent tools parameter."""
    
    def test_planning_agent_accepts_tools_parameter(self):
        """Test that PlanningAgent accepts tools parameter."""
        from praisonaiagents.planning import PlanningAgent
        
        def search_tool(query: str) -> str:
            """Search the web."""
            return f"Results for {query}"
        
        planner = PlanningAgent(tools=[search_tool])
        
        assert planner.tools is not None
        assert len(planner.tools) == 1
        
    def test_planning_agent_tools_default_empty(self):
        """Test that tools defaults to empty list."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent()
        
        assert planner.tools == []
        
    def test_planning_agent_with_multiple_tools(self):
        """Test PlanningAgent with multiple tools."""
        from praisonaiagents.planning import PlanningAgent
        
        def tool1(x: str) -> str:
            return x
        def tool2(x: str) -> str:
            return x
        def tool3(x: str) -> str:
            return x
        
        planner = PlanningAgent(tools=[tool1, tool2, tool3])
        
        assert len(planner.tools) == 3


# =============================================================================
# SECTION 2: PlanningAgent Internal Agent Tests
# =============================================================================

class TestPlanningAgentInternalAgent:
    """Tests for PlanningAgent internal Agent creation."""
    
    def test_planning_agent_creates_internal_agent_when_tools_provided(self):
        """Test that internal Agent is created when tools are provided."""
        from praisonaiagents.planning import PlanningAgent
        
        def search_tool(query: str) -> str:
            """Search the web."""
            return f"Results for {query}"
        
        planner = PlanningAgent(tools=[search_tool])
        
        # Internal agent should be created lazily
        agent = planner._get_agent()
        
        assert agent is not None
        assert agent.tools is not None
        
    def test_planning_agent_no_internal_agent_without_tools(self):
        """Test that no internal Agent is created without tools."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent()
        
        agent = planner._get_agent()
        
        assert agent is None
        
    def test_planning_agent_internal_agent_uses_planning_llm(self):
        """Test that internal Agent uses the planning LLM."""
        from praisonaiagents.planning import PlanningAgent
        
        def search_tool(query: str) -> str:
            return "results"
        
        planner = PlanningAgent(llm="gpt-4o", tools=[search_tool])
        agent = planner._get_agent()
        
        assert agent is not None
        # The agent should use the same LLM model
        assert agent.llm == "gpt-4o"


# =============================================================================
# SECTION 3: PlanningAgent Create Plan with Tools Tests
# =============================================================================

class TestPlanningAgentCreatePlanWithTools:
    """Tests for create_plan_sync with tools."""
    
    def test_create_plan_sync_uses_agent_when_tools_provided(self):
        """Test that create_plan_sync uses Agent.chat when tools provided."""
        from praisonaiagents.planning import PlanningAgent
        from praisonaiagents import Agent
        
        def search_tool(query: str) -> str:
            """Search the web for information."""
            return f"Search results for: {query}"
        
        planner = PlanningAgent(tools=[search_tool])
        
        # Mock the internal agent's chat method
        mock_agent = MagicMock()
        mock_agent.chat = MagicMock(return_value=json.dumps({
            "name": "Research Plan",
            "description": "Plan created with research",
            "steps": [
                {"description": "Research topic", "agent": "Researcher"},
                {"description": "Write content", "agent": "Writer"}
            ]
        }))
        mock_agent.tools = [search_tool]
        mock_agent.llm = "gpt-4o-mini"
        
        planner._agent = mock_agent
        
        agents = [Agent(name="Researcher", role="Researcher")]
        plan = planner.create_plan_sync(
            request="Research AI trends",
            agents=agents
        )
        
        # Verify agent.chat was called (not LLM.get_response)
        mock_agent.chat.assert_called_once()
        assert plan.name == "Research Plan"
        
    def test_create_plan_sync_uses_llm_when_no_tools(self):
        """Test that create_plan_sync uses LLM when no tools provided."""
        from praisonaiagents.planning import PlanningAgent
        from praisonaiagents import Agent
        
        planner = PlanningAgent()
        
        # Mock the LLM
        mock_llm = MagicMock()
        mock_llm.get_response = MagicMock(return_value=json.dumps({
            "name": "Simple Plan",
            "description": "Plan without research",
            "steps": [{"description": "Step 1"}]
        }))
        
        planner._llm = mock_llm
        
        agents = [Agent(name="Worker", role="Worker")]
        plan = planner.create_plan_sync(
            request="Simple task",
            agents=agents
        )
        
        # Verify LLM.get_response was called
        mock_llm.get_response.assert_called_once()
        assert plan.name == "Simple Plan"


# =============================================================================
# SECTION 4: Agents planning_tools Parameter Tests
# =============================================================================

class TestAgentsPlanningTools:
    """Tests for Agents planning_tools parameter."""
    
    def test_praisonaiagents_accepts_planning_tools(self):
        """Test that Agents accepts planning_tools parameter."""
        from praisonaiagents import Agent, Task, AgentManager
        
        def search_tool(query: str) -> str:
            return "results"
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(tools=[search_tool])
        )
        
        assert agents.planning_tools is not None
        assert len(agents.planning_tools) == 1
        
    def test_praisonaiagents_planning_tools_default_none(self):
        """Test that planning_tools defaults to None."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=True
        )
        
        assert agents.planning_tools is None
        
    def test_praisonaiagents_passes_tools_to_planning_agent(self):
        """Test that planning_tools are passed to PlanningAgent."""
        from praisonaiagents import Agent, Task, AgentManager
        
        def search_tool(query: str) -> str:
            return "results"
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(tools=[search_tool])
        )
        
        # Get the planning agent
        planning_agent = agents._get_planning_agent()
        
        assert planning_agent is not None
        assert planning_agent.tools is not None
        assert len(planning_agent.tools) == 1


# =============================================================================
# SECTION 5: PlanningAgent Reasoning Mode Tests
# =============================================================================

class TestPlanningAgentReasoningMode:
    """Tests for PlanningAgent reasoning mode."""
    
    def test_planning_agent_accepts_reasoning_parameter(self):
        """Test that PlanningAgent accepts reasoning parameter."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent(reasoning=True)
        
        assert planner.reasoning is True
        
    def test_planning_agent_reasoning_default_false(self):
        """Test that reasoning defaults to False."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent()
        
        assert planner.reasoning is False
        
    def test_planning_agent_accepts_max_reasoning_steps(self):
        """Test that PlanningAgent accepts max_reasoning_steps parameter."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent(reasoning=True, max_reasoning_steps=10)
        
        assert planner.max_reasoning_steps == 10
        
    def test_planning_agent_max_reasoning_steps_default(self):
        """Test that max_reasoning_steps defaults to 5."""
        from praisonaiagents.planning import PlanningAgent
        
        planner = PlanningAgent(reasoning=True)
        
        assert planner.max_reasoning_steps == 5


# =============================================================================
# SECTION 6: Agents planning_reasoning Parameter Tests
# =============================================================================

class TestAgentsPlanningReasoning:
    """Tests for Agents planning_reasoning parameter."""
    
    def test_praisonaiagents_accepts_planning_reasoning(self):
        """Test that Agents accepts planning_reasoning parameter."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(reasoning=True)
        )
        
        assert agents.planning_reasoning is True
        
    def test_praisonaiagents_planning_reasoning_default_false(self):
        """Test that planning_reasoning defaults to False."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=True
        )
        
        assert agents.planning_reasoning is False
        
    def test_praisonaiagents_passes_reasoning_to_planning_agent(self):
        """Test that planning_reasoning is passed to PlanningAgent."""
        from praisonaiagents import Agent, Task, AgentManager
        
        agent = Agent(name="Test", role="Tester")
        task = Task(description="Test task", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(reasoning=True)
        )
        
        planning_agent = agents._get_planning_agent()
        
        assert planning_agent.reasoning is True


# =============================================================================
# SECTION 7: Integration Tests
# =============================================================================

class TestPlanningToolsIntegration:
    """Integration tests for planning with tools."""
    
    def test_planning_with_tools_and_reasoning(self):
        """Test planning with both tools and reasoning enabled."""
        from praisonaiagents import Agent, Task, AgentManager
        
        def search_tool(query: str) -> str:
            return "search results"
        
        agent = Agent(name="Researcher", role="Research Analyst")
        task = Task(description="Research AI trends", agent=agent)
        
        from praisonaiagents.config import MultiAgentPlanningConfig
        agents = AgentManager(
            agents=[agent],
            tasks=[task],
            planning=MultiAgentPlanningConfig(
                tools=[search_tool],
                reasoning=True,
                auto_approve=True
            )
        )
        
        assert agents.planning is not None  # Planning config is set
        assert agents.planning_tools is not None
        assert agents.planning_reasoning is True
        
        planning_agent = agents._get_planning_agent()
        assert planning_agent.tools is not None
        assert planning_agent.reasoning is True


# =============================================================================
# SECTION 8: RESEARCH_TOOLS List Tests
# =============================================================================

class TestResearchToolsList:
    """Tests for RESEARCH_TOOLS list in planning module."""
    
    def test_research_tools_list_exists(self):
        """Test that RESEARCH_TOOLS list exists."""
        from praisonaiagents.planning import RESEARCH_TOOLS
        
        assert RESEARCH_TOOLS is not None
        assert isinstance(RESEARCH_TOOLS, list)
        
    def test_research_tools_contains_search_tools(self):
        """Test that RESEARCH_TOOLS contains common search tools."""
        from praisonaiagents.planning import RESEARCH_TOOLS
        
        expected_tools = [
            "web_search",
            "search_web",
            "duckduckgo_search",
        ]
        
        for tool in expected_tools:
            assert tool in RESEARCH_TOOLS, f"{tool} should be in RESEARCH_TOOLS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
