"""
Test for agent.name being None in multi-agent workflows.

Bug: When Agent is created with only instructions= and no name=,
self.name is set to None, causing TypeError in string join operations.

TDD: This test should FAIL before the fix and PASS after.
"""
import pytest
from unittest.mock import patch


class TestAgentNameNone:
    """Test cases for handling None agent names in multi-agent workflows."""
    
    def test_agent_with_instructions_only_has_none_name(self):
        """Verify the current behavior: instructions-only agent has name=None."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Research about AI")
        # This documents current behavior - name is None
        assert agent.name is None
    
    def test_agent_display_name_property_returns_fallback(self):
        """Agent should have a display_name property that never returns None."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Research about AI")
        # display_name should return a fallback when name is None
        assert hasattr(agent, 'display_name'), "Agent should have display_name property"
        assert agent.display_name is not None
        assert isinstance(agent.display_name, str)
        assert len(agent.display_name) > 0
    
    def test_agent_display_name_returns_name_when_set(self):
        """display_name should return the actual name when explicitly set."""
        from praisonaiagents import Agent
        
        agent = Agent(name="MyAgent", instructions="Research about AI")
        assert agent.name == "MyAgent"
        assert agent.display_name == "MyAgent"
    
    def test_multi_agent_workflow_with_instructions_only_agents(self):
        """Multi-agent workflow should not crash with instructions-only agents."""
        from praisonaiagents import Agent, AgentManager
        
        research_agent = Agent(instructions="Research about AI")
        summarise_agent = Agent(instructions="Summarise research agent's findings")
        
        # This should NOT raise TypeError
        agents = AgentManager(agents=[research_agent, summarise_agent])
        
        # The workflow should be able to display agent names
        agent_names = " → ".join([a.display_name for a in agents.agents])
        assert isinstance(agent_names, str)
        assert len(agent_names) > 0
    
    def test_agents_start_with_instructions_only_agents_no_crash(self):
        """Agents.start() should not crash with instructions-only agents."""
        from praisonaiagents import Agent, AgentManager
        
        research_agent = Agent(instructions="Research about AI")
        summarise_agent = Agent(instructions="Summarise findings")
        
        agents = AgentManager(agents=[research_agent, summarise_agent])
        
        # Mock the actual LLM call to avoid API calls in tests
        with patch.object(research_agent, 'chat', return_value="AI research findings"):
            with patch.object(summarise_agent, 'chat', return_value="Summary"):
                # This should NOT raise TypeError: sequence item 0: expected str instance, NoneType found
                try:
                    # We just need to verify it doesn't crash on the name join
                    # The actual execution may fail for other reasons in test env
                    _ = agents.start()
                except TypeError as e:
                    if "NoneType" in str(e) and "sequence item" in str(e):
                        pytest.fail(f"Agents.start() crashed due to None agent name: {e}")
                    # Other TypeErrors are acceptable in test environment
                except Exception:
                    # Other exceptions are acceptable - we're testing the name issue
                    pass


class TestUniqueDisplayNames:
    """Test unique display names for agents without explicit names."""
    
    def test_multiple_nameless_agents_have_unique_display_names(self):
        """Multiple agents with name=None should have unique display names."""
        from praisonaiagents import Agent
        
        agent1 = Agent(instructions="First agent")
        agent2 = Agent(instructions="Second agent")
        agent3 = Agent(instructions="Third agent")
        
        # All should have unique display names
        display_names = [agent1.display_name, agent2.display_name, agent3.display_name]
        assert len(set(display_names)) == 3, f"Display names should be unique: {display_names}"
    
    def test_nameless_agent_display_name_format(self):
        """Nameless agents should have display names like 'Agent 1', 'Agent 2'."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent")
        # Should match pattern "Agent N" where N is a number
        assert agent.display_name.startswith("Agent "), f"Expected 'Agent N' format, got: {agent.display_name}"
        # The part after "Agent " should be a number
        suffix = agent.display_name.replace("Agent ", "")
        assert suffix.isdigit(), f"Expected numeric suffix, got: {suffix}"
    
    def test_named_agent_keeps_explicit_name(self):
        """Agents with explicit names should use their name, not 'Agent N'."""
        from praisonaiagents import Agent
        
        agent = Agent(name="CustomAgent", instructions="Test")
        assert agent.display_name == "CustomAgent"
        assert agent.name == "CustomAgent"
    
    def test_multi_agent_workflow_shows_unique_names(self):
        """Multi-agent workflow should show unique names for nameless agents."""
        from praisonaiagents import Agent, AgentManager
        
        agent1 = Agent(instructions="Research")
        agent2 = Agent(instructions="Summarize")
        
        agents = AgentManager(agents=[agent1, agent2])
        agent_names = " → ".join([a.display_name for a in agents.agents])
        
        # Should not be "Agent → Agent"
        parts = agent_names.split(" → ")
        assert parts[0] != parts[1], f"Agent names should be unique: {agent_names}"


class TestAgentNameEdgeCases:
    """Edge cases for agent naming."""
    
    def test_agent_with_role_only_has_default_name(self):
        """Agent with role only should have default name 'Agent'."""
        from praisonaiagents import Agent
        
        agent = Agent(role="Researcher")
        assert agent.name == "Agent"
    
    def test_agent_with_empty_name_string(self):
        """Agent with empty string name should use the empty string."""
        from praisonaiagents import Agent
        
        agent = Agent(name="", instructions="Test")
        # Empty string is falsy, so it should be treated as no name
        # display_name should still return a fallback
        assert agent.display_name is not None
        assert len(agent.display_name) > 0
    
    def test_display_name_is_readonly(self):
        """display_name should be a computed property, not settable."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test")
        # Trying to set display_name should raise AttributeError
        with pytest.raises(AttributeError):
            agent.display_name = "NewName"
