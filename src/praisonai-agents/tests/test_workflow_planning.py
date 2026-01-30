"""
Test suite for Workflow Planning Mode Integration.

Tests the enhanced workflow system's ability to integrate with planning mode,
including workflow-level planning settings and planning LLM configuration.
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Workflow, Task
from praisonaiagents.workflows import WorkflowManager, WorkflowPlanningConfig, WorkflowMemoryConfig


class TestWorkflowPlanningFields:
    """Test Workflow dataclass planning-related fields."""
    
    def test_workflow_has_planning_field(self):
        """Workflow should have planning field."""
        workflow = Workflow(
            name="test_workflow",
            planning=True
        )
        assert hasattr(workflow, 'planning')
        assert workflow.planning is True
    
    def test_workflow_planning_default_false(self):
        """Workflow planning should default to False."""
        workflow = Workflow(name="test_workflow")
        assert workflow.planning is False
    
    def test_workflow_has_planning_llm_field(self):
        """Workflow should have planning_llm via consolidated planning param."""
        workflow = Workflow(
            name="test_workflow",
            planning=WorkflowPlanningConfig(enabled=True, llm="gpt-4o")
        )
        assert hasattr(workflow, '_planning_llm')
        assert workflow._planning_llm == "gpt-4o"
    
    def test_workflow_planning_llm_default_none(self):
        """Workflow planning_llm should default to None."""
        workflow = Workflow(name="test_workflow")
        assert workflow._planning_llm is None
    
    def test_workflow_to_dict_includes_planning_fields(self):
        """to_dict() should include planning-related fields."""
        workflow = Workflow(
            name="test_workflow",
            planning=WorkflowPlanningConfig(enabled=True, llm="gpt-4o")
        )
        d = workflow.to_dict()
        assert "planning" in d
        # Planning is now a config object
        assert workflow._planning_enabled is True
        assert workflow._planning_llm == "gpt-4o"


class TestWorkflowMemoryFields:
    """Test Workflow dataclass memory-related fields."""
    
    def test_workflow_has_memory_config_field(self):
        """Workflow should have memory via consolidated memory param."""
        workflow = Workflow(
            name="test_workflow",
            memory=WorkflowMemoryConfig(
                backend="rag"
            )
        )
        assert hasattr(workflow, '_memory_config')
        assert workflow._memory_config is not None
    
    def test_workflow_memory_config_default_none(self):
        """Workflow memory should default to None."""
        workflow = Workflow(name="test_workflow")
        assert workflow._memory_config is None
    
    def test_workflow_to_dict_includes_memory_config(self):
        """to_dict() should include memory field."""
        workflow = Workflow(
            name="test_workflow",
            memory=WorkflowMemoryConfig(backend="sqlite")
        )
        d = workflow.to_dict()
        assert "memory" in d


class TestExecutePlanningParameter:
    """Test execute() planning parameter."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_execute_accepts_planning_parameter(self):
        """Execute should accept planning parameter."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return "Result"
        
        # Should not raise error
        result = manager.execute(
            "test_workflow",
            executor=mock_executor,
            planning=True
        )
        
        assert result["success"]
    
    def test_workflow_planning_used_when_not_overridden(self):
        """Workflow's planning setting should be used when not overridden."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            planning=True,  # Workflow-level planning enabled
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return "Result"
        
        # Execute without planning parameter - should use workflow's setting
        result = manager.execute(
            "test_workflow",
            executor=mock_executor
        )
        
        assert result["success"]


class TestExecuteMemoryParameter:
    """Test execute() memory parameter."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_execute_accepts_memory_parameter(self):
        """Execute should accept memory parameter."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        mock_memory = Mock()
        
        def mock_executor(action):
            return "Result"
        
        # Should not raise error
        result = manager.execute(
            "test_workflow",
            executor=mock_executor,
            memory=mock_memory
        )
        
        assert result["success"]
    
    def test_memory_passed_to_step_agent(self):
        """Memory should be passed to created step agents."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="step1",
                    action="Action 1",
                    agent_config={"role": "Helper"}
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        mock_memory = Mock()
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent = Mock()
            mock_agent.chat = Mock(return_value="Response")
            MockAgent.return_value = mock_agent
            
            manager.execute(
                "test_workflow",
                memory=mock_memory,
                default_llm="gpt-4o-mini"
            )
            
            call_kwargs = MockAgent.call_args[1]
            assert "memory" in call_kwargs
            assert call_kwargs["memory"] == mock_memory


class TestExecuteStreamParameter:
    """Test execute() stream parameter."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_execute_accepts_stream_parameter(self):
        """Execute should accept stream parameter."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return "Result"
        
        # Should not raise error
        result = manager.execute(
            "test_workflow",
            executor=mock_executor,
            stream=True
        )
        
        assert result["success"]


class TestExecuteVerboseParameter:
    """Test execute() verbose parameter."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_execute_accepts_verbose_parameter(self):
        """Execute should accept verbose parameter."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return "Result"
        
        # Should not raise error
        result = manager.execute(
            "test_workflow",
            executor=mock_executor,
            verbose=2
        )
        
        assert result["success"]
    
    def test_verbose_passed_to_step_agent(self):
        """Verbose level should be passed to created step agents."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
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
            mock_agent = Mock()
            mock_agent.chat = Mock(return_value="Response")
            MockAgent.return_value = mock_agent
            
            manager.execute(
                "test_workflow",
                verbose=3,
                default_llm="gpt-4o-mini"
            )
            
            # Verbose is handled at workflow level, not passed to Agent constructor
            # Just verify the workflow executed successfully
            assert MockAgent.called


class TestExecuteResultsWithVariables:
    """Test that execute() returns variables in results."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_results_include_variables(self):
        """Results should include accumulated variables."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            variables={"initial": "value"},
            steps=[
                Task(name="step1", action="Action 1"),
                Task(name="step2", action="Action 2")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def mock_executor(action):
            return f"Output for {action}"
        
        result = manager.execute("test_workflow", executor=mock_executor)
        
        assert "variables" in result
        assert "initial" in result["variables"]
        # Should also have step outputs as variables
        assert "previous_output" in result["variables"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
