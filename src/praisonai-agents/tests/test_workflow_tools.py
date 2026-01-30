"""
Test suite for Workflow Per-Step Tools Support.

Tests the enhanced workflow system's ability to configure different tools
for each step, including tool execution and tool results in context.
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add the package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from praisonaiagents import Workflow, Task
from praisonaiagents.workflows import WorkflowManager


class TestTaskToolsField:
    """Test Task tools field."""
    
    def test_workflow_step_tools_accepts_list(self):
        """Task should accept a list of tools."""
        mock_tool1 = Mock()
        mock_tool2 = Mock()
        
        step = Task(
            name="research",
            action="Research topic",
            tools=[mock_tool1, mock_tool2]
        )
        
        assert step.tools is not None
        assert len(step.tools) == 2
        assert mock_tool1 in step.tools
        assert mock_tool2 in step.tools
    
    def test_workflow_step_tools_accepts_callable(self):
        """Task should accept callable tools."""
        def search_tool(query):
            return f"Results for {query}"
        
        step = Task(
            name="search",
            action="Search for info",
            tools=[search_tool]
        )
        
        assert step.tools is not None
        assert callable(step.tools[0])
    
    def test_workflow_step_tools_in_to_dict(self):
        """to_dict() should include tools field."""
        step = Task(
            name="test",
            action="test action",
            tools=["tool1", "tool2"]
        )
        
        d = step.to_dict()
        assert "tools" in d
        assert d["tools"] == ["tool1", "tool2"]


class TestToolsPassedToAgent:
    """Test that tools are passed to agent during step execution."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_step_tools_passed_to_agent(self):
        """Step's tools should be passed to created agent."""
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
            manager._create_step_agent(step=step, default_llm="gpt-4o-mini")
            
            call_kwargs = MockAgent.call_args[1]
            assert "tools" in call_kwargs
            assert mock_tool in call_kwargs["tools"]
    
    def test_multiple_tools_passed_to_agent(self):
        """Multiple tools should all be passed to agent."""
        manager = WorkflowManager()
        
        tool1 = Mock(name="search")
        tool2 = Mock(name="calculator")
        tool3 = Mock(name="browser")
        
        step = Task(
            name="research",
            action="Research topic",
            agent_config={"role": "Researcher"},
            tools=[tool1, tool2, tool3]
        )
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            MockAgent.return_value = Mock()
            manager._create_step_agent(step=step, default_llm="gpt-4o-mini")
            
            call_kwargs = MockAgent.call_args[1]
            assert len(call_kwargs["tools"]) == 3


class TestDifferentToolsPerStep:
    """Test different tools for different steps."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_different_steps_different_tools(self):
        """Different steps can have different tools."""
        manager = WorkflowManager()
        
        search_tool = Mock(name="search")
        write_tool = Mock(name="write")
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="research",
                    action="Research AI",
                    agent_config={"role": "Researcher"},
                    tools=[search_tool]
                ),
                Task(
                    name="write",
                    action="Write article",
                    agent_config={"role": "Writer"},
                    tools=[write_tool]
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        created_agents = []
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            def track_agent(**kwargs):
                agent = Mock()
                agent.chat = Mock(return_value="Response")
                agent.tools = kwargs.get("tools", [])
                created_agents.append(kwargs)
                return agent
            
            MockAgent.side_effect = track_agent
            
            manager.execute("test_workflow", default_llm="gpt-4o-mini")
            
            # Verify different tools for each step
            assert len(created_agents) == 2
            assert search_tool in created_agents[0]["tools"]
            assert write_tool in created_agents[1]["tools"]
    
    def test_step_without_tools(self):
        """Steps without tools should work correctly."""
        manager = WorkflowManager()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="think",
                    action="Think about topic",
                    agent_config={"role": "Thinker"}
                    # No tools
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent = Mock()
            mock_agent.chat = Mock(return_value="Thoughts")
            MockAgent.return_value = mock_agent
            
            result = manager.execute("test_workflow", default_llm="gpt-4o-mini")
            
            assert result["success"]
            # tools should not be in kwargs or should be None
            call_kwargs = MockAgent.call_args[1]
            assert call_kwargs.get("tools") is None or call_kwargs.get("tools") == []


class TestToolsWithExecutor:
    """Test tools behavior when using custom executor."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_executor_ignores_step_tools(self):
        """When executor is provided, step tools are not used for agent creation."""
        manager = WorkflowManager()
        
        mock_tool = Mock()
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="step1",
                    action="Action 1",
                    tools=[mock_tool]  # Tools defined but executor provided
                )
            ]
        )
        self._register_workflow(manager, workflow)
        
        executor_called = [False]
        
        def custom_executor(action):
            executor_called[0] = True
            return "Executor result"
        
        # Should not try to create agent since executor is provided
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            result = manager.execute("test_workflow", executor=custom_executor)
            
            assert result["success"]
            assert executor_called[0]
            MockAgent.assert_not_called()


class TestToolsIntegration:
    """Integration tests for tools in workflow execution."""
    
    @staticmethod
    def _register_workflow(manager, workflow):
        """Helper to register workflow and mark as loaded."""
        manager._workflows[workflow.name.lower()] = workflow
        manager._loaded = True
    
    def test_full_workflow_with_tools(self):
        """Full workflow execution with tools should work."""
        manager = WorkflowManager()
        
        # Create mock tools
        search_tool = Mock(name="search")
        analyze_tool = Mock(name="analyze")
        
        workflow = Workflow(
            name="research_workflow",
            steps=[
                Task(
                    name="search",
                    action="Search for {{topic}}",
                    agent_config={"role": "Searcher"},
                    tools=[search_tool]
                ),
                Task(
                    name="analyze",
                    action="Analyze: {{previous_output}}",
                    agent_config={"role": "Analyzer"},
                    tools=[analyze_tool]
                ),
                Task(
                    name="summarize",
                    action="Summarize findings",
                    agent_config={"role": "Summarizer"}
                    # No tools for final step
                )
            ],
            variables={"topic": "AI trends"}
        )
        self._register_workflow(manager, workflow)
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            def create_mock_agent(**kwargs):
                agent = Mock()
                agent.chat = Mock(return_value=f"Response from {kwargs.get('role', 'agent')}")
                return agent
            
            MockAgent.side_effect = create_mock_agent
            
            result = manager.execute("research_workflow")
            
            assert result["success"]
            assert len(result["results"]) == 3
            assert MockAgent.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
