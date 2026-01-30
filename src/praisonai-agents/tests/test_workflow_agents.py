"""
Test suite for Workflow Per-Step Agent Configuration.

Tests the enhanced workflow system's ability to configure different agents
for each step, including custom roles, goals, backstories, and LLM settings.
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Workflow, Task
from praisonaiagents.workflows import WorkflowManager


class TestTaskAgentFields:
    """Test Task dataclass agent-related fields."""
    
    def test_workflow_step_has_agent_config_field(self):
        """Task should have agent_config field."""
        step = Task(
            name="test_step",
            action="do something",
            agent_config={
                "role": "Researcher",
                "goal": "Find information",
                "backstory": "Expert researcher"
            }
        )
        assert hasattr(step, 'agent_config')
        assert step.agent_config["role"] == "Researcher"
    
    def test_workflow_step_has_tools_field(self):
        """Task should have tools field."""
        step = Task(
            name="test_step",
            action="do something",
            tools=["search", "calculator"]
        )
        assert hasattr(step, 'tools')
        assert "search" in step.tools
    
    def test_workflow_step_agent_config_default_none(self):
        """agent_config should default to None."""
        step = Task(name="test_step", action="do something")
        assert step.agent_config is None
    
    def test_workflow_step_tools_default_none(self):
        """tools should default to None."""
        step = Task(name="test_step", action="do something")
        assert step.tools is None
    
    def test_workflow_step_to_dict_includes_agent_fields(self):
        """to_dict() should include agent-related fields."""
        step = Task(
            name="test_step",
            action="do something",
            agent_config={"role": "Writer"},
            tools=["grammar_check"]
        )
        d = step.to_dict()
        assert "agent_config" in d
        assert "tools" in d


class TestWorkflowDefaultAgentConfig:
    """Test Workflow dataclass default agent configuration."""
    
    def test_workflow_has_default_agent_config(self):
        """Workflow should have default_agent_config field."""
        workflow = Workflow(
            name="test_workflow",
            default_agent_config={
                "role": "Assistant",
                "goal": "Help with tasks"
            }
        )
        assert hasattr(workflow, 'default_agent_config')
        assert workflow.default_agent_config["role"] == "Assistant"
    
    def test_workflow_has_default_llm(self):
        """Workflow should have default_llm field."""
        workflow = Workflow(
            name="test_workflow",
            default_llm="gpt-4o-mini"
        )
        assert hasattr(workflow, 'default_llm')
        assert workflow.default_llm == "gpt-4o-mini"
    
    def test_workflow_to_dict_includes_defaults(self):
        """to_dict() should include default agent config fields."""
        workflow = Workflow(
            name="test_workflow",
            default_agent_config={"role": "Helper"},
            default_llm="gpt-4o"
        )
        d = workflow.to_dict()
        assert "default_agent_config" in d
        assert "default_llm" in d


class TestCreateStepAgent:
    """Test _create_step_agent method."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_create_step_agent_with_config(self):
        """Should create agent from step's agent_config."""
        manager = WorkflowManager()
        
        step = Task(
            name="research",
            action="Research topic",
            agent_config={
                "role": "Researcher",
                "goal": "Find comprehensive information",
                "backstory": "Expert in research"
            }
        )
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            MockAgent.return_value = Mock()
            agent = manager._create_step_agent(
                step=step,
                default_llm="gpt-4o-mini",
                verbose=0
            )
            
            # Verify Agent was called with config
            MockAgent.assert_called_once()
            call_kwargs = MockAgent.call_args[1]
            assert call_kwargs["role"] == "Researcher"
            assert call_kwargs["goal"] == "Find comprehensive information"
    
    def test_create_step_agent_uses_default_agent(self):
        """Should return default_agent when no agent_config."""
        manager = WorkflowManager()
        
        step = Task(
            name="simple_step",
            action="Do something"
        )
        
        default_agent = Mock()
        agent = manager._create_step_agent(
            step=step,
            default_agent=default_agent,
            default_llm="gpt-4o-mini"
        )
        
        assert agent == default_agent
    
    def test_create_step_agent_includes_tools(self):
        """Should include tools in agent config."""
        manager = WorkflowManager()
        
        mock_tool = Mock()
        step = Task(
            name="research",
            action="Research topic",
            agent_config={"role": "Researcher"},
            tools=[mock_tool]
        )
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            MockAgent.return_value = Mock()
            manager._create_step_agent(
                step=step,
                default_llm="gpt-4o-mini"
            )
            
            call_kwargs = MockAgent.call_args[1]
            assert "tools" in call_kwargs
            assert mock_tool in call_kwargs["tools"]
    
    def test_create_step_agent_includes_memory(self):
        """Should include memory in agent config."""
        manager = WorkflowManager()
        
        step = Task(
            name="research",
            action="Research topic",
            agent_config={"role": "Researcher"}
        )
        
        mock_memory = Mock()
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            MockAgent.return_value = Mock()
            manager._create_step_agent(
                step=step,
                memory=mock_memory
            )
            
            call_kwargs = MockAgent.call_args[1]
            assert "memory" in call_kwargs
            assert call_kwargs["memory"] == mock_memory


