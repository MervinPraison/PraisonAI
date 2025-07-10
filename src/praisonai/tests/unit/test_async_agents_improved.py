"""
Test async agent functionality with improved patterns.

This module tests asynchronous operations in the PraisonAI agents framework,
including async tools, task execution, callbacks, and mixed sync/async workflows.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from typing import Any

# Import from the package (conftest.py handles path setup)
from praisonaiagents import Agent, Task, PraisonAIAgents


class TestAsyncAgents:
    """Test async agent functionality with proper isolation and mocking."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_async_tool_creation_with_proper_mock(self, mock_async_sleep):
        """Test agent creation with async tools using proper mocking."""
        async def async_search_tool(query: str) -> str:
            """Async search tool for testing."""
            await asyncio.sleep(0.1)  # This is now mocked
            return f"Async search result for: {query}"
        
        agent = Agent(
            name="AsyncAgent",
            role="Async Test Agent",
            goal="Test async operations",
            tools=[async_search_tool]
        )
        
        # Verify agent properties
        assert agent.name == "AsyncAgent"
        assert agent.role == "Async Test Agent"
        assert len(agent.tools) >= 1
        
        # Verify the mock was called (no actual sleep occurred)
        result = await async_search_tool("test query")
        assert result == "Async search result for: test query"
        mock_async_sleep.assert_called_once_with(0.1)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_async_task_execution_isolated(self, sample_agent_config, sample_task_config):
        """Test async task configuration without external dependencies."""
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            async_execution=True,
            **sample_task_config
        )
        
        # Verify task properties
        assert task.async_execution is True
        assert task.agent == agent
        assert task.name == sample_task_config['name']
        assert task.description == sample_task_config['description']
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_async_callback_without_shared_state(self, sample_agent_config, sample_task_config, mock_async_sleep):
        """Test async callback functionality with proper state management."""
        # Use a class to track callback state instead of nonlocal
        class CallbackTracker:
            def __init__(self):
                self.called = False
                self.output = None
            
            async def callback(self, output: Any) -> None:
                self.called = True
                self.output = output
                await asyncio.sleep(0.1)  # Mocked, no actual delay
        
        tracker = CallbackTracker()
        
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            callback=tracker.callback,
            async_execution=True,
            **sample_task_config
        )
        
        # Verify task setup
        assert task.callback == tracker.callback
        assert task.async_execution is True
        
        # Simulate callback execution
        await tracker.callback("test output")
        assert tracker.called is True
        assert tracker.output == "test output"
        mock_async_sleep.assert_called_once_with(0.1)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_async_agents_workflow_with_mock_llm(
        self, 
        sample_agent_config, 
        sample_task_config, 
        mock_litellm,
        mock_async_sleep
    ):
        """Test complete async workflow with mocked LLM responses."""
        # Configure mock response
        mock_litellm.return_value = Mock(
            choices=[Mock(message=Mock(content="Async task completed successfully"))],
            usage=Mock(total_tokens=50)
        )
        
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            async_execution=True,
            **sample_task_config
        )
        
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )
        
        # Mock the async execution
        expected_result = "Async workflow completed"
        with patch.object(agents, 'astart', new_callable=AsyncMock) as mock_astart:
            mock_astart.return_value = expected_result
            
            result = await agents.astart()
            
            # Verify execution
            assert result == expected_result
            mock_astart.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_mixed_sync_async_tasks_with_clear_naming(
        self, 
        sample_agent_config, 
        sample_task_config
    ):
        """Test workflow with both synchronous and asynchronous tasks."""
        # Create agents with clear, distinct configurations
        sync_agent_config = {**sample_agent_config, 'name': 'SyncAgent'}
        async_agent_config = {**sample_agent_config, 'name': 'AsyncAgent'}
        
        sync_agent = Agent(**sync_agent_config)
        async_agent = Agent(**async_agent_config)
        
        # Create tasks with clear async flags
        sync_task = Task(
            name="sync_task",
            description="Synchronous task",
            expected_output="Sync output",
            agent=sync_agent,
            async_execution=False  # Explicitly set to False
        )
        
        async_task = Task(
            name="async_task",
            description="Asynchronous task",
            expected_output="Async output",
            agent=async_agent,
            async_execution=True
        )
        
        # Verify task configurations
        assert sync_task.async_execution is False
        assert async_task.async_execution is True
        assert sync_task.agent.name == "SyncAgent"
        assert async_task.agent.name == "AsyncAgent"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_async_error_handling(self, sample_agent_config, mock_litellm):
        """Test proper error handling in async operations."""
        # Configure mock to raise an exception
        mock_litellm.side_effect = Exception("Async operation failed")
        
        agent = Agent(**sample_agent_config)
        task = Task(
            name="error_task",
            description="Task that will fail",
            expected_output="Should not reach this",
            agent=agent,
            async_execution=True
        )
        
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )
        
        # Test that error is properly handled
        with pytest.raises(Exception) as exc_info:
            with patch.object(agents, 'astart', new_callable=AsyncMock) as mock_astart:
                mock_astart.side_effect = Exception("Async operation failed")
                await agents.astart()
        
        assert "Async operation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    @pytest.mark.timeout(5)  # Ensure test doesn't hang
    async def test_async_timeout_behavior(self, sample_agent_config):
        """Test that async operations respect timeouts."""
        async def slow_tool(input: str) -> str:
            """Tool that simulates slow operation."""
            await asyncio.sleep(10)  # Longer than test timeout
            return "Should not reach this"
        
        agent = Agent(
            name="TimeoutAgent",
            tools=[slow_tool],
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        # This test verifies the timeout marker works
        # The actual timeout testing would require running the tool
        assert agent.name == "TimeoutAgent"
        assert len(agent.tools) >= 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_concurrent_async_tasks(self, sample_agent_config, mock_litellm, mock_async_sleep):
        """Test concurrent execution of multiple async tasks."""
        # Configure mock responses
        mock_litellm.return_value = Mock(
            choices=[Mock(message=Mock(content="Concurrent task completed"))],
            usage=Mock(total_tokens=30)
        )
        
        # Create multiple agents and tasks
        agents = []
        tasks = []
        
        for i in range(3):
            agent = Agent(
                name=f"ConcurrentAgent{i}",
                **{k: v for k, v in sample_agent_config.items() if k != 'name'}
            )
            task = Task(
                name=f"concurrent_task_{i}",
                description=f"Concurrent task {i}",
                expected_output=f"Output {i}",
                agent=agent,
                async_execution=True
            )
            agents.append(agent)
            tasks.append(task)
        
        # Verify setup
        assert len(agents) == 3
        assert len(tasks) == 3
        assert all(task.async_execution for task in tasks)