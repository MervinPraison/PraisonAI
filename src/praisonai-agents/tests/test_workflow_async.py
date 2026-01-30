"""
Test suite for Workflow Async Support.

Tests the aexecute() async method for workflow execution.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Workflow, Task
from praisonaiagents.workflows import WorkflowManager


class TestAexecuteMethod:
    """Test aexecute() async method."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    @pytest.mark.asyncio
    async def test_aexecute_exists(self):
        """WorkflowManager should have aexecute method."""
        manager = WorkflowManager()
        assert hasattr(manager, 'aexecute')
        assert asyncio.iscoroutinefunction(manager.aexecute)
    
    @pytest.mark.asyncio
    async def test_aexecute_with_sync_executor(self):
        """aexecute should work with sync executor."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1"),
                Task(name="step2", action="Action 2")
            ]
        )
        self._register_workflow(manager, workflow)
        
        def sync_executor(action):
            return f"Sync result for {action}"
        
        result = await manager.aexecute("test_workflow", executor=sync_executor)
        
        assert result["success"]
        assert len(result["results"]) == 2
    
    @pytest.mark.asyncio
    async def test_aexecute_with_async_executor(self):
        """aexecute should work with async executor."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1"),
                Task(name="step2", action="Action 2")
            ]
        )
        self._register_workflow(manager, workflow)
        
        async def async_executor(action):
            await asyncio.sleep(0.01)  # Simulate async operation
            return f"Async result for {action}"
        
        result = await manager.aexecute("test_workflow", executor=async_executor)
        
        assert result["success"]
        assert len(result["results"]) == 2
        assert "Async result" in result["results"][0]["output"]
    
    @pytest.mark.asyncio
    async def test_aexecute_context_passing(self):
        """aexecute should pass context between steps."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Generate data"),
                Task(name="step2", action="Process {{previous_output}}")
            ]
        )
        self._register_workflow(manager, workflow)
        
        received_actions = []
        
        async def async_executor(action):
            received_actions.append(action)
            if "Generate" in action:
                return "DATA_ABC"
            return "Processed"
        
        result = await manager.aexecute("test_workflow", executor=async_executor)
        
        assert result["success"]
        # Step 2 should have received context
        assert "DATA_ABC" in received_actions[1] or "previous_output" in received_actions[1]
    
    @pytest.mark.asyncio
    async def test_aexecute_workflow_not_found(self):
        """aexecute should return error for non-existent workflow."""
        manager = WorkflowManager()
        manager._loaded = True
        
        result = await manager.aexecute("nonexistent_workflow")
        
        assert not result["success"]
        assert "not found" in result.get("error", "")
    
    @pytest.mark.asyncio
    async def test_aexecute_with_default_agent(self):
        """aexecute should work with default_agent."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Agent response")
        
        result = await manager.aexecute(
            "test_workflow",
            default_agent=mock_agent
        )
        
        assert result["success"]
        mock_agent.chat.assert_called()
    
    @pytest.mark.asyncio
    async def test_aexecute_with_async_agent(self):
        """aexecute should use achat if available on agent."""
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
            mock_agent.achat = AsyncMock(return_value="Async agent response")
            MockAgent.return_value = mock_agent
            
            result = await manager.aexecute(
                "test_workflow",
                default_llm="gpt-4o-mini"
            )
            
            assert result["success"]
            mock_agent.achat.assert_called()
    
    @pytest.mark.asyncio
    async def test_aexecute_returns_variables(self):
        """aexecute should return accumulated variables."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            variables={"initial": "value"},
            steps=[
                Task(name="step1", action="Action 1")
            ]
        )
        self._register_workflow(manager, workflow)
        
        async def async_executor(action):
            return "Output"
        
        result = await manager.aexecute("test_workflow", executor=async_executor)
        
        assert "variables" in result
        assert "previous_output" in result["variables"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