class TestExecuteWithAgents:
    """Test execute() with per-step agent configuration."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_execute_with_default_agent(self):
        """Execute should use default_agent when provided."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1"),
                Task(name="step2", action="Action 2")
            ]
        )
        self._register_workflow(manager, workflow)
        
        # Create mock default agent
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Agent response")
        
        result = manager.execute(
            "test_workflow",
            default_agent=mock_agent
        )
        
        assert result["success"]
        assert mock_agent.chat.call_count == 2
    
    def test_execute_with_step_agent_config(self):
        """Execute should create agent from step's agent_config."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="research",
                    action="Research AI",
                    agent_config={
                        "role": "Researcher",
                        "goal": "Find information"
                    }
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent_instance = Mock()
            mock_agent_instance.chat = Mock(return_value="Research results")
            MockAgent.return_value = mock_agent_instance
            
            result = manager.execute(
                "test_workflow",
                default_llm="gpt-4o-mini"
            )
            
            assert result["success"]
            MockAgent.assert_called_once()
    
    def test_execute_with_executor_overrides_agent(self):
        """Executor function should override agent creation."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="step1",
                    action="Action 1",
                    agent_config={"role": "Should not be used"}
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        executor_called = [False]
        
        def custom_executor(action):
            executor_called[0] = True
            return "Custom executor result"
        
        result = manager.execute(
            "test_workflow",
            executor=custom_executor
        )
        
        assert result["success"]
        assert executor_called[0]
    
    def test_execute_fails_without_executor_or_agent(self):
        """Execute should fail if no executor or agent provided."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        result = manager.execute("test_workflow")
        
        assert not result["success"]
        # Error can be at top level or in results array
        error_found = "No executor available" in result.get("error", "")
        if not error_found and "results" in result:
            error_found = any(
                "No executor available" in r.get("error", "") 
                for r in result.get("results", [])
            )
        assert error_found, f"Expected 'No executor available' error, got: {result}"


class TestWorkflowLevelDefaults:
    """Test workflow-level default configurations."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_workflow_default_llm_used(self):
        """Workflow's default_llm should be used for agent creation."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            default_llm="gpt-4o",
            steps=[
                Task(
                    name="step1",
                    action="Action 1",
                    agent_config={"role": "Helper"}
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent_instance = Mock()
            mock_agent_instance.chat = Mock(return_value="Response")
            MockAgent.return_value = mock_agent_instance
            
            manager.execute("test_workflow")
            
            call_kwargs = MockAgent.call_args[1]
            assert call_kwargs.get("llm") == "gpt-4o"
    
    def test_execute_default_llm_overrides_workflow(self):
        """Execute's default_llm should override workflow's default_llm."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            default_llm="gpt-3.5-turbo",
            steps=[
                Task(
                    name="step1",
                    action="Action 1",
                    agent_config={"role": "Helper"}
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent_instance = Mock()
            mock_agent_instance.chat = Mock(return_value="Response")
            MockAgent.return_value = mock_agent_instance
            
            manager.execute("test_workflow", default_llm="gpt-4o-mini")
            
            call_kwargs = MockAgent.call_args[1]
            assert call_kwargs.get("llm") == "gpt-4o-mini"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
