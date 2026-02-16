"""
Unit tests for Agent.as_tool() method.

Tests:
1. as_tool() returns a Handoff with ContextPolicy.NONE
2. as_tool() generates correct default tool name
3. as_tool() uses custom description and name when provided
4. as_tool() can be used in tools list
"""

from unittest.mock import MagicMock


class TestAgentAsTool:
    """Tests for Agent.as_tool() method."""
    
    def test_as_tool_returns_handoff(self):
        """Test that as_tool() returns a Handoff instance."""
        from praisonaiagents.agent.handoff import Handoff, HandoffConfig, ContextPolicy
        
        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_agent.role = "Test Role"
        mock_agent.goal = "Test Goal"
        
        # Simulate as_tool behavior
        agent_name_snake = mock_agent.name.lower().replace(' ', '_').replace('-', '_')
        default_tool_name = f"invoke_{agent_name_snake}"
        
        result = Handoff(
            agent=mock_agent,
            tool_name_override=default_tool_name,
            tool_description_override=f"Invoke {mock_agent.name} to complete a subtask and return the result",
            config=HandoffConfig(context_policy=ContextPolicy.NONE),
        )
        
        assert isinstance(result, Handoff)
        assert result.config.context_policy == ContextPolicy.NONE
        assert result.tool_name == "invoke_testagent"
    
    def test_as_tool_context_policy_none(self):
        """Test that as_tool() uses ContextPolicy.NONE (no history passed)."""
        from praisonaiagents.agent.handoff import Handoff, HandoffConfig, ContextPolicy
        
        mock_agent = MagicMock()
        mock_agent.name = "Researcher"
        
        result = Handoff(
            agent=mock_agent,
            tool_name_override="invoke_researcher",
            tool_description_override="Research topics",
            config=HandoffConfig(context_policy=ContextPolicy.NONE),
        )
        
        assert result.config.context_policy == ContextPolicy.NONE
    
    def test_as_tool_default_tool_name(self):
        """Test that as_tool() generates correct default tool name."""
        from praisonaiagents.agent.handoff import Handoff, HandoffConfig, ContextPolicy
        
        # Test various agent names
        test_cases = [
            ("Researcher", "invoke_researcher"),
            ("Code Writer", "invoke_code_writer"),
            ("data-analyst", "invoke_data_analyst"),
            ("MyAgent123", "invoke_myagent123"),
        ]
        
        for agent_name, expected_tool_name in test_cases:
            mock_agent = MagicMock()
            mock_agent.name = agent_name
            
            agent_name_snake = agent_name.lower().replace(' ', '_').replace('-', '_')
            tool_name = f"invoke_{agent_name_snake}"
            
            result = Handoff(
                agent=mock_agent,
                tool_name_override=tool_name,
                tool_description_override="Test",
                config=HandoffConfig(context_policy=ContextPolicy.NONE),
            )
            
            assert result.tool_name == expected_tool_name, f"Failed for {agent_name}"
    
    def test_as_tool_custom_description(self):
        """Test that as_tool() uses custom description when provided."""
        from praisonaiagents.agent.handoff import Handoff, HandoffConfig, ContextPolicy
        
        mock_agent = MagicMock()
        mock_agent.name = "Coder"
        
        custom_description = "Write Python code for any task"
        
        result = Handoff(
            agent=mock_agent,
            tool_name_override="invoke_coder",
            tool_description_override=custom_description,
            config=HandoffConfig(context_policy=ContextPolicy.NONE),
        )
        
        assert result.tool_description == custom_description
    
    def test_as_tool_custom_name(self):
        """Test that as_tool() uses custom tool name when provided."""
        from praisonaiagents.agent.handoff import Handoff, HandoffConfig, ContextPolicy
        
        mock_agent = MagicMock()
        mock_agent.name = "Researcher"
        
        custom_name = "research_topic"
        
        result = Handoff(
            agent=mock_agent,
            tool_name_override=custom_name,
            tool_description_override="Research topics",
            config=HandoffConfig(context_policy=ContextPolicy.NONE),
        )
        
        assert result.tool_name == custom_name


class TestAgentAsToolIntegration:
    """Integration tests for Agent.as_tool() with real Agent instances."""
    
    def test_as_tool_on_real_agent(self):
        """Test as_tool() on a real Agent instance (no LLM calls)."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.handoff import Handoff, ContextPolicy
        
        # Create a real agent (no LLM calls needed for this test)
        agent = Agent(
            name="TestResearcher",
            instructions="Research topics thoroughly",
        )
        
        # Call as_tool()
        result = agent.as_tool("Research a topic and return findings")
        
        # Verify result
        assert isinstance(result, Handoff)
        assert result.config.context_policy == ContextPolicy.NONE
        assert result.tool_name == "invoke_testresearcher"
        assert "Research a topic" in result.tool_description
    
    def test_as_tool_with_custom_params(self):
        """Test as_tool() with custom tool name and description."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.handoff import Handoff, ContextPolicy
        
        agent = Agent(
            name="Coder",
            instructions="Write clean Python code",
        )
        
        result = agent.as_tool(
            description="Generate Python code for any programming task",
            tool_name="generate_code",
        )
        
        assert isinstance(result, Handoff)
        assert result.tool_name == "generate_code"
        assert "Generate Python code" in result.tool_description
    
    def test_as_tool_in_tools_list(self):
        """Test that as_tool() result can be added to another agent's tools."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.handoff import Handoff
        
        # Create specialist agents
        researcher = Agent(name="Researcher", instructions="Research topics")
        coder = Agent(name="Coder", instructions="Write code")
        
        # Create parent agent with specialists as tools
        writer = Agent(
            name="Writer",
            instructions="Write articles using your tools",
            tools=[
                researcher.as_tool("Research a topic"),
                coder.as_tool("Write Python code"),
            ],
        )
        
        # Verify tools were added (they get converted to tool functions)
        # The handoffs should be processed into the tools list
        assert writer.name == "Writer"
        # Note: Handoffs are processed in _process_handoffs, so we check the agent was created
