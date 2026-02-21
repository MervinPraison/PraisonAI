"""
AutoGen Backward Compatibility Tests

This test module ensures that the introduction of AutoGen v0.4 support
maintains full backward compatibility with existing v0.2 implementations.
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock, patch

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))


class TestAutoGenBackwardCompatibility:
    """Test backward compatibility between AutoGen v0.2 and v0.4"""

    @pytest.fixture
    def v2_config(self):
        """Configuration that should work with both v0.2 and v0.4"""
        return {
            'framework': 'autogen',
            'roles': {
                'researcher': {
                    'role': 'Research Specialist',
                    'goal': 'Conduct research on {topic}',
                    'backstory': 'Expert researcher with years of experience',
                    'tools': ['WebsiteSearchTool', 'FileReadTool'],
                    'tasks': {
                        'research_task': {
                            'description': 'Research the given topic thoroughly',
                            'expected_output': 'Comprehensive research report'
                        }
                    }
                },
                'writer': {
                    'role': 'Content Writer',
                    'goal': 'Write content about {topic}',
                    'backstory': 'Professional content writer',
                    'tools': ['FileReadTool'],
                    'tasks': {
                        'writing_task': {
                            'description': 'Write a well-structured article',
                            'expected_output': 'High-quality article'
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def mock_tools_dict(self):
        """Mock tools that should work with both versions"""
        mock_tool1 = Mock()
        mock_tool1.run = Mock(return_value="Tool 1 result")
        
        mock_tool2 = Mock()
        mock_tool2.run = Mock(return_value="Tool 2 result")
        
        return {
            'WebsiteSearchTool': mock_tool1,
            'FileReadTool': mock_tool2
        }

    def test_same_config_works_with_both_versions(self, v2_config, mock_tools_dict):
        """Test that the same configuration works with both v0.2 and v0.4"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Test with v0.2 only
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                result = generator.generate_crew_and_kickoff(v2_config, "AI", mock_tools_dict)
                mock_v2.assert_called_once()
                assert result == "v2 result"
        
        # Test with v0.4 only
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4:
                result = generator.generate_crew_and_kickoff(v2_config, "AI", mock_tools_dict)
                mock_v4.assert_called_once()
                assert result == "v4 result"

    def test_existing_v2_code_continues_working(self, v2_config, mock_tools_dict):
        """Test that existing v0.2 code continues to work without modification"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Simulate existing v0.2 deployment with no environment variable set
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {}, clear=True):  # No AUTOGEN_VERSION set
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                result = generator.generate_crew_and_kickoff(v2_config, "AI", mock_tools_dict)
                mock_v2.assert_called_once()
                assert result == "v2 result"

    def test_no_breaking_changes_in_api(self, v2_config, mock_tools_dict):
        """Test that the API remains unchanged for existing code"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # The constructor should work the same way
        generator = AgentsGenerator(
            config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
            framework='autogen'
        )
        
        # The main method should have the same signature
        assert hasattr(generator, 'generate_crew_and_kickoff')
        
        # Test that the method still accepts the same parameters
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            with patch.object(generator, '_run_autogen', return_value="v2 result"):
                # This should work exactly as before
                result = generator.generate_crew_and_kickoff(v2_config, "AI", mock_tools_dict)
                assert isinstance(result, str)

    def test_tool_compatibility_between_versions(self, v2_config, mock_tools_dict):
        """Test that tools work consistently across both versions"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Test that the same tools work with both versions
        for version_available, version_name in [(True, 'v4'), (False, 'v2')]:
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', version_available), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', not version_available), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework='autogen'
                )
                
                method_name = f'_run_autogen_v4' if version_available else '_run_autogen'
                with patch.object(generator, method_name, return_value=f"{version_name} result") as mock_method:
                    result = generator.generate_crew_and_kickoff(v2_config, "AI", mock_tools_dict)
                    
                    # Verify the method was called with the tools
                    mock_method.assert_called_once()
                    call_args = mock_method.call_args
                    assert call_args[0][2] == mock_tools_dict  # tools_dict parameter

    def test_config_structure_compatibility(self, mock_tools_dict):
        """Test that different config structures are handled consistently"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Test various config structures that should work with both versions
        configs = [
            # Simple config
            {
                'framework': 'autogen',
                'roles': {
                    'agent': {
                        'role': 'Simple Agent',
                        'goal': 'Simple goal',
                        'backstory': 'Simple backstory',
                        'tools': [],
                        'tasks': {
                            'task': {
                                'description': 'Simple task',
                                'expected_output': 'Simple output'
                            }
                        }
                    }
                }
            },
            # Config with topic placeholders
            {
                'framework': 'autogen',
                'roles': {
                    'agent': {
                        'role': 'Agent for {topic}',
                        'goal': 'Work on {topic}',
                        'backstory': 'Expert in {topic}',
                        'tools': [],
                        'tasks': {
                            'task': {
                                'description': 'Handle {topic}',
                                'expected_output': 'Result for {topic}'
                            }
                        }
                    }
                }
            },
            # Config with multiple agents
            {
                'framework': 'autogen',
                'roles': {
                    'agent1': {
                        'role': 'First Agent',
                        'goal': 'First goal',
                        'backstory': 'First backstory',
                        'tools': [],
                        'tasks': {
                            'task1': {
                                'description': 'First task',
                                'expected_output': 'First output'
                            }
                        }
                    },
                    'agent2': {
                        'role': 'Second Agent',
                        'goal': 'Second goal',
                        'backstory': 'Second backstory',
                        'tools': [],
                        'tasks': {
                            'task2': {
                                'description': 'Second task',
                                'expected_output': 'Second output'
                            }
                        }
                    }
                }
            }
        ]
        
        for config in configs:
            # Test with v0.2
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework='autogen'
                )
                
                with patch.object(generator, '_run_autogen', return_value="v2 result"):
                    result = generator.generate_crew_and_kickoff(config, "test", mock_tools_dict)
                    assert result == "v2 result"
            
            # Test with v0.4
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework='autogen'
                )
                
                with patch.object(generator, '_run_autogen_v4', return_value="v4 result"):
                    result = generator.generate_crew_and_kickoff(config, "test", mock_tools_dict)
                    assert result == "v4 result"

    def test_error_handling_consistency(self, v2_config, mock_tools_dict):
        """Test that error handling is consistent between versions"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Test ImportError when no AutoGen is available
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with pytest.raises(ImportError) as exc_info:
                generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
            
            # Should mention both installation options
            error_msg = str(exc_info.value)
            assert "AutoGen is not installed" in error_msg
            assert "pip install praisonai[autogen]" in error_msg
            assert "pip install praisonai[autogen-v4]" in error_msg

    def test_config_list_handling_consistency(self, v2_config, mock_tools_dict):
        """Test that config_list is handled consistently across versions"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        test_config_lists = [
            # Single config
            [{'model': 'gpt-4o', 'api_key': 'test-key'}],
            # Multiple configs
            [
                {'model': 'gpt-4o', 'api_key': 'test-key1'},
                {'model': 'gpt-4o-mini', 'api_key': 'test-key2'}
            ],
            # Config with base_url
            [{'model': 'gpt-4o', 'api_key': 'test-key', 'base_url': 'https://api.openai.com/v1'}]
        ]
        
        for config_list in test_config_lists:
            # Test with v0.2
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=config_list,
                    framework='autogen'
                )
                
                with patch.object(generator, '_run_autogen', return_value="v2 result"):
                    result = generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
                    assert result == "v2 result"
            
            # Test with v0.4
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=config_list,
                    framework='autogen'
                )
                
                with patch.object(generator, '_run_autogen_v4', return_value="v4 result"):
                    result = generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
                    assert result == "v4 result"

    def test_framework_parameter_compatibility(self, v2_config, mock_tools_dict):
        """Test that framework parameter handling remains consistent"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Test different ways to specify framework
        test_cases = [
            # Framework in constructor
            {'constructor_framework': 'autogen', 'config_framework': None},
            # Framework in config
            {'constructor_framework': None, 'config_framework': 'autogen'},
            # Framework in both (constructor should take precedence)
            {'constructor_framework': 'autogen', 'config_framework': 'crewai'},
        ]
        
        for case in test_cases:
            config = v2_config.copy()
            if case['config_framework']:
                config['framework'] = case['config_framework']
            elif 'framework' in config:
                del config['framework']
            
            # Test with v0.2
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework=case['constructor_framework']
                )
                
                with patch.object(generator, '_run_autogen', return_value="v2 result"):
                    result = generator.generate_crew_and_kickoff(config, "test", mock_tools_dict)
                    assert result == "v2 result"
            
            # Test with v0.4
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework=case['constructor_framework']
                )
                
                with patch.object(generator, '_run_autogen_v4', return_value="v4 result"):
                    result = generator.generate_crew_and_kickoff(config, "test", mock_tools_dict)
                    assert result == "v4 result"

    def test_output_format_consistency(self, v2_config, mock_tools_dict):
        """Test that output format remains consistent for existing code"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Both versions should return string results
        for version_available, expected_prefix in [(True, "### AutoGen v0.4 Output ###"), (False, "")]:
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', version_available), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', not version_available), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework='autogen'
                )
                
                method_name = f'_run_autogen_v4' if version_available else '_run_autogen'
                test_result = "Test result content"
                expected_result = f"{expected_prefix}\n{test_result}" if expected_prefix else test_result
                
                with patch.object(generator, method_name, return_value=expected_result):
                    result = generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
                    
                    # Both versions should return strings
                    assert isinstance(result, str)
                    # v0.4 should have its prefix, v0.2 should not
                    if version_available:
                        assert "### AutoGen v0.4 Output ###" in result
                    else:
                        assert "### AutoGen v0.4 Output ###" not in result

    def test_migration_path_smooth(self, v2_config, mock_tools_dict):
        """Test that migration from v0.2 to v0.4 is smooth"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Step 1: Existing v0.2 deployment
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen', return_value="v2 result"):
                result = generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
                assert result == "v2 result"
        
        # Step 2: Install v0.4 alongside v0.2 (should default to v0.4)
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result"):
                result = generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
                assert result == "v4 result"
        
        # Step 3: Force v0.2 if needed for compatibility
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.2'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen', return_value="v2 result"):
                result = generator.generate_crew_and_kickoff(v2_config, "test", mock_tools_dict)
                assert result == "v2 result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])