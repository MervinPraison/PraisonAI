"""
Unit tests for the context= parameter in Agent, Workflow, and Agents.

Tests cover:
- Parameter types (False, True, ManagerConfig, ContextManager)
- Lazy initialization (zero overhead when disabled)
- Precedence rules
- Multi-agent isolation
"""

import pytest
import time


class TestAgentContextParam:
    """Tests for Agent context= parameter."""
    
    def test_context_false_default(self):
        """context=False (default) should have zero overhead."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", context=False)
        
        # Should not initialize context manager
        assert agent._context_param is False
        assert agent._context_manager is None
        assert agent._context_manager_initialized is False
    
    def test_context_false_no_init_on_access(self):
        """Accessing context_manager when context=False should return None."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", context=False)
        
        # Access should return None without error
        assert agent.context_manager is None
        assert agent._context_manager_initialized is True
    
    def test_context_true_lazy_init(self):
        """context=True should lazy-init ContextManager on first access."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", context=True)
        
        # Not initialized until first access
        assert agent._context_param is True
        assert agent._context_manager_initialized is False
        
        # Access triggers initialization
        manager = agent.context_manager
        assert agent._context_manager_initialized is True
        assert manager is not None
    
    def test_context_manager_config(self):
        """context=ManagerConfig should use provided config."""
        from praisonaiagents import Agent
        from praisonaiagents.context import ManagerConfig
        
        config = ManagerConfig(
            auto_compact=False,
            compact_threshold=0.5,
            monitor_enabled=True,
        )
        agent = Agent(instructions="Test agent", context=config)
        
        manager = agent.context_manager
        assert manager is not None
        assert manager.config.auto_compact is False
        assert manager.config.compact_threshold == 0.5
        assert manager.config.monitor_enabled is True
    
    def test_context_manager_instance(self):
        """context=ContextManager should use provided instance directly."""
        from praisonaiagents import Agent
        from praisonaiagents.context import ContextManager
        
        custom_manager = ContextManager(model="gpt-4o")
        agent = Agent(instructions="Test agent", context=custom_manager)
        
        # Should use the exact same instance
        assert agent.context_manager is custom_manager
    
    def test_context_manager_setter(self):
        """context_manager setter should work correctly."""
        from praisonaiagents import Agent
        from praisonaiagents.context import ContextManager
        
        agent = Agent(instructions="Test agent", context=False)
        
        # Initially None
        assert agent.context_manager is None
        
        # Set a manager
        manager = ContextManager(model="gpt-4o-mini")
        agent.context_manager = manager
        
        assert agent.context_manager is manager
        assert agent._context_manager_initialized is True


class TestAgentContextPerformance:
    """Performance tests for context= parameter."""
    
    def test_context_false_init_overhead(self):
        """context=False should add minimal overhead to init."""
        from praisonaiagents import Agent
        
        # Warm up
        Agent(instructions="warmup", context=False)
        
        # Measure init time with context=False
        start = time.perf_counter()
        for _ in range(10):
            Agent(instructions="test", context=False)
        elapsed = time.perf_counter() - start
        
        # Should be very fast (< 50ms for 10 inits)
        assert elapsed < 0.5, f"Init too slow: {elapsed}s for 10 agents"
    
    def test_context_true_no_init_until_access(self):
        """context=True should not initialize manager until accessed."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", context=True)
        
        # Manager should not be initialized yet
        assert agent._context_manager is None
        assert agent._context_manager_initialized is False


class TestWorkflowContextParam:
    """Tests for Workflow context= parameter."""
    
    def test_workflow_context_false_default(self):
        """Workflow context=True should be the default (enabled for overflow prevention)."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(name="Test", steps=[])
        
        # Changed from False to True to enable context management by default for workflows
        # This prevents context overflow errors in recipes with many tool calls
        assert workflow.context is True
    
    def test_workflow_context_true(self):
        """Workflow context=True should be stored."""
        from praisonaiagents import Workflow
        
        workflow = Workflow(name="Test", steps=[], context=True)
        
        assert workflow.context is True


class TestAgentsContextParam:
    """Tests for Agents context= parameter."""
    
    def test_agents_context_false_default(self):
        """Agents context=False should have zero overhead."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        agent = Agent(instructions="Test agent")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentTeam(agents=[agent], tasks=[task], context=False)
        
        assert agents._context_param is False
        assert agents._context_manager is None
        assert agents._context_manager_initialized is False
    
    def test_agents_context_true_lazy_init(self):
        """Agents context=True should lazy-init MultiAgentContextManager."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        agent = Agent(instructions="Test agent")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentTeam(agents=[agent], tasks=[task], context=True)
        
        # Not initialized until first access
        assert agents._context_manager_initialized is False
        
        # Access triggers initialization
        manager = agents.context_manager
        assert agents._context_manager_initialized is True
        assert manager is not None
    
    def test_agents_context_manager_config(self):
        """Agents context=ManagerConfig should use provided config."""
        from praisonaiagents import Agent, AgentTeam, Task
        from praisonaiagents.context import ManagerConfig
        
        config = ManagerConfig(
            auto_compact=True,
            compact_threshold=0.7,
        )
        
        agent = Agent(instructions="Test agent")
        task = Task(description="Test task", agent=agent)
        
        agents = AgentTeam(agents=[agent], tasks=[task], context=config)
        
        manager = agents.context_manager
        assert manager is not None


class TestContextPrecedence:
    """Tests for context parameter precedence rules."""
    
    def test_old_context_params_rejected(self):
        """Old context-related params should raise TypeError."""
        from praisonaiagents import Agent
        
        # Old params should be rejected (breaking change)
        with pytest.raises(TypeError):
            Agent(instructions="Test", auto_summarize=True)
            
        with pytest.raises(TypeError):
            Agent(instructions="Test", summarize_threshold=0.9)
            
        with pytest.raises(TypeError):
            Agent(instructions="Test", fast_context=True)
            
        with pytest.raises(TypeError):
            Agent(instructions="Test", respect_context_window=True)
            
        with pytest.raises(TypeError):
            Agent(instructions="Test", history_in_context=5)
            
        with pytest.raises(TypeError):
            Agent(instructions="Test", context_compactor="test")
    
    def test_context_param_is_only_interface(self):
        """context= should be the only interface for context management."""
        from praisonaiagents import Agent
        from praisonaiagents.context import ManagerConfig
        
        # New way: use context= param
        config = ManagerConfig(auto_compact=True, compact_threshold=0.8)
        agent = Agent(instructions="Test agent", context=config)
        
        # Verify context manager is configured
        assert agent.context_manager is not None
        assert agent.context_manager.config.auto_compact is True
        assert agent.context_manager.config.compact_threshold == 0.8


class TestContextManagerIntegration:
    """Integration tests for context manager with Agent."""
    
    def test_context_manager_has_required_methods(self):
        """ContextManager should have required methods."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", context=True)
        manager = agent.context_manager
        
        # Check required methods exist
        assert hasattr(manager, 'process')
        assert hasattr(manager, 'get_stats')
        assert hasattr(manager, 'config')
    
    def test_context_manager_model_from_agent(self):
        """ContextManager should use agent's model."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            llm="gpt-4o",
            context=True,
        )
        manager = agent.context_manager
        
        # Manager should use agent's model
        assert manager.model == "gpt-4o"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
