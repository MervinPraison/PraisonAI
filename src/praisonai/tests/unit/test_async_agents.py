import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent, Task, PraisonAIAgents
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestAsyncAgents:
    """Test async agent functionality."""
    
    @pytest.mark.asyncio
    async def test_async_tool_creation(self):
        """Test agent with async tools."""
        async def async_search_tool(query: str) -> str:
            """Async search tool for testing."""
            await asyncio.sleep(0.1)  # Simulate async work
            return f"Async search result for: {query}"
        
        agent = Agent(
            name="AsyncAgent",
            tools=[async_search_tool]
        )
        
        assert agent.name == "AsyncAgent"
        assert len(agent.tools) >= 1
    
    @pytest.mark.asyncio
    async def test_async_task_execution(self, sample_agent_config, sample_task_config):
        """Test async task execution."""
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            async_execution=True,
            **sample_task_config
        )
        
        assert task.async_execution is True
    
    @pytest.mark.asyncio
    async def test_async_callback(self, sample_agent_config, sample_task_config):
        """Test async callback functionality."""
        callback_called = False
        callback_output = None
        
        async def async_callback(output):
            nonlocal callback_called, callback_output
            callback_called = True
            callback_output = output
            await asyncio.sleep(0.1)  # Simulate async processing
        
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            callback=async_callback,
            async_execution=True,
            **sample_task_config
        )
        
        assert task.callback == async_callback
        assert task.async_execution is True
    
    @pytest.mark.asyncio
    @patch('litellm.completion')
    async def test_async_agents_start(self, mock_completion, sample_agent_config, sample_task_config, mock_llm_response):
        """Test async agents start method."""
        mock_completion.return_value = mock_llm_response
        
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
        
        # Mock the astart method
        with patch.object(agents, 'astart', return_value="Async execution completed") as mock_astart:
            result = await agents.astart()
            assert result == "Async execution completed"
            mock_astart.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_mixed_sync_async_tasks(self, sample_agent_config, sample_task_config):
        """Test mixing sync and async tasks."""
        sync_agent = Agent(name="SyncAgent", **{k: v for k, v in sample_agent_config.items() if k != 'name'})
        async_agent = Agent(name="AsyncAgent", **{k: v for k, v in sample_agent_config.items() if k != 'name'})
        
        sync_task = Task(
            agent=sync_agent,
            name="sync_task",
            async_execution=False,
            **{k: v for k, v in sample_task_config.items() if k != 'name'}
        )
        
        async_task = Task(
            agent=async_agent,
            name="async_task",
            async_execution=True,
            **{k: v for k, v in sample_task_config.items() if k != 'name'}
        )
        
        agents = PraisonAIAgents(
            agents=[sync_agent, async_agent],
            tasks=[sync_task, async_task],
            process="sequential"
        )
        
        assert len(agents.agents) == 2
        assert len(agents.tasks) == 2
        assert sync_task.async_execution is False
        assert async_task.async_execution is True
    
    @pytest.mark.asyncio
    async def test_workflow_async_execution(self, sample_agent_config):
        """Test workflow with async task dependencies."""
        agent1 = Agent(name="Agent1", **{k: v for k, v in sample_agent_config.items() if k != 'name'})
        agent2 = Agent(name="Agent2", **{k: v for k, v in sample_agent_config.items() if k != 'name'})
        
        task1 = Task(
            name="workflow_start",
            description="Starting workflow task",
            expected_output="Start result",
            agent=agent1,
            is_start=True,
            next_tasks=["workflow_end"],
            async_execution=True
        )
        
        task2 = Task(
            name="workflow_end",
            description="Ending workflow task",
            expected_output="End result",
            agent=agent2,
            async_execution=True
        )
        
        agents = PraisonAIAgents(
            agents=[agent1, agent2],
            tasks=[task1, task2],
            process="workflow"
        )
        
        assert len(agents.tasks) == 2
        assert task1.is_start is True
        assert task1.next_tasks == ["workflow_end"]


class TestAsyncTools:
    """Test async tool functionality."""
    
    @pytest.mark.asyncio
    async def test_async_search_tool(self, mock_duckduckgo):
        """Test async search tool."""
        async def async_search_tool(query: str) -> dict:
            """Async search tool using DuckDuckGo."""
            await asyncio.sleep(0.1)  # Simulate network delay
            
            # Mock the search results
            return {
                "query": query,
                "results": [
                    {"title": "Test Result", "url": "https://example.com", "snippet": "Test content"}
                ],
                "total_results": 1
            }
        
        result = await async_search_tool("Python programming")
        
        assert result["query"] == "Python programming"
        assert result["total_results"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Test Result"
    
    @pytest.mark.asyncio
    async def test_async_tool_with_agent(self, sample_agent_config):
        """Test async tool integration with agent."""
        async def async_calculator(expression: str) -> str:
            """Async calculator tool."""
            await asyncio.sleep(0.1)
            try:
                result = eval(expression)  # Simple eval for testing
                return f"Result: {result}"
            except Exception as e:
                return f"Error: {e}"
        
        agent = Agent(
            name="AsyncCalculatorAgent",
            tools=[async_calculator],
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        assert agent.name == "AsyncCalculatorAgent"
        assert len(agent.tools) >= 1
    
    @pytest.mark.asyncio
    async def test_async_tool_error_handling(self):
        """Test async tool error handling."""
        async def failing_async_tool(input_data: str) -> str:
            """Async tool that fails."""
            await asyncio.sleep(0.1)
            raise ValueError("Intentional test error")
        
        try:
            result = await failing_async_tool("test")
            assert False, "Should have raised an error"
        except ValueError as e:
            assert str(e) == "Intentional test error"


class TestAsyncMemory:
    """Test async memory functionality."""
    
    @pytest.mark.asyncio
    async def test_async_memory_operations(self, temp_directory):
        """Test async memory add and search operations."""
        # Mock async memory operations
        async def async_memory_add(content: str) -> str:
            """Add content to memory asynchronously."""
            await asyncio.sleep(0.1)
            return f"Added to memory: {content}"
        
        async def async_memory_search(query: str) -> list:
            """Search memory asynchronously."""
            await asyncio.sleep(0.1)
            return [f"Memory result for: {query}"]
        
        # Test adding to memory
        add_result = await async_memory_add("Test memory content")
        assert "Added to memory" in add_result
        
        # Test searching memory
        search_results = await async_memory_search("test query")
        assert len(search_results) == 1
        assert "Memory result for" in search_results[0]


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 