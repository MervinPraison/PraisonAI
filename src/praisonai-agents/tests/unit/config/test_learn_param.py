"""TDD Tests for top-level learn= parameter on Agent and related classes.

Tests that learn= is a first-class citizen, peer to memory=, not nested inside it.
"""


class TestAgentLearnParam:
    """Test Agent(learn=...) top-level parameter."""

    def test_agent_accepts_learn_false(self):
        """Agent should accept learn=False (default, no learning)."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=False,
        )
        
        assert agent._learn_config is None or agent._learn_config is False

    def test_agent_accepts_learn_true(self):
        """Agent should accept learn=True (enable with defaults)."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=True,
        )
        
        # Should have learn config enabled
        assert agent._learn_config is not None
        assert agent._learn_config is not False

    def test_agent_accepts_learn_config(self):
        """Agent should accept learn=LearnConfig(...)."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import LearnConfig
        
        config = LearnConfig(persona=True, insights=True, patterns=False)
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=config,
        )
        
        # Should store the config
        assert agent._learn_config is not None
        if hasattr(agent._learn_config, 'persona'):
            assert agent._learn_config.persona is True
            assert agent._learn_config.insights is True

    def test_learn_param_independent_of_memory(self):
        """learn= should work without memory= being set."""
        from praisonaiagents import Agent
        
        # learn=True without memory=True should still work
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=True,
            memory=None,  # No memory explicitly
        )
        
        # Learn should be enabled even without explicit memory
        assert agent._learn_config is not None

    def test_learn_and_memory_both_work(self):
        """learn= and memory= should work together."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=True,
            memory=True,
        )
        
        # Both should be enabled
        assert agent._learn_config is not None
        assert agent._memory_instance is not None


class TestLearnConfigExport:
    """Test that LearnConfig is exported from top-level package."""

    def test_learn_config_exported(self):
        """LearnConfig should be importable from praisonaiagents."""
        from praisonaiagents import LearnConfig
        
        assert LearnConfig is not None
        
        # Should be able to instantiate
        config = LearnConfig()
        assert config.persona is True  # Default
        assert config.insights is True  # Default

    def test_learn_scope_exported(self):
        """LearnScope should be importable from praisonaiagents."""
        from praisonaiagents import LearnScope
        
        assert LearnScope is not None
        assert LearnScope.PRIVATE.value == "private"
        assert LearnScope.SHARED.value == "shared"


class TestAgentTeamLearnParam:
    """Test AgentTeam(learn=...) parameter."""

    def test_agent_team_accepts_learn_param(self):
        """AgentTeam should accept learn= parameter."""
        from praisonaiagents import Agent, AgentTeam
        
        agent1 = Agent(name="agent1", instructions="Agent 1")
        agent2 = Agent(name="agent2", instructions="Agent 2")
        
        team = AgentTeam(
            agents=[agent1, agent2],
            learn=True,
        )
        
        # Should store learn config
        assert hasattr(team, '_learn') or hasattr(team, 'learn')


class TestWorkflowLearnParam:
    """Test Workflow/AgentFlow(learn=...) parameter."""

    def test_workflow_accepts_learn_param(self):
        """Workflow should accept learn= parameter."""
        from praisonaiagents import Agent
        from praisonaiagents.workflows import Workflow
        
        agent = Agent(name="test", instructions="Test")
        
        workflow = Workflow(
            steps=[agent],  # Workflow uses steps=, not agents=
            learn=True,
        )
        
        # Should store learn config (dataclass field)
        assert workflow.learn is True


class TestLearnParamDocstring:
    """Test that learn= param is documented."""

    def test_agent_docstring_mentions_learn(self):
        """Agent.__init__ docstring should mention learn parameter."""
        from praisonaiagents import Agent
        
        docstring = Agent.__init__.__doc__ or ""
        
        # Should mention learn parameter
        assert "learn" in docstring.lower()


class TestBackwardCompatibility:
    """Test backward compatibility with memory=MemoryConfig(learn=...)."""

    def test_memory_config_learn_still_works(self):
        """memory=MemoryConfig(learn=True) should still work."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import MemoryConfig
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory=MemoryConfig(learn=True),
        )
        
        # Should have memory with learn enabled
        assert agent._memory_instance is not None
        # Learn context should be accessible
        if hasattr(agent._memory_instance, 'get_learn_context'):
            context = agent._memory_instance.get_learn_context()
            assert isinstance(context, str)

    def test_top_level_learn_takes_precedence(self):
        """Top-level learn= should take precedence over memory.learn."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import MemoryConfig
        
        # Top-level learn=False should override memory.learn=True
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory=MemoryConfig(learn=True),
            learn=False,  # This should take precedence
        )
        
        # Learn should be disabled due to top-level param
        assert agent._learn_config is None or agent._learn_config is False
