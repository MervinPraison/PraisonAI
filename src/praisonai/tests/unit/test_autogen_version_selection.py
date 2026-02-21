"""
AutoGen Version Selection Tests

This test module focuses specifically on testing the version selection logic
and environment variable handling for AutoGen v0.2 and v0.4 support.
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock, patch

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))


class TestAutoGenVersionSelection:
    """Test AutoGen version selection logic"""

    @pytest.fixture
    def sample_config(self):
        """Simple config for testing"""
        return {
            'framework': 'autogen',
            'roles': {
                'assistant': {
                    'role': 'Assistant',
                    'goal': 'Help with tasks',
                    'backstory': 'Helpful assistant',
                    'tools': [],
                    'tasks': {
                        'task1': {
                            'description': 'Complete the task',
                            'expected_output': 'Task completion'
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def mock_tools_dict(self):
        """Empty tools dict for testing"""
        return {}

    def test_auto_version_prefers_v4_when_both_available(self, sample_config, mock_tools_dict):
        """Test that 'auto' version selection prefers v0.4 when both versions are available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'auto'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                mock_v4.assert_called_once()
                mock_v2.assert_not_called()
                assert result == "v4 result"

    def test_auto_version_fallback_to_v2_when_only_available(self, sample_config, mock_tools_dict):
        """Test that 'auto' version falls back to v0.2 when v0.4 is not available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'auto'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                mock_v2.assert_called_once()
                mock_v4.assert_not_called()
                assert result == "v2 result"

    def test_explicit_v4_version_selection(self, sample_config, mock_tools_dict):
        """Test explicit v0.4 version selection"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.4'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                mock_v4.assert_called_once()
                mock_v2.assert_not_called()

    def test_explicit_v2_version_selection(self, sample_config, mock_tools_dict):
        """Test explicit v0.2 version selection"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.2'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                mock_v2.assert_called_once()
                mock_v4.assert_not_called()

    def test_v4_not_available_fallback_logic(self, sample_config, mock_tools_dict):
        """Test fallback logic when v0.4 is requested but not available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.4'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                # Should fallback to v2 when v4 is not available
                mock_v2.assert_called_once()
                mock_v4.assert_not_called()

    def test_v2_not_available_fallback_logic(self, sample_config, mock_tools_dict):
        """Test fallback logic when v0.2 is requested but not available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.2'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                # Should fallback to v4 when v2 is not available
                mock_v4.assert_called_once()
                mock_v2.assert_not_called()

    def test_default_auto_version_when_env_not_set(self, sample_config, mock_tools_dict):
        """Test that default behavior is 'auto' when AUTOGEN_VERSION is not set"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {}, clear=True):  # Clear environment
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                # Should default to v4 (auto behavior)
                mock_v4.assert_called_once()
                mock_v2.assert_not_called()

    def test_invalid_version_string_fallback(self, sample_config, mock_tools_dict):
        """Test handling of invalid version strings"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'invalid-version'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                 patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                # Should fallback to auto behavior (prefer v4)
                mock_v4.assert_called_once()
                mock_v2.assert_not_called()

    def test_case_insensitive_version_strings(self, sample_config, mock_tools_dict):
        """Test that version strings are case insensitive"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        test_cases = ['V0.4', 'V0.2', 'AUTO', 'Auto', 'v0.4', 'v0.2']
        
        for version_string in test_cases:
            with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
                 patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False), \
                 patch.dict(os.environ, {'AUTOGEN_VERSION': version_string}):
                
                generator = AgentsGenerator(
                    config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                    framework='autogen'
                )
                
                with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4, \
                     patch.object(generator, '_run_autogen', return_value="v2 result") as mock_v2:
                    
                    generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                    
                    if version_string.lower() in ['v0.2']:
                        mock_v2.assert_called_once()
                        mock_v4.assert_not_called()
                    else:  # v0.4, auto, or any other string should prefer v4
                        mock_v4.assert_called_once()
                        mock_v2.assert_not_called()
                    
                    mock_v4.reset_mock()
                    mock_v2.reset_mock()

    def test_neither_version_available_raises_error(self, sample_config, mock_tools_dict):
        """Test that ImportError is raised when neither version is available"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with pytest.raises(ImportError) as exc_info:
                generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
            
            assert "AutoGen is not installed" in str(exc_info.value)
            assert "pip install praisonai[autogen]" in str(exc_info.value)
            assert "pip install praisonai[autogen-v4]" in str(exc_info.value)

    def test_agentops_tagging_for_versions(self, sample_config, mock_tools_dict):
        """Test that AgentOps is tagged correctly for different versions"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        mock_agentops = Mock()
        
        # Test v0.4 tagging
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.agentops', mock_agentops), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.4'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result"):
                generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                # Verify AgentOps was initialized with v4 tag
                mock_agentops.init.assert_called_once()
                call_args = mock_agentops.init.call_args
                assert 'autogen-v4' in call_args[1]['default_tags']
        
        mock_agentops.reset_mock()
        
        # Test v0.2 tagging
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.agentops', mock_agentops), \
             patch.dict(os.environ, {'AUTOGEN_VERSION': 'v0.2'}):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'
            )
            
            with patch.object(generator, '_run_autogen', return_value="v2 result"):
                generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                # Verify AgentOps was initialized with v2 tag
                mock_agentops.init.assert_called_once()
                call_args = mock_agentops.init.call_args
                assert 'autogen-v2' in call_args[1]['default_tags']

    def test_framework_param_override(self, sample_config, mock_tools_dict):
        """Test that framework parameter works correctly with AutoGen"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        # Test with framework='autogen' explicitly
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework='autogen'  # Explicit framework
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4:
                result = generator.generate_crew_and_kickoff(sample_config, "test", mock_tools_dict)
                
                mock_v4.assert_called_once()
                assert result == "v4 result"

    def test_config_framework_override(self, mock_tools_dict):
        """Test that config framework setting works correctly"""
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
        config_with_framework = {
            'framework': 'autogen',  # Framework specified in config
            'roles': {
                'assistant': {
                    'role': 'Assistant',
                    'goal': 'Help with tasks',
                    'backstory': 'Helpful assistant',
                    'tools': [],
                    'tasks': {
                        'task1': {
                            'description': 'Complete the task',
                            'expected_output': 'Task completion'
                        }
                    }
                }
            }
        }
        
        with patch('praisonai.praisonai.agents_generator.AUTOGEN_V4_AVAILABLE', True), \
             patch('praisonai.praisonai.agents_generator.AUTOGEN_AVAILABLE', False), \
             patch('praisonai.praisonai.agents_generator.AGENTOPS_AVAILABLE', False):
            
            generator = AgentsGenerator(
                config_list=[{'model': 'gpt-4o', 'api_key': 'test-key'}],
                framework=None  # No explicit framework, should use config
            )
            
            with patch.object(generator, '_run_autogen_v4', return_value="v4 result") as mock_v4:
                result = generator.generate_crew_and_kickoff(config_with_framework, "test", mock_tools_dict)
                
                mock_v4.assert_called_once()
                assert result == "v4 result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])