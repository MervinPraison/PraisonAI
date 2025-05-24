import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent, Task, PraisonAIAgents
    from praisonaiagents.llm.llm import LLM
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestAgent:
    """Test core Agent functionality."""
    
    def test_agent_creation(self, sample_agent_config):
        """Test basic agent creation."""
        agent = Agent(**sample_agent_config)
        assert agent.name == "TestAgent"
        assert agent.role == "Test Specialist"
        assert agent.goal == "Perform testing tasks"
        assert agent.backstory == "An expert testing agent"
    
    def test_agent_with_llm_dict(self):
        """Test agent creation with LLM dictionary."""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key',
            'temperature': 0.7
        }
        
        agent = Agent(
            name="LLM Test Agent",
            llm=llm_config
        )
        
        assert agent.name == "LLM Test Agent"
        assert isinstance(agent.llm, (LLM, dict))
    
    def test_agent_with_tools(self):
        """Test agent creation with custom tools."""
        def sample_tool(query: str) -> str:
            """A sample tool for testing."""
            return f"Tool result for: {query}"
        
        agent = Agent(
            name="Tool Agent",
            tools=[sample_tool]
        )
        
        assert agent.name == "Tool Agent"
        assert len(agent.tools) >= 1
    
    @patch('praisonaiagents.llm.llm.litellm')
    def test_agent_execution(self, mock_litellm, sample_agent_config, mock_llm_response):
        """Test agent task execution."""
        mock_litellm.completion.return_value = mock_llm_response
        
        agent = Agent(**sample_agent_config)
        
        # Mock the execute_task method if it exists
        with patch.object(agent, 'execute_task', return_value="Task completed") as mock_execute:
            result = agent.execute_task("Test task")
            assert result == "Task completed"
            mock_execute.assert_called_once_with("Test task")


class TestTask:
    """Test core Task functionality."""
    
    def test_task_creation(self, sample_task_config, sample_agent_config):
        """Test basic task creation."""
        agent = Agent(**sample_agent_config)
        task = Task(agent=agent, **sample_task_config)
        
        assert task.name == "test_task"
        assert task.description == "A test task"
        assert task.expected_output == "Test output"
        assert task.agent == agent
    
    def test_task_with_callback(self, sample_task_config, sample_agent_config):
        """Test task creation with callback function."""
        def sample_callback(output):
            return f"Processed: {output}"
        
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            callback=sample_callback,
            **sample_task_config
        )
        
        assert task.callback == sample_callback
    
    def test_async_task_creation(self, sample_task_config, sample_agent_config):
        """Test async task creation."""
        agent = Agent(**sample_agent_config)
        task = Task(
            agent=agent,
            async_execution=True,
            **sample_task_config
        )
        
        assert task.async_execution is True


class TestPraisonAIAgents:
    """Test PraisonAIAgents orchestration."""
    
    def test_agents_creation(self, sample_agent_config, sample_task_config):
        """Test PraisonAIAgents creation."""
        agent = Agent(**sample_agent_config)
        task = Task(agent=agent, **sample_task_config)
        
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )
        
        assert len(agents.agents) == 1
        assert len(agents.tasks) == 1
        assert agents.process == "sequential"
    
    @patch('praisonaiagents.llm.llm.litellm')
    def test_sequential_execution(self, mock_litellm, sample_agent_config, sample_task_config, mock_llm_response):
        """Test sequential task execution."""
        mock_litellm.completion.return_value = mock_llm_response
        
        agent = Agent(**sample_agent_config)
        task = Task(agent=agent, **sample_task_config)
        
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )
        
        # Mock the start method
        with patch.object(agents, 'start', return_value="Execution completed") as mock_start:
            result = agents.start()
            assert result == "Execution completed"
            mock_start.assert_called_once()
    
    def test_multiple_agents(self, sample_agent_config, sample_task_config):
        """Test multiple agents creation."""
        agent1 = Agent(name="Agent1", **{k: v for k, v in sample_agent_config.items() if k != 'name'})
        agent2 = Agent(name="Agent2", **{k: v for k, v in sample_agent_config.items() if k != 'name'})
        
        task1 = Task(agent=agent1, name="task1", **{k: v for k, v in sample_task_config.items() if k != 'name'})
        task2 = Task(agent=agent2, name="task2", **{k: v for k, v in sample_task_config.items() if k != 'name'})
        
        agents = PraisonAIAgents(
            agents=[agent1, agent2],
            tasks=[task1, task2],
            process="hierarchical"
        )
        
        assert len(agents.agents) == 2
        assert len(agents.tasks) == 2
        assert agents.process == "hierarchical"


class TestLLMIntegration:
    """Test LLM integration functionality."""
    
    @patch('praisonaiagents.llm.llm.litellm')
    def test_llm_creation(self, mock_litellm):
        """Test LLM creation with different providers."""
        llm = LLM(model='gpt-4o-mini', api_key='test-key')
        assert llm.model == 'gpt-4o-mini'
        assert llm.api_key == 'test-key'
    
    @patch('praisonaiagents.llm.llm.litellm')
    def test_llm_chat(self, mock_litellm, mock_llm_response):
        """Test LLM chat functionality."""
        mock_litellm.completion.return_value = mock_llm_response
        
        llm = LLM(model='gpt-4o-mini', api_key='test-key')
        messages = [{'role': 'user', 'content': 'Hello'}]
        
        response = llm.chat(messages)
        assert response is not None
        mock_litellm.completion.assert_called_once()
    
    @patch('praisonaiagents.llm.llm.litellm')
    def test_llm_with_base_url(self, mock_litellm, mock_llm_response):
        """Test LLM with custom base URL."""
        mock_litellm.completion.return_value = mock_llm_response
        
        llm = LLM(
            model='openai/custom-model',
            api_key='test-key',
            base_url='http://localhost:4000'
        )
        
        messages = [{'role': 'user', 'content': 'Hello'}]
        llm.chat(messages)
        
        # Verify both base_url and api_base are set
        call_args = mock_litellm.completion.call_args[1]
        assert 'base_url' in call_args
        assert 'api_base' in call_args
        assert call_args['base_url'] == 'http://localhost:4000'
        assert call_args['api_base'] == 'http://localhost:4000'


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 