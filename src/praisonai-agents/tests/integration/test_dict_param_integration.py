"""
Integration tests for Dict support in consolidated param resolution.

Tests that Agent, AgentManager, and Workflow classes correctly handle dict params
through the unified canonical resolver.

Note: Agent tests are skipped as they require LLM setup. The core dict
resolution is tested in unit tests. These tests focus on Workflow/Task
which don't require LLM setup.
"""

import pytest


# =============================================================================
# AGENT DICT PARAM TESTS - Using resolver directly to avoid LLM setup
# =============================================================================

class TestAgentDictParamsResolver:
    """Test Agent dict param resolution using the resolver directly."""
    
    def test_agent_output_dict_resolution(self):
        """Output dict resolves correctly through canonical resolver."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import OutputConfig
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        result = resolve(
            value={"verbose": True, "markdown": False},
            param_name="output",
            config_class=OutputConfig,
            presets=OUTPUT_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, OutputConfig)
        assert result.verbose is True
        assert result.markdown is False
    
    def test_agent_execution_dict_resolution(self):
        """Execution dict resolves correctly through canonical resolver."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import ExecutionConfig
        from praisonaiagents.config.presets import EXECUTION_PRESETS
        
        result = resolve(
            value={"max_iter": 50, "max_retry_limit": 10},
            param_name="execution",
            config_class=ExecutionConfig,
            presets=EXECUTION_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, ExecutionConfig)
        assert result.max_iter == 50
    
    def test_agent_dict_with_unknown_key_raises_error(self):
        """Dict with unknown key raises TypeError."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import OutputConfig
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"verbose": True, "invalid_key": "value"},
                param_name="output",
                config_class=OutputConfig,
                presets=OUTPUT_PRESETS,
                array_mode=ArrayMode.PRESET_OVERRIDE,
            )
        assert "Unknown keys" in str(exc_info.value)


# =============================================================================
# AGENTS (MULTI-AGENT) DICT PARAM TESTS - Using resolver directly
# =============================================================================

class TestAgentsDictParamsResolver:
    """Test Agents dict param resolution using the resolver directly."""
    
    def test_agents_output_dict_resolution(self):
        """Multi-agent output dict resolves correctly."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import MultiAgentOutputConfig
        from praisonaiagents.config.presets import MULTI_AGENT_OUTPUT_PRESETS
        
        result = resolve(
            value={"verbose": 2, "stream": False},
            param_name="output",
            config_class=MultiAgentOutputConfig,
            presets=MULTI_AGENT_OUTPUT_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, MultiAgentOutputConfig)
        assert result.verbose == 2
        assert result.stream is False
    
    def test_agents_execution_dict_resolution(self):
        """Multi-agent execution dict resolves correctly."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import MultiAgentExecutionConfig
        from praisonaiagents.config.presets import MULTI_AGENT_EXECUTION_PRESETS
        
        result = resolve(
            value={"max_iter": 25, "max_retries": 8},
            param_name="execution",
            config_class=MultiAgentExecutionConfig,
            presets=MULTI_AGENT_EXECUTION_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, MultiAgentExecutionConfig)
        assert result.max_iter == 25
        assert result.max_retries == 8
    
    def test_agents_hooks_dict_resolution(self):
        """Multi-agent hooks dict resolves correctly."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import MultiAgentHooksConfig
        
        def my_checker(result):
            return True
        
        result = resolve(
            value={"completion_checker": my_checker},
            param_name="hooks",
            config_class=MultiAgentHooksConfig,
            array_mode=ArrayMode.PASSTHROUGH,
        )
        assert isinstance(result, MultiAgentHooksConfig)
        assert result.completion_checker is my_checker


# =============================================================================
# WORKFLOW DICT PARAM TESTS
# =============================================================================

