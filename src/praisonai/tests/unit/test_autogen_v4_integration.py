"""
AutoGen v0.4 Integration Tests

This test module provides comprehensive testing for AutoGen v0.4 support including:
- Version detection and environment variable handling
- Async execution patterns and resource management
- Tool integration and agent creation
- Backward compatibility with v0.2
- Error handling and edge cases
"""

import pytest
import os
import sys
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))

class TestAutoGenV4Integration:
    """Test AutoGen v0.4 integration functionality"""

    @pytest.fixture
    def mock_autogen_v4_imports(self):
        """Mock AutoGen v0.4 imports for testing"""
        with patch.dict('sys.modules', {
            'autogen_agentchat.agents': MagicMock(),
            'autogen_ext.models.openai': MagicMock(),
            'autogen_agentchat.teams': MagicMock(),
            'autogen_agentchat.conditions': MagicMock(),
            'autogen_agentchat.messages': MagicMock(),
            'autogen_core': MagicMock(),
        }):
            yield

    @pytest.fixture
    def mock_autogen_v2_imports(self):
        """Mock AutoGen v0.2 imports for testing"""
        with patch.dict('sys.modules', {
            'autogen': MagicMock(),
        }):
            yield

    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing"""
        return {
            'framework': 'autogen',
            'roles': {
                'researcher': {
                    'role': 'Research Specialist for {topic}',
                    'goal': 'Conduct thorough research on {topic}',
                    'backstory': 'Expert researcher with deep knowledge in {topic}',
                    'tools': ['WebsiteSearchTool', 'FileReadTool'],
                    'tasks': {
                        'research_task': {
                            'description': 'Research the latest developments in {topic}',
                            'expected_output': 'Comprehensive research report on {topic}'
                        }
                    }
                },
                'writer': {
                    'role': 'Content Writer for {topic}',
                    'goal': 'Create engaging content about {topic}',
                    'backstory': 'Professional writer specializing in {topic}',
                    'tools': ['FileReadTool'],
                    'tasks': {
                        'writing_task': {
                            'description': 'Write a summary of research findings on {topic}',
                            'expected_output': 'Well-written summary document'
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def sample_tools_dict(self):
        """Sample tools dictionary for testing"""
        mock_tool1 = Mock()
        mock_tool1.run = Mock(return_value="Tool 1 result")
        
        mock_tool2 = Mock()
        mock_tool2.run = Mock(return_value="Tool 2 result")
        
        return {
            'WebsiteSearchTool': mock_tool1,
            'FileReadTool': mock_tool2
        }

    @pytest.fixture
    def agents_generator_v4(self, mock_autogen_v4_imports):
        """Create AgentsGenerator instance with v0.4 available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Mock the availability flags
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            yield generator

    @pytest.fixture
    def agents_generator_both_versions(self, mock_autogen_v4_imports, mock_autogen_v2_imports):
        """Create AgentsGenerator instance with both versions available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Mock the availability flags
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            yield generator

    def test_version_detection_auto_prefers_v4(self, agents_generator_both_versions, sample_config, sample_tools_dict):
        """Test that 'auto' version selection prefers v0.4 when both are available"""
        with patch.dict(os.environ, {'AUTOGEN_VERSION': 'auto'}), \
             patch.object(agents_generator_both_versions, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
             patch.object(agents_generator_both_versions, '_run_autogen', return_value="v2 result") as mock_v2:
            
            result = agents_generator_both_versions.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            mock_v4.assert_called_once()
            mock_v2.assert_not_called()
            assert result == "v4 result"

    def test_version_detection_explicit_v4(self, agents_generator_both_versions, sample_config, sample_tools_dict):
        """Test explicit v0.4 version selection"""
        with patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.4'}), \
             patch.object(agents_generator_both_versions, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
             patch.object(agents_generator_both_versions, '_run_autogen', return_value="v2 result") as mock_v2:
            
            result = agents_generator_both_versions.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            mock_v4.assert_called_once()
            mock_v2.assert_not_called()
            assert result == "v4 result"

    def test_version_detection_explicit_v2(self, agents_generator_both_versions, sample_config, sample_tools_dict):
        """Test explicit v0.2 version selection"""
        with patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.2'}), \
             patch.object(agents_generator_both_versions, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
             patch.object(agents_generator_both_versions, '_run_autogen', return_value="v2 result") as mock_v2:
            
            result = agents_generator_both_versions.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            mock_v2.assert_called_once()
            mock_v4.assert_not_called()
            assert result == "v2 result"

    def test_version_detection_fallback_to_v4_only(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test fallback when only v0.4 is available"""
        with patch.dict(os.environ, {'AUTOGEN_VERSION': 'auto'}), \
             patch.object(agents_generator_v4, '_run_autogen_v4', return_value="v4 result") as mock_v4:
            
            result = agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            mock_v4.assert_called_once()
            assert result == "v4 result"

    def test_missing_autogen_import_error(self):
        """Test that ImportError is raised when AutoGen is not available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with pytest.raises(ImportError, match="AutoGen is not installed"):
                generator.generate_crew_and_kickoff({}, "test", {})

    @pytest.mark.asyncio
    async def test_autogen_v4_async_execution(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test the async execution pattern of AutoGen v0.4"""
        
        # Mock the v0.4 components
        mock_model_client = AsyncMock()
        mock_assistant = Mock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Test completion result")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent', return_value=mock_assistant), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination') as mock_text_term, \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination') as mock_max_term, \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x.replace(' ', '_')):
            
            result = agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify model client was created
            assert mock_model_client is not None
            
            # Verify group chat was run
            mock_group_chat.run.assert_called_once()
            
            # Verify model client was closed
            mock_model_client.close.assert_called_once()
            
            # Verify result format
            assert "### AutoGen v0.4 Output ###" in result

    def test_autogen_v4_tool_integration(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test tool integration for AutoGen v0.4"""
        
        mock_model_client = AsyncMock()
        mock_assistant_class = Mock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent', mock_assistant_class), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x.replace(' ', '_')):
            
            agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify that tools were passed to agents
            call_args = mock_assistant_class.call_args_list
            assert len(call_args) == 2  # Two agents created
            
            # Check that tools were properly passed
            for call in call_args:
                kwargs = call[1]
                if 'tools' in kwargs:
                    tools = kwargs['tools']
                    # Should contain the run methods of the tools
                    assert len(tools) > 0

    def test_autogen_v4_error_handling(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test error handling in AutoGen v0.4 execution"""
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_group_chat.run.side_effect = Exception("Test execution error")
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x.replace(' ', '_')):
            
            result = agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify error is handled gracefully
            assert "### AutoGen v0.4 Error ###" in result
            assert "Test execution error" in result
            
            # Verify cleanup occurred
            mock_model_client.close.assert_called_once()

    def test_autogen_v4_asyncio_run_error_handling(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test handling of asyncio.run() errors"""
        
        with patch('praisonai.praisonai.agents_generator.asyncio.run', side_effect=RuntimeError("Event loop error")):
            
            result = agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify error is handled gracefully
            assert "### AutoGen v0.4 Error ###" in result
            assert "Event loop error" in result

    def test_autogen_v4_agent_name_sanitization(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test agent name sanitization for AutoGen v0.4"""
        
        mock_model_client = AsyncMock()
        mock_assistant_class = Mock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent', mock_assistant_class), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4') as mock_sanitize:
            
            mock_sanitize.side_effect = lambda x: x.replace(' ', '_').replace('-', '_')
            
            agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify sanitization was called
            assert mock_sanitize.call_count == 2  # Once for each agent

    def test_autogen_v4_termination_conditions(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test that proper termination conditions are set for v0.4"""
        
        mock_model_client = AsyncMock()
        mock_group_chat_class = Mock()
        mock_group_chat = AsyncMock()
        mock_group_chat_class.return_value = mock_group_chat
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        mock_text_termination = Mock()
        mock_max_termination = Mock()
        mock_combined_termination = Mock()
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', mock_group_chat_class), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination', return_value=mock_text_termination), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination', return_value=mock_max_termination), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x.replace(' ', '_')):
            
            # Mock the OR operation for termination conditions
            mock_text_termination.__or__ = Mock(return_value=mock_combined_termination)
            
            agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify termination conditions were created
            mock_text_termination.__or__.assert_called_once_with(mock_max_termination)
            
            # Verify group chat was created with termination condition
            call_args = mock_group_chat_class.call_args
            kwargs = call_args[1]
            assert 'termination_condition' in kwargs
            assert kwargs['termination_condition'] == mock_combined_termination

    def test_autogen_v4_model_config_handling(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test model configuration handling for v0.4"""
        
        # Test with custom model config
        agents_generator_v4.config_list = [
            {
                'model': 'gpt-4-turbo',
                'api_key': 'custom-key',
                'base_url': 'https://custom.openai.com/v1'
            }
        ]
        
        mock_model_client_class = Mock()
        mock_model_client = AsyncMock()
        mock_model_client_class.return_value = mock_model_client
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', mock_model_client_class), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x.replace(' ', '_')):
            
            agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify model client was created with correct config
            mock_model_client_class.assert_called_once_with(
                model='gpt-4-turbo',
                api_key='custom-key',
                base_url='https://custom.openai.com/v1'
            )

    def test_autogen_v4_empty_config_list_handling(self, agents_generator_v4, sample_config, sample_tools_dict):
        """Test handling of empty config_list for v0.4"""
        
        # Set empty config list
        agents_generator_v4.config_list = []
        
        mock_model_client_class = Mock()
        mock_model_client = AsyncMock()
        mock_model_client_class.return_value = mock_model_client
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', mock_model_client_class), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x.replace(' ', '_')), \
             patch.dict(os.environ, {'OPENAI_API_KEY': 'env-key'}):
            
            agents_generator_v4.generate_crew_and_kickoff(
                sample_config, "AI research", sample_tools_dict
            )
            
            # Verify fallback to default values
            mock_model_client_class.assert_called_once_with(
                model='gpt-4o',  # default model
                api_key='env-key',  # from environment
                base_url='https://api.openai.com/v1'  # default base_url
            )

if __name__ == "__main__":
    pytest.main([__file__, "-v"])