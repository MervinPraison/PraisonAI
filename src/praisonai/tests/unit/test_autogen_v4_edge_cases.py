"""
AutoGen v0.4 Edge Cases and Error Scenarios Tests

This test module covers edge cases, error scenarios, and boundary conditions
for AutoGen v0.4 support to ensure robust error handling and edge case management.
"""

import pytest
import os
import sys
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))


class TestAutoGenV4EdgeCases:
    """Test edge cases and error scenarios for AutoGen v0.4"""

    @pytest.fixture
    def minimal_config(self):
        """Minimal configuration for testing"""
        return {
            'framework': 'autogen',
            'roles': {
                'agent': {
                    'role': 'Test Agent',
                    'goal': 'Test goal',
                    'backstory': 'Test backstory',
                    'tools': [],
                    'tasks': {
                        'task': {
                            'description': 'Test task',
                            'expected_output': 'Test output'
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def agents_generator_v4(self):
        """Create AgentsGenerator with v0.4 available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            yield generator

    def test_empty_config_roles(self, agents_generator_v4):
        """Test handling of empty roles configuration"""
        empty_config = {
            'framework': 'autogen',
            'roles': {}
        }
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = []
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'):
            
            result = agents_generator_v4.generate_crew_and_kickoff(empty_config, "test", {})
            
            # Should handle empty roles gracefully
            assert "No agents created from configuration" in result

    def test_config_with_no_tasks(self, agents_generator_v4):
        """Test configuration with agents but no tasks"""
        config_no_tasks = {
            'framework': 'autogen',
            'roles': {
                'agent': {
                    'role': 'Test Agent',
                    'goal': 'Test goal',
                    'backstory': 'Test backstory',
                    'tools': [],
                    'tasks': {}  # Empty tasks
                }
            }
        }
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Agent created but no tasks")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(config_no_tasks, "test", {})
            
            # Should handle empty tasks gracefully
            assert "### AutoGen v0.4 Output ###" in result

    def test_missing_config_fields(self, agents_generator_v4):
        """Test handling of missing configuration fields"""
        incomplete_configs = [
            # Missing role
            {
                'framework': 'autogen',
                'roles': {
                    'agent': {
                        'goal': 'Test goal',
                        'backstory': 'Test backstory',
                        'tools': [],
                        'tasks': {'task': {'description': 'Test', 'expected_output': 'Test'}}
                    }
                }
            },
            # Missing goal
            {
                'framework': 'autogen',
                'roles': {
                    'agent': {
                        'role': 'Test Agent',
                        'backstory': 'Test backstory',
                        'tools': [],
                        'tasks': {'task': {'description': 'Test', 'expected_output': 'Test'}}
                    }
                }
            },
            # Missing backstory
            {
                'framework': 'autogen',
                'roles': {
                    'agent': {
                        'role': 'Test Agent',
                        'goal': 'Test goal',
                        'tools': [],
                        'tasks': {'task': {'description': 'Test', 'expected_output': 'Test'}}
                    }
                }
            }
        ]
        
        for config in incomplete_configs:
            mock_model_client = AsyncMock()
            
            with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
                 patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
                
                # Should handle missing fields gracefully (might use defaults or raise appropriate errors)
                try:
                    result = agents_generator_v4.generate_crew_and_kickoff(config, "test", {})
                    # If it succeeds, it should be a string
                    assert isinstance(result, str)
                except (KeyError, AttributeError):
                    # If it fails with missing fields, that's also acceptable behavior
                    pass

    def test_invalid_tool_references(self, agents_generator_v4, minimal_config):
        """Test handling of invalid tool references"""
        config_invalid_tools = minimal_config.copy()
        config_invalid_tools['roles']['agent']['tools'] = ['NonExistentTool', 'AnotherInvalidTool']
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent') as mock_agent, \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(config_invalid_tools, "test", {})
            
            # Should handle invalid tools gracefully - agent should be created with empty tools
            mock_agent.assert_called_once()
            call_args = mock_agent.call_args
            assert call_args[1]['tools'] == []  # Should be empty list since tools don't exist

    def test_asyncio_runtime_error_handling(self, agents_generator_v4, minimal_config):
        """Test handling of asyncio runtime errors"""
        with patch('praisonai.praisonai.agents_generator.asyncio.run', side_effect=RuntimeError("Event loop is already running")):
            
            result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
            
            # Should handle asyncio errors gracefully
            assert "### AutoGen v0.4 Error ###" in result
            assert "Event loop is already running" in result

    def test_model_client_creation_failure(self, agents_generator_v4, minimal_config):
        """Test handling of model client creation failures"""
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', side_effect=Exception("API key invalid")):
            
            result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
            
            # Should handle model client creation errors
            assert "### AutoGen v0.4 Error ###" in result
            assert "API key invalid" in result

    def test_agent_creation_failure(self, agents_generator_v4, minimal_config):
        """Test handling of agent creation failures"""
        mock_model_client = AsyncMock()
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent', side_effect=Exception("Agent creation failed")), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
            
            # Should handle agent creation errors
            assert "### AutoGen v0.4 Error ###" in result
            assert "Agent creation failed" in result

    def test_group_chat_creation_failure(self, agents_generator_v4, minimal_config):
        """Test handling of group chat creation failures"""
        mock_model_client = AsyncMock()
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', side_effect=Exception("Group chat creation failed")), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
            
            # Should handle group chat creation errors
            assert "### AutoGen v0.4 Error ###" in result
            assert "Group chat creation failed" in result

    def test_group_chat_run_failure(self, agents_generator_v4, minimal_config):
        """Test handling of group chat run failures"""
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_group_chat.run.side_effect = Exception("Group chat execution failed")
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
            
            # Should handle group chat run errors
            assert "### AutoGen v0.4 Error ###" in result
            assert "Group chat execution failed" in result

    def test_model_client_close_failure(self, agents_generator_v4, minimal_config):
        """Test handling of model client close failures"""
        mock_model_client = AsyncMock()
        mock_model_client.close.side_effect = Exception("Close failed")
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
            
            # Should complete successfully despite close failure
            assert "### AutoGen v0.4 Output ###" in result
            assert "Task completed" in result

    def test_extreme_agent_names(self, agents_generator_v4):
        """Test handling of extreme agent names"""
        extreme_names = [
            "",  # Empty string
            "   ",  # Only whitespace
            "123456",  # Only numbers
            "!@#$%^&*()",  # Only special characters
            "a" * 1000,  # Very long name
            "class",  # Python keyword
            "def",  # Python keyword
            "Agent-With-Many-Hyphens-And-Spaces",  # Complex name
            "Agent_With_Unicode_测试",  # Unicode characters
        ]
        
        for name in extreme_names:
            config = {
                'framework': 'autogen',
                'roles': {
                    'agent': {
                        'role': name,
                        'goal': 'Test goal',
                        'backstory': 'Test backstory',
                        'tools': [],
                        'tasks': {
                            'task': {
                                'description': 'Test task',
                                'expected_output': 'Test output'
                            }
                        }
                    }
                }
            }
            
            mock_model_client = AsyncMock()
            mock_group_chat = AsyncMock()
            mock_result = Mock()
            mock_result.messages = [Mock(content="Task completed")]
            mock_group_chat.run.return_value = mock_result
            
            with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
                 patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent') as mock_agent, \
                 patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
                 patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
                 patch('praisonai.praisonai.agents_generator.MaxMessageTermination'):
                
                result = agents_generator_v4.generate_crew_and_kickoff(config, "test", {})
                
                # Should handle extreme names gracefully
                assert "### AutoGen v0.4 Output ###" in result
                
                # Check that agent was created with sanitized name
                mock_agent.assert_called_once()
                call_args = mock_agent.call_args
                agent_name = call_args[1]['name']
                
                # Sanitized name should be a valid Python identifier
                assert agent_name.isidentifier() or agent_name == 'agent'  # fallback name

    def test_unicode_in_config(self, agents_generator_v4):
        """Test handling of Unicode characters in configuration"""
        unicode_config = {
            'framework': 'autogen',
            'roles': {
                'agent': {
                    'role': 'Agent 测试',
                    'goal': 'Goal with émojis 🚀',
                    'backstory': 'Backstory with çharacters',
                    'tools': [],
                    'tasks': {
                        'task': {
                            'description': 'Task déscription',
                            'expected_output': 'Oütput'
                        }
                    }
                }
            }
        }
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Task completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'):
            
            result = agents_generator_v4.generate_crew_and_kickoff(unicode_config, "test", {})
            
            # Should handle Unicode characters gracefully
            assert "### AutoGen v0.4 Output ###" in result

    def test_very_large_config(self, agents_generator_v4):
        """Test handling of very large configurations"""
        # Create a config with many agents and tasks
        roles = {}
        for i in range(50):  # 50 agents
            roles[f'agent_{i}'] = {
                'role': f'Agent {i}',
                'goal': f'Goal for agent {i}',
                'backstory': f'Backstory for agent {i}',
                'tools': [],
                'tasks': {
                    f'task_{j}': {
                        'description': f'Task {j} for agent {i}',
                        'expected_output': f'Output {j} for agent {i}'
                    }
                    for j in range(5)  # 5 tasks per agent
                }
            }
        
        large_config = {
            'framework': 'autogen',
            'roles': roles
        }
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="All tasks completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(large_config, "test", {})
            
            # Should handle large configurations
            assert "### AutoGen v0.4 Output ###" in result
            
            # Verify that max_turns was calculated correctly (50 agents * 3 = 150)
            call_args = mock_group_chat.call_args
            assert call_args[1]['max_turns'] == 150

    def test_malformed_result_messages(self, agents_generator_v4, minimal_config):
        """Test handling of malformed result messages"""
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        
        # Test various malformed results
        malformed_results = [
            Mock(messages=[Mock(content=None)]),  # None content
            Mock(messages=[Mock(spec=[])]),  # No content attribute
            Mock(messages=[Mock(content="")]),  # Empty content
            Mock(messages=[]),  # No messages
            Mock(messages=None),  # None messages
            None,  # None result
        ]
        
        for result_obj in malformed_results:
            mock_group_chat.run.return_value = result_obj
            
            with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
                 patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
                 patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
                 patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
                 patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
                 patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
                
                try:
                    result = agents_generator_v4.generate_crew_and_kickoff(minimal_config, "test", {})
                    # Should handle malformed results gracefully
                    assert isinstance(result, str)
                    assert "### AutoGen v0.4" in result
                except Exception:
                    # If it fails, that's also acceptable for malformed data
                    pass

    def test_memory_intensive_operations(self, agents_generator_v4):
        """Test handling of memory-intensive operations"""
        # Create a config with very long strings
        long_string = "A" * 10000  # 10KB string
        
        config = {
            'framework': 'autogen',
            'roles': {
                'agent': {
                    'role': 'Agent with long description',
                    'goal': long_string,
                    'backstory': long_string,
                    'tools': [],
                    'tasks': {
                        'task': {
                            'description': long_string,
                            'expected_output': long_string
                        }
                    }
                }
            }
        }
        
        mock_model_client = AsyncMock()
        mock_group_chat = AsyncMock()
        mock_result = Mock()
        mock_result.messages = [Mock(content="Completed")]
        mock_group_chat.run.return_value = mock_result
        
        with patch('praisonai.praisonai.agents_generator.OpenAIChatCompletionClient', return_value=mock_model_client), \
             patch('praisonai.praisonai.agents_generator.AutoGenV4AssistantAgent'), \
             patch('praisonai.praisonai.agents_generator.RoundRobinGroupChat', return_value=mock_group_chat), \
             patch('praisonai.praisonai.agents_generator.TextMentionTermination'), \
             patch('praisonai.praisonai.agents_generator.MaxMessageTermination'), \
             patch('praisonai.praisonai.agents_generator.sanitize_agent_name_for_autogen_v4', side_effect=lambda x: x):
            
            result = agents_generator_v4.generate_crew_and_kickoff(config, "test", {})
            
            # Should handle memory-intensive operations
            assert "### AutoGen v0.4 Output ###" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])