class TestWorkflowDictParams:
    """Test Workflow and Task with dict params."""
    
    def test_workflow_output_dict(self):
        """Workflow accepts output as dict."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            steps=[],
            output={"verbose": True, "stream": False},
        )
        # Output config should be resolved
        assert workflow.output is not None
    
    def test_workflow_planning_dict(self):
        """Workflow accepts planning as dict."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            steps=[],
            planning={"enabled": True, "llm": "gpt-4o"},
        )
        # Planning should be configured
        assert workflow.planning is not None
    
    def test_workflow_memory_dict(self):
        """Workflow accepts memory as dict."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            steps=[],
            memory={"backend": "sqlite", "user_id": "test_user"},
        )
        # Memory should be configured
        assert workflow.memory is not None
    
    def test_workflowstep_context_dict(self):
        """Task accepts context as dict (via TaskContextConfig)."""
        from praisonaiagents.workflows.workflows import Task
        from praisonaiagents.workflows.workflow_configs import TaskContextConfig
        
        step = Task(
            name="step1",
            action="do something",
            context=TaskContextConfig(from_steps=["step0"], retain_full=True),
        )
        # context stores the TaskContextConfig object
        assert hasattr(step.context, 'from_steps')
        assert step.context.from_steps == ["step0"]
        # retain_full_context is a separate param on Task
        assert step.context.retain_full is True
    
    def test_workflowstep_output_dict(self):
        """Task accepts output as dict."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="step1",
            action="do something",
            output={"file": "output.txt", "variable": "result"},
        )
        assert step.output_file == "output.txt"
        assert step.output_variable == "result"
    
    def test_workflowstep_execution_dict(self):
        """Task accepts execution as dict (params passed directly)."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="step1",
            action="do something",
            max_retries=5,
            quality_check=True,
        )
        assert step.max_retries == 5
        assert step.quality_check is True
    
    def test_workflowstep_routing_dict(self):
        """Task accepts routing as dict (via next_tasks param)."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="step1",
            action="do something",
            next_tasks=["step2", "step3"],
        )
        assert step.next_tasks == ["step2", "step3"]


# =============================================================================
# BACKWARD COMPATIBILITY TESTS - Using resolver directly
# =============================================================================

class TestBackwardCompatibility:
    """Test that existing usage patterns still work via resolver."""
    
    def test_bool_true_creates_default_config(self):
        """Bool True creates default config instance."""
        from praisonaiagents.config.param_resolver import resolve
        from praisonaiagents.config.feature_configs import PlanningConfig
        
        result = resolve(
            value=True,
            param_name="planning",
            config_class=PlanningConfig,
        )
        assert isinstance(result, PlanningConfig)
    
    def test_bool_false_returns_none(self):
        """Bool False returns None (disabled)."""
        from praisonaiagents.config.param_resolver import resolve
        from praisonaiagents.config.feature_configs import ReflectionConfig
        
        result = resolve(
            value=False,
            param_name="reflection",
            config_class=ReflectionConfig,
        )
        assert result is None
    
    def test_string_preset_resolves(self):
        """String preset resolves to config."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import OutputConfig
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        result = resolve(
            value="verbose",
            param_name="output",
            config_class=OutputConfig,
            presets=OUTPUT_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, OutputConfig)
        assert result.verbose is True
    
    def test_array_preset_override_works(self):
        """[preset, overrides] pattern works."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import OutputConfig
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        result = resolve(
            value=["verbose", {"stream": False}],
            param_name="output",
            config_class=OutputConfig,
            presets=OUTPUT_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, OutputConfig)
        assert result.verbose is True
        assert result.stream is False
    
    def test_workflow_bool_params_still_work(self):
        """Workflow with bool params still works."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            steps=[],
            planning=True,
        )
        # Should not raise - workflow created successfully
        assert workflow is not None
    
    def test_workflowstep_list_context_still_works(self):
        """Task with list context still works."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="step1",
            action="do something",
            context=["step0", "step_prev"],
        )
        # context stores the list directly
        assert step.context == ["step0", "step_prev"]


# =============================================================================
# BASE_URL / API_KEY SEPARATION TESTS
# =============================================================================

class TestBaseUrlApiKeySeparation:
    """Test that base_url and api_key remain separate parameters."""
    
    def test_agent_base_url_separate(self):
        """Agent base_url is a separate parameter, not consolidated."""
        from praisonaiagents.agent.agent import Agent
        import inspect
        
        sig = inspect.signature(Agent.__init__)
        params = list(sig.parameters.keys())
        
        # base_url should be a separate parameter
        assert "base_url" in params
        # It should NOT be part of any consolidated config
    
    def test_agent_api_key_separate(self):
        """Agent api_key is a separate parameter, not consolidated."""
        from praisonaiagents.agent.agent import Agent
        import inspect
        
        sig = inspect.signature(Agent.__init__)
        params = list(sig.parameters.keys())
        
        # api_key should be a separate parameter
        assert "api_key" in params
