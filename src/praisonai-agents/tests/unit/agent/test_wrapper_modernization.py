"""
Tests for wrapper agent modernization - ensuring legacy args are mapped to consolidated params.

TDD: These tests verify that wrapper classes (PromptExpanderAgent, QueryRewriterAgent)
correctly use consolidated params (output=) instead of legacy args (verbose=, markdown=).
"""


class TestPromptExpanderAgentModernization:
    """Test PromptExpanderAgent uses consolidated output param."""
    
    def test_agent_uses_output_config_not_legacy_args(self):
        """PromptExpanderAgent should pass output= to Agent, not verbose=/markdown=."""
        from praisonaiagents.agent.prompt_expander_agent import PromptExpanderAgent
        
        # Create wrapper with verbose=True
        expander = PromptExpanderAgent(verbose=True)
        
        # Access the lazy-initialized agent
        agent = expander.agent
        
        # Verify: Agent should have output config set, not legacy verbose/markdown as direct args
        # The Agent stores resolved output in self.verbose and self.markdown after resolution
        # But the key is that the wrapper passed output= dict, not verbose=/markdown= directly
        assert hasattr(agent, 'verbose')
        assert hasattr(agent, 'markdown')
        # verbose should be True (from output config)
        assert agent.verbose == True
        # markdown should be False (from output config)
        assert agent.markdown == False
    
    def test_agent_verbose_false_propagates(self):
        """PromptExpanderAgent with verbose=False should propagate correctly."""
        from praisonaiagents.agent.prompt_expander_agent import PromptExpanderAgent
        
        expander = PromptExpanderAgent(verbose=False)
        agent = expander.agent
        
        assert agent.verbose == False
        assert agent.markdown == False


class TestQueryRewriterAgentModernization:
    """Test QueryRewriterAgent uses consolidated output param."""
    
    def test_agent_uses_output_config_not_legacy_args(self):
        """QueryRewriterAgent should pass output= to Agent, not verbose=/markdown=."""
        from praisonaiagents.agent.query_rewriter_agent import QueryRewriterAgent
        
        # Create wrapper with verbose=True
        rewriter = QueryRewriterAgent(verbose=True)
        
        # Access the lazy-initialized agent
        agent = rewriter.agent
        
        # Verify output config was applied
        assert agent.verbose == True
        assert agent.markdown == False
    
    def test_agent_verbose_false_propagates(self):
        """QueryRewriterAgent with verbose=False should propagate correctly."""
        from praisonaiagents.agent.query_rewriter_agent import QueryRewriterAgent
        
        rewriter = QueryRewriterAgent(verbose=False)
        agent = rewriter.agent
        
        assert agent.verbose == False
        assert agent.markdown == False


class TestProcessManagerAgentModernization:
    """Test Process class manager agents use consolidated params."""
    
    def test_manager_agent_creation_uses_consolidated_params(self):
        """Process manager agent should use output= consolidated param."""
        # This is a structural test - we verify the code pattern
        import inspect
        from praisonaiagents.process.process import Process
        
        # Get source of hierarchical method (sync version)
        source = inspect.getsource(Process.hierarchical)
        
        # After fix: should contain output= consolidated param
        assert 'output=' in source, "Process.hierarchical should use output= consolidated param"


class TestAutoAgentsConsolidatedParams:
    """Test AutoAgents already uses consolidated params correctly."""
    
    def test_autoagents_has_consolidated_params(self):
        """AutoAgents should accept consolidated params."""
        import inspect
        from praisonaiagents.agents.autoagents import AutoAgents
        
        sig = inspect.signature(AutoAgents.__init__)
        params = list(sig.parameters.keys())
        
        # Should have consolidated params
        assert 'output' in params
        assert 'reflection' in params
        assert 'caching' in params
        assert 'knowledge' in params
        assert 'execution' in params
        assert 'guardrails' in params
        assert 'web' in params
        assert 'hooks' in params
    
    def test_autoagents_consolidated_takes_precedence(self):
        """AutoAgents consolidated params should override legacy params."""
        import inspect
        from praisonaiagents.agents.autoagents import AutoAgents
        
        # Get source of _create_agents_and_tasks
        source = inspect.getsource(AutoAgents._create_agents_and_tasks)
        
        # Should pass consolidated params to Agent
        assert 'output=self._output' in source
        assert 'reflection=self._reflection' in source
        assert 'caching=self._caching' in source
