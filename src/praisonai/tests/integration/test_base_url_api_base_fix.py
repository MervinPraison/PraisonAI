"""Issue #467: a configured base_url must reach the litellm call.

Measured against `_build_completion_params`, the endpoint is forwarded as
`base_url` and `api_base` is never set, so the historical "maps to api_base"
framing is stale. What matters, and what these tests now assert, is that the
endpoint survives into the kwargs litellm is called with. The test names are
kept as-is because they are referenced from the issue.

Every test here is fully mocked and makes no network call, hence the module-level
`offline` marker: without it the gating plugin infers `network` from the provider
names appearing in the file and CI deselects all of them.
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


# Every test in this module patches litellm and makes no network call.
pytestmark = pytest.mark.offline


def make_completion_response(text="Test response"):
    """A litellm.completion stand-in the LLM tool-calling loop can consume.

    A bare dict is NOT sufficient: the loop reads ``.choices[0].message`` and a
    dict raises ``'str' object has no attribute 'choices'`` -- which is why four
    of these tests failed the moment they were actually executed.
    """
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.choices[0].message.tool_calls = None
    resp.choices[0].finish_reason = "stop"
    return resp


class TestBaseUrlApiBaseMapping:
    """Test suite for base_url to api_base parameter mapping in litellm integration."""
    
    @patch('litellm.completion')
    def test_llm_class_maps_base_url_to_api_base(self, mock_completion):
        """Test that LLM class properly maps base_url to api_base for litellm."""
        mock_completion.return_value = make_completion_response()
        
        llm = LLM(
            model='openai/mistral',
            base_url='http://localhost:4000',
            api_key='sk-test'
        )
        
        # Test that LLM instance was created with base_url
        assert llm.base_url == 'http://localhost:4000'
        assert llm.model == 'openai/mistral'
        assert llm.api_key == 'sk-test'
        
        # Trigger a completion 
        llm.get_response("test", stream=False)
        
        # Verify litellm.completion was called
        kwargs = mock_completion.call_args.kwargs
        assert 'model' in kwargs, 'litellm was called without a model'
        assert kwargs['base_url'] == 'http://localhost:4000'
        assert kwargs['api_key'] == 'sk-test'
        assert kwargs['model'] == 'openai/mistral'
    
    @patch('litellm.completion')
    def test_agent_with_llm_dict_base_url_parameter(self, mock_completion):
        """Test that Agent properly handles base_url in llm dictionary - Issue #467 scenario."""
        llm_config = {
            'model': 'openai/mistral',
            'base_url': 'http://localhost:4000',  # This is the key parameter from the issue
            'api_key': 'sk-1234'
        }
        
        mock_completion.return_value = make_completion_response()
        
        agent = Agent(
            name="Test Agent",
            llm=llm_config
        )
        
        # Verify the agent was created successfully
        assert agent.name == "Test Agent"
        assert hasattr(agent, 'llm_instance')
        assert isinstance(agent.llm_instance, LLM)
        assert agent.llm_instance.base_url == 'http://localhost:4000'
    
    @patch('litellm.image_generation')
    def test_image_agent_base_url_consistency(self, mock_image_generation):
        """Test that ImageAgent maintains parameter consistency with api_base."""
        mock_image_generation.return_value = {
            'data': [{'url': 'http://example.com/image.png'}]
        }
        
        image_agent = ImageAgent(
            api_base='http://localhost:4000',
            api_key='sk-test'
        )
        
        # Verify that ImageAgent was created with api_base
        assert image_agent.image_config.api_base == 'http://localhost:4000'
        assert image_agent.image_config.api_key == 'sk-test'
    
    @patch('litellm.completion')
    def test_koboldcpp_specific_scenario(self, mock_completion):
        """Test the specific KoboldCPP scenario mentioned in Issue #467."""
        KOBOLD_V1_BASE_URL = "http://127.0.0.1:5001/v1"
        CHAT_MODEL_NAME = "koboldcpp-model"
        
        llm_config = {
            'model': f'openai/{CHAT_MODEL_NAME}',
            'base_url': KOBOLD_V1_BASE_URL,
            'api_key': "sk-1234"
        }
        
        # Mock successful response (not OpenAI key error)
        mock_completion.return_value = make_completion_response()
        
        llm = LLM(**llm_config)
        
        # Verify LLM was created with correct parameters
        assert llm.model == f'openai/{CHAT_MODEL_NAME}'
        assert llm.base_url == KOBOLD_V1_BASE_URL
        assert llm.api_key == "sk-1234"
        
        # This should not raise an OpenAI key error
        response = llm.get_response("test", stream=False)
        
        # Verify that completion was called
        kwargs = mock_completion.call_args.kwargs
        assert 'model' in kwargs, 'litellm was called without a model'
        assert kwargs['base_url'] == "http://127.0.0.1:5001/v1"
    
    @patch('litellm.completion')
    def test_litellm_documentation_example_compatibility(self, mock_completion):
        """Test compatibility with the litellm documentation example from Issue #467."""
        # This is the exact example from litellm docs mentioned in the issue
        mock_completion.return_value = make_completion_response()
        
        llm = LLM(
            model="openai/mistral",
            api_key="sk-1234",
            base_url="http://0.0.0.0:4000"  # This should map to api_base
        )
        
        # Verify the parameters are stored correctly
        assert llm.model == "openai/mistral"
        assert llm.api_key == "sk-1234"
        assert llm.base_url == "http://0.0.0.0:4000"
        
        response = llm.get_response("Hey, how's it going?")
        
        # Verify that completion was called
        kwargs = mock_completion.call_args.kwargs
        assert 'model' in kwargs, 'litellm was called without a model'
        assert kwargs['base_url'] == "http://0.0.0.0:4000"
    
    @patch('litellm.completion')
    def test_backward_compatibility_with_api_base(self, mock_completion):
        """Test that existing code using api_base still works."""
        mock_completion.return_value = make_completion_response()
        
        # Test basic LLM functionality works
        llm_config = {
            'model': 'openai/test',
            'api_key': 'sk-test',
            'base_url': 'http://localhost:4000'
        }
        
        llm = LLM(**llm_config)
        assert llm.model == 'openai/test'
        assert llm.api_key == 'sk-test'
        assert llm.base_url == 'http://localhost:4000'
    
    @patch('litellm.completion')
    def test_ollama_environment_variable_compatibility(self, mock_completion):
        """Test Ollama compatibility with OLLAMA_API_BASE environment variable."""
        with patch.dict(os.environ, {'OLLAMA_API_BASE': 'http://localhost:11434'}):
            mock_completion.return_value = make_completion_response('Ollama response')
            
            llm = LLM(
                model='ollama/llama2',
                api_key='not-needed-for-ollama'
            )
            
            # Verify LLM creation works
            assert llm.model == 'ollama/llama2'
            assert llm.api_key == 'not-needed-for-ollama'
            
            response = llm.get_response("test", stream=False)
            
            # Should work without errors when environment variable is set
            kwargs = mock_completion.call_args.kwargs
            assert 'model' in kwargs, 'litellm was called without a model'
            assert kwargs['model'] == 'ollama/llama2'
            # No base_url was configured on this LLM, so none must be injected.
            assert not kwargs.get('base_url')


if __name__ == '__main__':
    # Run the tests
    pytest.main([__file__, '-v'])