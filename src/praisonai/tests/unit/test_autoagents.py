"""
Unit tests for AutoAgents class
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import json
import logging

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai-agents'))

try:
    from praisonaiagents.agents.autoagents import AutoAgents, AutoAgentsConfig, AgentConfig, TaskConfig
    from praisonaiagents.llm import OpenAIClient, LLM
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestAutoAgents:
    """Test suite for AutoAgents functionality"""
    
    @pytest.fixture
    def sample_valid_config(self):
        """Fixture providing a valid AutoAgentsConfig"""
        return AutoAgentsConfig(
            main_instruction="Create a blog post about AI",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Research Agent",
                    role="Researcher",
                    goal="Research AI topics",
                    backstory="Expert researcher",
                    tools=["web_search"],
                    tasks=[
                        TaskConfig(
                            name="Research Task",
                            description="Research latest AI trends",
                            expected_output="Research summary",
                            tools=["web_search"]
                        )
                    ]
                ),
                AgentConfig(
                    name="Writer Agent",
                    role="Writer",
                    goal="Write blog post",
                    backstory="Professional writer",
                    tools=["text_editor"],
                    tasks=[
                        TaskConfig(
                            name="Writing Task",
                            description="Write blog post based on research",
                            expected_output="Complete blog post",
                            tools=["text_editor"]
                        )
                    ]
                )
            ]
        )
    
    @pytest.fixture
    def sample_invalid_config_string_tasks(self):
        """Fixture providing an invalid config with string tasks"""
        return {
            "main_instruction": "Create a blog post about AI",
            "process_type": "sequential",
            "agents": [
                {
                    "name": "Research Agent",
                    "role": "Researcher",
                    "goal": "Research AI topics",
                    "backstory": "Expert researcher",
                    "tools": ["web_search"],
                    "tasks": ["Research latest AI trends"]  # Invalid: string instead of object
                }
            ]
        }
    
    @pytest.fixture
    def sample_invalid_config_missing_fields(self):
        """Fixture providing an invalid config with missing task fields"""
        return AutoAgentsConfig(
            main_instruction="Create a blog post about AI",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Research Agent",
                    role="Researcher",
                    goal="Research AI topics",
                    backstory="Expert researcher",
                    tools=["web_search"],
                    tasks=[
                        TaskConfig(
                            name="Research Task",
                            description="",  # Missing description
                            expected_output="Research summary",
                            tools=["web_search"]
                        )
                    ]
                )
            ]
        )
    
    @pytest.fixture
    def mock_tools(self):
        """Fixture providing mock tools"""
        web_search = Mock()
        web_search.__name__ = "web_search"
        
        text_editor = Mock()
        text_editor.__name__ = "text_editor"
        
        return [web_search, text_editor]
    
    def test_validate_config_success(self, sample_valid_config):
        """Test successful validation of a valid configuration"""
        # Create AutoAgents instance without calling __init__ to avoid API calls
        auto_agents = object.__new__(AutoAgents)
        
        # Initialize only the necessary attributes for validation
        auto_agents.instructions = "Test instructions"
        auto_agents.max_agents = 3
        
        is_valid, error_msg = auto_agents._validate_config(sample_valid_config)
        
        assert is_valid is True
        assert error_msg == ""
    
    def test_validate_config_failure_not_taskconfig(self):
        """Test validation failure when task is not a TaskConfig instance"""
        # Create AutoAgents instance without calling __init__ to avoid API calls
        auto_agents = object.__new__(AutoAgents)
        
        # Initialize only the necessary attributes for validation
        auto_agents.instructions = "Test instructions"
        auto_agents.max_agents = 3
        
        # Create a valid config first, then modify it to bypass Pydantic validation
        config = AutoAgentsConfig(
            main_instruction="Test",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Agent",
                    role="Role",
                    goal="Goal",
                    backstory="Story",
                    tools=[],
                    tasks=[
                        TaskConfig(
                            name="Valid Task",
                            description="Valid description", 
                            expected_output="Valid output",
                            tools=[]
                        )
                    ]
                )
            ]
        )
        
        # Now manually replace the task with a string to simulate the error condition
        config.agents[0].tasks = ["This is a string task"]
        
        is_valid, error_msg = auto_agents._validate_config(config)
        
        assert is_valid is False
        assert "is not a proper TaskConfig object" in error_msg
    
    def test_validate_config_failure_missing_name(self):
        """Test validation failure when task is missing name"""
        # Create AutoAgents instance without calling __init__ to avoid API calls
        auto_agents = object.__new__(AutoAgents)
        
        # Initialize only the necessary attributes for validation
        auto_agents.instructions = "Test instructions"
        auto_agents.max_agents = 3
        
        config = AutoAgentsConfig(
            main_instruction="Test",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Agent",
                    role="Role",
                    goal="Goal",
                    backstory="Story",
                    tools=[],
                    tasks=[
                        TaskConfig(
                            name="",  # Empty name
                            description="Description",
                            expected_output="Output",
                            tools=[]
                        )
                    ]
                )
            ]
        )
        
        is_valid, error_msg = auto_agents._validate_config(config)
        
        assert is_valid is False
        assert "has no name" in error_msg
    
    def test_validate_config_failure_missing_description(self, sample_invalid_config_missing_fields):
        """Test validation failure when task is missing description"""
        # Create AutoAgents instance without calling __init__ to avoid API calls
        auto_agents = object.__new__(AutoAgents)
        
        # Initialize only the necessary attributes for validation
        auto_agents.instructions = "Test instructions"
        auto_agents.max_agents = 3
        
        is_valid, error_msg = auto_agents._validate_config(sample_invalid_config_missing_fields)
        
        assert is_valid is False
        assert "has no description" in error_msg
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.get_openai_client')
    def test_generate_config_openai_success(self, mock_get_client, mock_supports_structured, sample_valid_config, mock_tools):
        """Test successful config generation using OpenAI structured output"""
        # Mock support for structured outputs
        mock_supports_structured.return_value = True
        
        # Mock OpenAI client
        mock_client = Mock(spec=OpenAIClient)
        mock_client.parse_structured_output.return_value = sample_valid_config
        mock_get_client.return_value = mock_client
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init:
            
            # Mock the return value of _create_agents_and_tasks
            mock_create.return_value = ([], [])  # Empty agents and tasks lists
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Create a blog post about AI",
                tools=mock_tools,
                max_agents=2,
                llm="gpt-4"
            )
            
            # Verify OpenAI client was called
            mock_client.parse_structured_output.assert_called_once()
            mock_create.assert_called_once_with(sample_valid_config)
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.LLM')
    def test_generate_config_llm_success(self, mock_llm_class, mock_supports_structured, sample_valid_config, mock_tools):
        """Test successful config generation using generic LLM"""
        # Mock no support for structured outputs to force LLM path
        mock_supports_structured.return_value = False
        
        # Mock LLM instance
        mock_llm = Mock()
        mock_llm.get_response.return_value = json.dumps(sample_valid_config.model_dump())
        mock_llm_class.return_value = mock_llm
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init:
            
            # Mock the return value of _create_agents_and_tasks
            mock_create.return_value = ([], [])  # Empty agents and tasks lists
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Create a blog post about AI",
                tools=mock_tools,
                max_agents=2,
                llm="claude-3"  # Non-OpenAI model
            )
            
            # Verify LLM was called
            mock_llm.get_response.assert_called_once()
            mock_create.assert_called_once_with(sample_valid_config)
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.LLM')
    def test_generate_config_with_markdown_response(self, mock_llm_class, mock_supports_structured, sample_valid_config, mock_tools):
        """Test config generation when LLM returns markdown-wrapped JSON"""
        # Mock no support for structured outputs to force LLM path
        mock_supports_structured.return_value = False
        
        # Mock LLM instance
        mock_llm = Mock()
        # Return JSON wrapped in markdown code block
        wrapped_response = f"```json\n{json.dumps(sample_valid_config.model_dump(), indent=2)}\n```"
        mock_llm.get_response.return_value = wrapped_response
        mock_llm_class.return_value = mock_llm
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init:
            
            # Mock the return value of _create_agents_and_tasks
            mock_create.return_value = ([], [])  # Empty agents and tasks lists
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Create a blog post about AI",
                tools=mock_tools,
                max_agents=2,
                llm="claude-3"
            )
            
            # The config should have been generated successfully despite markdown wrapping
            mock_create.assert_called_once_with(sample_valid_config)
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.get_openai_client')
    def test_generate_config_retry_on_validation_failure(self, mock_get_client, mock_supports_structured, sample_valid_config, mock_tools):
        """Test retry mechanism when validation fails"""
        # Mock support for structured outputs
        mock_supports_structured.return_value = True
        
        # Mock OpenAI client
        mock_client = Mock(spec=OpenAIClient)
        
        # First attempt: return invalid config with string tasks
        invalid_config = AutoAgentsConfig(
            main_instruction="Test",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Agent",
                    role="Role",
                    goal="Goal",
                    backstory="Story",
                    tools=[],
                    tasks=[]  # This will be mocked to contain strings
                )
            ]
        )
        # Mock the tasks to be strings (bypassing Pydantic validation)
        invalid_config.agents[0].tasks = ["Invalid string task"]
        
        # Second attempt: return valid config
        mock_client.parse_structured_output.side_effect = [invalid_config, sample_valid_config]
        mock_get_client.return_value = mock_client
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init, \
             patch('logging.warning') as mock_warning:
            
            # Mock the return value of _create_agents_and_tasks
            mock_create.return_value = ([], [])  # Empty agents and tasks lists
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Create a blog post about AI",
                tools=mock_tools,
                max_agents=2,
                llm="gpt-4"
            )
            
            # Verify retry occurred
            assert mock_client.parse_structured_output.call_count == 2
            mock_warning.assert_called_once()
            assert "Configuration validation failed" in str(mock_warning.call_args)
            mock_create.assert_called_once_with(sample_valid_config)
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.get_openai_client')
    def test_generate_config_max_retries_exceeded(self, mock_get_client, mock_supports_structured, mock_tools):
        """Test that max retries are properly enforced"""
        # Mock support for structured outputs
        mock_supports_structured.return_value = True
        
        # Mock OpenAI client
        mock_client = Mock(spec=OpenAIClient)
        
        # Always return invalid config
        invalid_config = AutoAgentsConfig(
            main_instruction="Test",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Agent",
                    role="Role",
                    goal="Goal",
                    backstory="Story",
                    tools=[],
                    tasks=[]
                )
            ]
        )
        # Mock the tasks to be strings
        invalid_config.agents[0].tasks = ["Invalid string task"]
        
        mock_client.parse_structured_output.return_value = invalid_config
        mock_get_client.return_value = mock_client
        
        with pytest.raises(ValueError, match="Configuration validation failed after 3 attempts"):
            AutoAgents(
                instructions="Create a blog post about AI",
                tools=mock_tools,
                max_agents=2,
                llm="gpt-4"
            )
        
        # Verify all retries were attempted
        assert mock_client.parse_structured_output.call_count == 3
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.get_openai_client')
    def test_max_agents_truncation(self, mock_get_client, mock_supports_structured, mock_tools):
        """Test that agents are truncated when exceeding max_agents"""
        # Mock support for structured outputs
        mock_supports_structured.return_value = True
        
        # Create config with 4 agents
        config_with_many_agents = AutoAgentsConfig(
            main_instruction="Test",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name=f"Agent {i}",
                    role="Role",
                    goal="Goal",
                    backstory="Story",
                    tools=[],
                    tasks=[
                        TaskConfig(
                            name=f"Task {i}",
                            description="Description",
                            expected_output="Output",
                            tools=[]
                        )
                    ]
                )
                for i in range(4)
            ]
        )
        
        mock_client = Mock(spec=OpenAIClient)
        mock_client.parse_structured_output.return_value = config_with_many_agents
        mock_get_client.return_value = mock_client
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init:
            
            # Mock the return value of _create_agents_and_tasks
            mock_agents = [Mock() for _ in range(2)]  # Only 2 agents after truncation
            for i, agent in enumerate(mock_agents):
                agent.name = f"Agent {i}"
            mock_create.return_value = (mock_agents, [])
            mock_super_init.return_value = None
            
            # Create AutoAgents with max_agents=2
            auto_agents = AutoAgents(
                instructions="Test",
                tools=mock_tools,
                max_agents=2,
                llm="gpt-4"
            )
            
            # Check that config was truncated before being passed to _create_agents_and_tasks
            call_args = mock_create.call_args[0][0]  # Get the config argument
            assert len(call_args.agents) == 2
            assert call_args.agents[0].name == "Agent 0"
            assert call_args.agents[1].name == "Agent 1"
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.get_openai_client')
    def test_insufficient_agents_warning(self, mock_get_client, mock_supports_structured, mock_tools):
        """Test warning when fewer agents than max_agents are generated"""
        # Mock support for structured outputs
        mock_supports_structured.return_value = True
        
        # Create config with only 1 agent
        config_with_few_agents = AutoAgentsConfig(
            main_instruction="Test",
            process_type="sequential",
            agents=[
                AgentConfig(
                    name="Single Agent",
                    role="Role",
                    goal="Goal",
                    backstory="Story",
                    tools=[],
                    tasks=[
                        TaskConfig(
                            name="Task",
                            description="Description",
                            expected_output="Output",
                            tools=[]
                        )
                    ]
                )
            ]
        )
        
        mock_client = Mock(spec=OpenAIClient)
        mock_client.parse_structured_output.return_value = config_with_few_agents
        mock_get_client.return_value = mock_client
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init, \
             patch('logging.warning') as mock_warning:
            
            # Mock the return value of _create_agents_and_tasks
            mock_agents = [Mock()]
            mock_agents[0].name = "Single Agent"
            mock_create.return_value = (mock_agents, [])
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Test",
                tools=mock_tools,
                max_agents=3,
                llm="gpt-4"
            )
            
            # Verify warning was logged
            mock_warning.assert_called()
            warning_msg = str(mock_warning.call_args)
            assert "Generated 1 agents, expected 3" in warning_msg
    
    def test_max_agents_validation(self):
        """Test max_agents parameter validation"""
        # Test too low
        with pytest.raises(ValueError, match="max_agents must be at least 1"):
            AutoAgents(instructions="Test", max_agents=0)
        
        # Test too high
        with pytest.raises(ValueError, match="max_agents cannot exceed 10"):
            AutoAgents(instructions="Test", max_agents=11)
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.LLM')
    def test_retry_with_previous_response_in_prompt(self, mock_llm_class, mock_supports_structured, sample_valid_config, mock_tools):
        """Test that retry includes previous response and error in prompt"""
        # Mock no support for structured outputs to force LLM path
        mock_supports_structured.return_value = False
        
        # Mock LLM instance
        mock_llm = Mock()
        
        # First response: invalid JSON that will fail validation
        first_response = json.dumps({
            "main_instruction": "Test",
            "process_type": "sequential",
            "agents": [{
                "name": "Agent",
                "role": "Role",
                "goal": "Goal",
                "backstory": "Story",
                "tools": [],
                "tasks": ["String task instead of object"]
            }]
        })
        
        # Second response: valid config
        second_response = json.dumps(sample_valid_config.model_dump())
        
        mock_llm.get_response.side_effect = [first_response, second_response]
        mock_llm_class.return_value = mock_llm
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init:
            
            # Mock the return value of _create_agents_and_tasks
            mock_create.return_value = ([], [])  # Empty agents and tasks lists
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Create a blog post about AI",
                tools=mock_tools,
                max_agents=2,
                llm="claude-3"
            )
            
            # Check that the second call included the previous response
            assert mock_llm.get_response.call_count == 2
            second_call_kwargs = mock_llm.get_response.call_args_list[1][1]
            assert "PREVIOUS ATTEMPT FAILED!" in second_call_kwargs['prompt']
            assert first_response in second_call_kwargs['prompt']
            assert "Error:" in second_call_kwargs['prompt']
            mock_create.assert_called_once_with(sample_valid_config)
    
    @patch('praisonaiagents.llm.supports_structured_outputs')
    @patch('praisonaiagents.agents.autoagents.OpenAIClient')
    @patch('praisonaiagents.agents.autoagents.get_openai_client')
    def test_custom_api_key_and_base_url(self, mock_get_client, mock_openai_class, mock_supports_structured, sample_valid_config, mock_tools):
        """Test that custom API key and base URL are used correctly"""
        # Mock support for structured outputs
        mock_supports_structured.return_value = True
        
        # Mock OpenAI client instance
        mock_client = Mock(spec=OpenAIClient)
        mock_client.parse_structured_output.return_value = sample_valid_config
        mock_openai_class.return_value = mock_client
        
        custom_api_key = "custom-api-key"
        custom_base_url = "https://custom.api.url"
        
        with patch.object(AutoAgents, '_create_agents_and_tasks') as mock_create, \
             patch.object(AutoAgents, '_display_agents_and_tasks') as mock_display, \
             patch('praisonaiagents.agents.agents.PraisonAIAgents.__init__') as mock_super_init:
            
            # Mock the return value of _create_agents_and_tasks
            mock_create.return_value = ([], [])  # Empty agents and tasks lists
            mock_super_init.return_value = None
            
            auto_agents = AutoAgents(
                instructions="Test",
                tools=mock_tools,
                max_agents=2,
                llm="gpt-4",
                api_key=custom_api_key,
                base_url=custom_base_url
            )
            
            # Verify custom client was created with correct parameters
            mock_openai_class.assert_called_once_with(
                api_key=custom_api_key,
                base_url=custom_base_url
            )
            
            # Verify get_openai_client was not called
            mock_get_client.assert_not_called()