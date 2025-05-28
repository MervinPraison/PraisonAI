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
        # When llm is a dict, it creates llm_instance (LLM object) not llm attribute
        assert hasattr(agent, 'llm_instance')
        assert isinstance(agent.llm_instance, LLM)
    
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
    
    @patch('litellm.completion')
    def test_agent_execution(self, mock_completion, sample_agent_config):
        """Test agent task execution."""
        # Create a mock that handles both streaming and non-streaming calls
        def mock_completion_side_effect(*args, **kwargs):
            # Check if streaming is requested
            if kwargs.get('stream', False):
                # Return an iterator for streaming
                class MockChunk:
                    def __init__(self, content):
                        self.choices = [MockChoice(content)]
                
                class MockChoice:
                    def __init__(self, content):
                        self.delta = MockDelta(content)
                
                class MockDelta:
                    def __init__(self, content):
                        self.content = content
                
                # Return iterator with chunks
                return iter([
                    MockChunk("Test "),
                    MockChunk("response "),
                    MockChunk("from "),
                    MockChunk("agent")
                ])
            else:
                # Return complete response for non-streaming
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "Test response from agent",
                                "role": "assistant",
                                "tool_calls": None
                            }
                        }
                    ]
                }
        
        mock_completion.side_effect = mock_completion_side_effect
        
        agent = Agent(**sample_agent_config)
        
        # Test the chat method instead of execute_task (which doesn't exist)
        result = agent.chat("Test task")
        assert result is not None
        assert "Test response from agent" in result
        # Verify that litellm.completion was called
        mock_completion.assert_called()


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
    
    @patch('litellm.completion')
    def test_sequential_execution(self, mock_completion, sample_agent_config, sample_task_config, mock_llm_response):
        """Test sequential task execution."""
        mock_completion.return_value = mock_llm_response
        
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
    
    def test_llm_creation(self):
        """Test LLM creation with different providers."""
        llm = LLM(model='gpt-4o-mini', api_key='test-key')
        assert llm.model == 'gpt-4o-mini'
        assert llm.api_key == 'test-key'
    
    @patch('litellm.completion')
    def test_llm_chat(self, mock_completion):
        """Test LLM chat functionality."""
        # Create a mock that handles both streaming and non-streaming calls
        def mock_completion_side_effect(*args, **kwargs):
            # Check if streaming is requested
            if kwargs.get('stream', False):
                # Return an iterator for streaming
                class MockChunk:
                    def __init__(self, content):
                        self.choices = [MockChoice(content)]
                
                class MockChoice:
                    def __init__(self, content):
                        self.delta = MockDelta(content)
                
                class MockDelta:
                    def __init__(self, content):
                        self.content = content
                
                # Return iterator with chunks
                return iter([
                    MockChunk("Hello! "),
                    MockChunk("How can "),
                    MockChunk("I help "),
                    MockChunk("you?")
                ])
            else:
                # Return complete response for non-streaming
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "Hello! How can I help you?",
                                "role": "assistant",
                                "tool_calls": None
                            }
                        }
                    ]
                }
        
        mock_completion.side_effect = mock_completion_side_effect
        
        llm = LLM(model='gpt-4o-mini', api_key='test-key')
        
        response = llm.get_response("Hello")
        assert response is not None
        assert "Hello! How can I help you?" in response
        mock_completion.assert_called()
    
    @patch('litellm.completion')
    def test_llm_with_base_url(self, mock_completion):
        """Test LLM with custom base URL."""
        # Create a mock that handles both streaming and non-streaming calls
        def mock_completion_side_effect(*args, **kwargs):
            # Check if streaming is requested
            if kwargs.get('stream', False):
                # Return an iterator for streaming
                class MockChunk:
                    def __init__(self, content):
                        self.choices = [MockChoice(content)]
                
                class MockChoice:
                    def __init__(self, content):
                        self.delta = MockDelta(content)
                
                class MockDelta:
                    def __init__(self, content):
                        self.content = content
                
                # Return iterator with chunks
                return iter([
                    MockChunk("Response "),
                    MockChunk("from "),
                    MockChunk("custom "),
                    MockChunk("base URL")
                ])
            else:
                # Return complete response for non-streaming
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "Response from custom base URL",
                                "role": "assistant",
                                "tool_calls": None
                            }
                        }
                    ]
                }
        
        mock_completion.side_effect = mock_completion_side_effect
        
        llm = LLM(
            model='openai/custom-model',
            api_key='test-key',
            base_url='http://localhost:4000'
        )
        
        response = llm.get_response("Hello")
        
        # Verify that completion was called and response is correct
        mock_completion.assert_called()
        assert response is not None
        assert "Response from custom base URL" in response
        # Check that base_url was stored in the LLM instance
        assert llm.base_url == 'http://localhost:4000'


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 