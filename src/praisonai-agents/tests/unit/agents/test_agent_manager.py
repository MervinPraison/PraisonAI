"""
Tests for AgentManager rename (Agents → AgentManager).

TDD: These tests define the expected behavior for the API consolidation.
"""
import pytest
import warnings


class TestAgentManagerRename:
    """Test that AgentManager is the primary class and Agents is deprecated alias."""
    
    def test_agent_manager_importable(self):
        """AgentManager should be importable from praisonaiagents."""
        from praisonaiagents import AgentManager
        assert AgentManager is not None
    
    def test_agents_still_importable(self):
        """Agents should still be importable for backward compatibility."""
        from praisonaiagents import Agents
        assert Agents is not None
    
    def test_agent_manager_is_agents(self):
        """AgentManager and Agents should be the same class."""
        from praisonaiagents import AgentManager, Agents
        assert AgentManager is Agents
    
    def test_agents_emits_deprecation_warning(self):
        """Importing Agents should emit a DeprecationWarning."""
        # Clear any cached imports
        import sys
        # Remove from cache to trigger fresh import
        modules_to_remove = [k for k in sys.modules.keys() if 'praisonaiagents' in k]
        for mod in modules_to_remove:
            del sys.modules[mod]
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Import fresh
            import praisonaiagents
            # Access Agents to trigger lazy loading
            _ = praisonaiagents.Agents
            
            # Check for deprecation warning
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            agents_warnings = [x for x in deprecation_warnings if 'Agents' in str(x.message)]
            assert len(agents_warnings) >= 1, f"Expected deprecation warning for Agents, got: {[str(x.message) for x in w]}"
    
    def test_agent_manager_no_deprecation_warning(self):
        """Importing AgentManager should NOT emit a deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import AgentManager
            _ = AgentManager  # Use it
            
            # Check no deprecation warning for AgentManager
            agent_manager_warnings = [x for x in w if 'AgentManager' in str(x.message) and issubclass(x.category, DeprecationWarning)]
            assert len(agent_manager_warnings) == 0, f"Unexpected deprecation warning for AgentManager: {agent_manager_warnings}"
    
    def test_agent_manager_in_all(self):
        """AgentManager should be in __all__ for IDE autocomplete."""
        import praisonaiagents
        assert 'AgentManager' in praisonaiagents.__all__
    
    def test_agent_manager_class_name(self):
        """The class should be named AgentManager."""
        from praisonaiagents import AgentManager
        assert AgentManager.__name__ == 'AgentManager'


class TestAgentManagerFunctionality:
    """Test that AgentManager works correctly with agents and tasks."""
    
    def test_agent_manager_instantiation(self):
        """AgentManager should be instantiable with agents list."""
        from praisonaiagents import AgentManager, Agent
        
        agent = Agent(name="test", instructions="Test agent")
        manager = AgentManager(agents=[agent])
        
        assert manager is not None
        assert len(manager.agents) == 1
    
    def test_agents_alias_instantiation(self):
        """Agents alias should work identically to AgentManager."""
        from praisonaiagents import Agents, Agent
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Ignore deprecation for this test
            agent = Agent(name="test", instructions="Test agent")
            manager = Agents(agents=[agent])
            
            assert manager is not None
            assert len(manager.agents) == 1


class TestBackwardCompatibility:
    """Test backward compatibility with existing code patterns."""
    
    def test_from_agents_import_pattern(self):
        """Common import pattern should still work."""
        from praisonaiagents.agents import Agents
        assert Agents is not None
    
    def test_from_agents_import_agent_manager(self):
        """New import pattern should work."""
        from praisonaiagents.agents import AgentManager
        assert AgentManager is not None
    
    def test_praison_ai_agents_deprecated(self):
        """PraisonAIAgents should still work as deprecated alias."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonaiagents import PraisonAIAgents
            
            # Should emit deprecation warning
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
