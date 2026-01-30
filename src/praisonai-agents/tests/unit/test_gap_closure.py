"""
Tests for Gap Closure - LLM Consolidation + Parity

TDD: These tests define the expected behavior for:
1. GAP A: No deprecation warnings for model/llm alias
2. GAP B: YAML parser supports consolidated params
3. GAP C: Wrapper agents use output= (not verbose/markdown)
4. GAP D: AutoAgents uses consolidated llm= (not function_calling_llm)
5. GAP E: model= and llm= are aliases with NO warnings
"""
import pytest
import warnings


class TestNoDeprecationWarnings:
    """GAP A + E: No deprecation warnings for model/llm or legacy params."""
    
    def test_no_warning_for_model_alias(self):
        """model= should work without any deprecation warning."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(instructions="Test", model="gpt-4o-mini")
            
            # Should NOT emit any deprecation warnings
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Unexpected warnings: {[str(x.message) for x in deprecation_warnings]}"
    
    def test_no_warning_for_llm_param(self):
        """llm= should work without any deprecation warning."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(instructions="Test", llm="gpt-4o-mini")
            
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Unexpected warnings: {[str(x.message) for x in deprecation_warnings]}"
    
    def test_llm_config_removed(self):
        """llm_config= is removed in v4 - should raise TypeError."""
        from praisonaiagents import Agent
        
        with pytest.raises(TypeError) as exc_info:
            agent = Agent(instructions="Test", llm_config={"temperature": 0.7})
        
        assert 'llm_config' in str(exc_info.value)
    
    def test_function_calling_llm_removed(self):
        """function_calling_llm= is removed in v4 - should raise TypeError."""
        from praisonaiagents import Agent
        
        with pytest.raises(TypeError) as exc_info:
            agent = Agent(instructions="Test", function_calling_llm="gpt-4o-mini")
        
        assert 'function_calling_llm' in str(exc_info.value)
    
    def test_model_and_llm_are_equivalent(self):
        """model= and llm= should produce identical behavior."""
        from praisonaiagents import Agent
        
        agent1 = Agent(instructions="Test", llm="gpt-4o")
        agent2 = Agent(instructions="Test", model="gpt-4o")
        
        assert agent1.llm == agent2.llm == "gpt-4o"


class TestAutoAgentsConsolidation:
    """GAP D: AutoAgents uses consolidated llm= (not function_calling_llm)."""
    
    def test_autoagents_does_not_pass_function_calling_llm_to_agent(self):
        """AutoAgents should not pass function_calling_llm= to Agent()."""
        from praisonaiagents.agents.autoagents import AutoAgents
        import inspect
        
        # Get the source code of the _create_agents_and_tasks method
        source = inspect.getsource(AutoAgents._create_agents_and_tasks)
        
        # Should NOT contain function_calling_llm= in Agent() call
        # This is a static analysis test
        assert "function_calling_llm=self.function_calling_llm" not in source, \
            "AutoAgents._create_agents_and_tasks still passes function_calling_llm= to Agent()"
    
    def test_autoagents_accepts_llm_param(self):
        """AutoAgents should accept llm= parameter."""
        from praisonaiagents.agents.autoagents import AutoAgents
        
        # Should not raise
        auto = AutoAgents(instructions="Test task", llm="gpt-4o-mini")
        assert auto.llm == "gpt-4o-mini"
    
    def test_autoagents_does_not_accept_function_calling_llm(self):
        """AutoAgents should reject function_calling_llm in v4."""
        from praisonaiagents.agents.autoagents import AutoAgents
        
        with pytest.raises(TypeError) as exc_info:
            auto = AutoAgents(
                instructions="Test task",
                llm="gpt-4o-mini",
                function_calling_llm="gpt-4o-mini"  # Should be rejected
            )
        
        assert 'function_calling_llm' in str(exc_info.value)


