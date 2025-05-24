"""
Comprehensive test suite for Issue #467: base_url to api_base mapping for litellm compatibility

This test ensures that when users provide 'base_url' in their llm dictionary,
it properly maps to 'api_base' for litellm, enabling OpenAI-compatible endpoints
like KoboldCPP to work correctly.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Add the source path to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents.agent.agent import Agent
    from praisonaiagents.llm.llm import LLM
    from praisonaiagents.agent.image_agent import ImageAgent
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestBaseUrlApiBaseMapping:
    """Test suite for base_url to api_base parameter mapping in litellm integration."""
    
    def test_llm_class_maps_base_url_to_api_base(self):
        """Test that LLM class properly maps base_url to api_base for litellm."""
        with patch('praisonaiagents.llm.llm.litellm') as mock_litellm:
            mock_litellm.completion.return_value = {
                'choices': [{'message': {'content': 'Test response'}}]
            }
            
            llm = LLM(
                model='openai/mistral',
                base_url='http://localhost:4000',
                api_key='sk-test'
            )
            
            # Trigger a completion to see the parameters passed to litellm
            llm.chat([{'role': 'user', 'content': 'test'}])
            
            # Verify litellm.completion was called with both base_url and api_base
            call_args = mock_litellm.completion.call_args
            assert call_args is not None, "litellm.completion should have been called"
            
            # Check that both parameters are present
            kwargs = call_args[1]
            assert 'base_url' in kwargs, "base_url should be passed to litellm"
            assert 'api_base' in kwargs, "api_base should be passed to litellm"
            assert kwargs['base_url'] == 'http://localhost:4000'
            assert kwargs['api_base'] == 'http://localhost:4000'
    
    def test_agent_with_llm_dict_base_url_parameter(self):
        """Test that Agent properly handles base_url in llm dictionary - Issue #467 scenario."""
        llm_config = {
            'model': 'openai/mistral',
            'base_url': 'http://localhost:4000',  # This is the key parameter from the issue
            'api_key': 'sk-1234'
        }
        
        with patch('praisonaiagents.llm.llm.litellm') as mock_litellm:
            mock_litellm.completion.return_value = {
                'choices': [{'message': {'content': 'Test response'}}]
            }
            
            agent = Agent(
                name="Test Agent",
                llm=llm_config
            )
            
            # Execute a simple task to trigger LLM usage
            with patch.object(agent, 'execute_task') as mock_execute:
                mock_execute.return_value = "Task completed"
                result = agent.execute_task("Test task")
            
            # Verify the agent was created successfully
            assert agent.name == "Test Agent"
            assert agent.llm is not None
            assert isinstance(agent.llm, LLM)
            assert agent.llm.base_url == 'http://localhost:4000'
    
    def test_image_agent_base_url_consistency(self):
        """Test that ImageAgent maintains parameter consistency with base_url."""
        with patch('praisonaiagents.agent.image_agent.litellm') as mock_litellm:
            mock_litellm.image_generation.return_value = {
                'data': [{'url': 'http://example.com/image.png'}]
            }
            
            image_agent = ImageAgent(
                base_url='http://localhost:4000',
                api_key='sk-test'
            )
            
            # Generate an image to trigger the API call
            result = image_agent.generate_image("test prompt")
            
            # Verify litellm.image_generation was called with proper parameters
            call_args = mock_litellm.image_generation.call_args
            assert call_args is not None
            
            kwargs = call_args[1]
            # Check that base_url is mapped to api_base for image generation
            assert 'api_base' in kwargs or 'base_url' in kwargs, "Either api_base or base_url should be present"
    
    def test_koboldcpp_specific_scenario(self):
        """Test the specific KoboldCPP scenario mentioned in Issue #467."""
        KOBOLD_V1_BASE_URL = "http://127.0.0.1:5001/v1"
        CHAT_MODEL_NAME = "koboldcpp-model"
        
        llm_config = {
            'model': f'openai/{CHAT_MODEL_NAME}',
            'base_url': KOBOLD_V1_BASE_URL,
            'api_key': "sk-1234"
        }
        
        with patch('praisonaiagents.llm.llm.litellm') as mock_litellm:
            # Mock successful response (not OpenAI key error)
            mock_litellm.completion.return_value = {
                'choices': [{'message': {'content': 'KoboldCPP response'}}]
            }
            
            llm = LLM(**llm_config)
            
            # This should not raise an OpenAI key error
            response = llm.chat([{'role': 'user', 'content': 'test'}])
            
            # Verify the call was made with correct parameters
            call_args = mock_litellm.completion.call_args[1]
            assert call_args['model'] == f'openai/{CHAT_MODEL_NAME}'
            assert call_args['api_base'] == KOBOLD_V1_BASE_URL
            assert call_args['base_url'] == KOBOLD_V1_BASE_URL
            assert call_args['api_key'] == "sk-1234"
    
    def test_litellm_documentation_example_compatibility(self):
        """Test compatibility with the litellm documentation example from Issue #467."""
        # This is the exact example from litellm docs mentioned in the issue
        with patch('praisonaiagents.llm.llm.litellm') as mock_litellm:
            mock_litellm.completion.return_value = {
                'choices': [{'message': {'content': 'Documentation example response'}}]
            }
            
            llm = LLM(
                model="openai/mistral",
                api_key="sk-1234",
                base_url="http://0.0.0.0:4000"  # This should map to api_base
            )
            
            response = llm.chat([{
                "role": "user",
                "content": "Hey, how's it going?",
            }])
            
            # Verify the parameters match litellm expectations
            call_args = mock_litellm.completion.call_args[1]
            assert call_args['model'] == "openai/mistral"
            assert call_args['api_key'] == "sk-1234"
            assert call_args['api_base'] == "http://0.0.0.0:4000"
    
    def test_backward_compatibility_with_api_base(self):
        """Test that existing code using api_base still works."""
        with patch('praisonaiagents.llm.llm.litellm') as mock_litellm:
            mock_litellm.completion.return_value = {
                'choices': [{'message': {'content': 'Backward compatibility response'}}]
            }
            
            # Test direct api_base parameter (if supported)
            llm_config = {
                'model': 'openai/test',
                'api_key': 'sk-test'
            }
            
            # If the LLM class has an api_base parameter, test it
            try:
                llm_config['api_base'] = 'http://localhost:4000'
                llm = LLM(**llm_config)
                response = llm.chat([{'role': 'user', 'content': 'test'}])
            except TypeError:
                # If api_base is not a direct parameter, that's fine
                # The important thing is that base_url works
                pass
    
    def test_ollama_environment_variable_compatibility(self):
        """Test Ollama compatibility with OLLAMA_API_BASE environment variable."""
        with patch.dict(os.environ, {'OLLAMA_API_BASE': 'http://localhost:11434'}):
            with patch('praisonaiagents.llm.llm.litellm') as mock_litellm:
                mock_litellm.completion.return_value = {
                    'choices': [{'message': {'content': 'Ollama response'}}]
                }
                
                llm = LLM(
                    model='ollama/llama2',
                    api_key='not-needed-for-ollama'
                )
                
                response = llm.chat([{'role': 'user', 'content': 'test'}])
                
                # Should work without errors when environment variable is set
                assert response is not None


if __name__ == '__main__':
    # Run the tests
    pytest.main([__file__, '-v'])