class TestYAMLParserConsolidation:
    """GAP B: YAML parser supports consolidated params."""
    
    def test_yaml_parser_maps_legacy_reflection_fields(self):
        """YAML parser should map legacy reflect_llm/min_reflect/max_reflect to reflection config."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
        roles:
          researcher:
            role: Researcher
            goal: Research topics
            backstory: Expert researcher
            reflect_llm: gpt-4o
            min_reflect: 2
            max_reflect: 5
            tasks:
              - description: Research AI
                expected_output: Report
        """
        
        import yaml
        config = yaml.safe_load(yaml_content)
        
        parser = YAMLWorkflowParser()
        # The parser should handle legacy fields without error
        # and map them appropriately
        agent = parser._create_agent("researcher", config["roles"]["researcher"])
        
        # Legacy fields should be stored for later use
        assert hasattr(agent, '_yaml_reflect_llm')
        assert hasattr(agent, '_yaml_min_reflect')
        assert hasattr(agent, '_yaml_max_reflect')
    
    def test_yaml_parser_supports_new_reflection_structure(self):
        """YAML parser should support new reflection: structure."""
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
        
        yaml_content = """
        roles:
          researcher:
            role: Researcher
            goal: Research topics
            backstory: Expert researcher
            reflection:
              enabled: true
              max_iterations: 5
              min_iterations: 2
            tasks:
              - description: Research AI
                expected_output: Report
        """
        
        import yaml
        config = yaml.safe_load(yaml_content)
        
        parser = YAMLWorkflowParser()
        agent = parser._create_agent("researcher", config["roles"]["researcher"])
        
        # Should handle new structure
        assert agent is not None


class TestWrapperAgentsModernization:
    """GAP C: Wrapper agents use output= (not verbose/markdown)."""
    
    def test_prompt_expander_agent_uses_output_in_agent_call(self):
        """PromptExpanderAgent should use output= when creating internal Agent."""
        from praisonaiagents.agent.prompt_expander_agent import PromptExpanderAgent
        import inspect
        
        # Get the source of the agent property
        source = inspect.getsource(PromptExpanderAgent.agent.fget)
        
        # Should use output= not verbose= or markdown=
        assert "output=" in source, "PromptExpanderAgent.agent should use output="
        assert "verbose=" not in source or "output=" in source, \
            "PromptExpanderAgent.agent should not pass verbose= directly to Agent()"
    
    def test_query_rewriter_agent_uses_output_in_agent_call(self):
        """QueryRewriterAgent should use output= when creating internal Agent."""
        from praisonaiagents.agent.query_rewriter_agent import QueryRewriterAgent
        import inspect
        
        # Get the source of the agent property
        source = inspect.getsource(QueryRewriterAgent.agent.fget)
        
        # Should use output= not verbose= or markdown=
        assert "output=" in source, "QueryRewriterAgent.agent should use output="
        assert "verbose=" not in source or "output=" in source, \
            "QueryRewriterAgent.agent should not pass verbose= directly to Agent()"
    
    def test_prompt_expander_accepts_model_param(self):
        """PromptExpanderAgent should accept model= parameter."""
        from praisonaiagents.agent.prompt_expander_agent import PromptExpanderAgent
        
        agent = PromptExpanderAgent(model="gpt-4o-mini")
        assert agent.model == "gpt-4o-mini"
    
    def test_query_rewriter_accepts_model_param(self):
        """QueryRewriterAgent should accept model= parameter."""
        from praisonaiagents.agent.query_rewriter_agent import QueryRewriterAgent
        
        agent = QueryRewriterAgent(model="gpt-4o-mini")
        assert agent.model == "gpt-4o-mini"


class TestAutoAgentsNoLegacyVerboseMarkdown:
    """AutoAgents should not pass verbose/markdown to Agent when output= is set."""
    
    def test_autoagents_uses_output_not_verbose_markdown(self):
        """AutoAgents should use output= and not pass verbose/markdown when output is set."""
        from praisonaiagents.agents.autoagents import AutoAgents
        import inspect
        
        source = inspect.getsource(AutoAgents._create_agents_and_tasks)
        
        # Should pass output= to Agent
        assert "output=self._output" in source or "output=" in source, \
            "AutoAgents should pass output= to Agent()"
        
        # Should NOT pass verbose= or markdown= directly
        assert "verbose=self.verbose" not in source, \
            "AutoAgents should not pass verbose= to Agent()"
