import pytest
import os
import sys
import asyncio
from unittest.mock import Mock, patch
from typing import Dict, Any, List

# Add the source path to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'praisonai-agents'))

@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return {
        'choices': [{'message': {'content': 'Test response from LLM'}}]
    }

@pytest.fixture
def sample_agent_config():
    """Sample agent configuration for testing."""
    return {
        'name': 'TestAgent',
        'role': 'Test Specialist',
        'goal': 'Perform testing tasks',
        'backstory': 'An expert testing agent',
        'llm': {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
    }

@pytest.fixture
def sample_task_config():
    """Sample task configuration for testing."""
    return {
        'name': 'test_task',
        'description': 'A test task',
        'expected_output': 'Test output'
    }

@pytest.fixture
def mock_vector_store():
    """Mock vector store for RAG testing."""
    with patch('chromadb.Client') as mock_client:
        mock_collection = Mock()
        mock_collection.query.return_value = {
            'documents': [['Sample document content']],
            'metadatas': [[{'source': 'test.pdf'}]]
        }
        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        yield mock_client

@pytest.fixture
def mock_duckduckgo():
    """Mock DuckDuckGo search for testing."""
    with patch('duckduckgo_search.DDGS') as mock_ddgs:
        mock_instance = mock_ddgs.return_value
        mock_instance.text.return_value = [
            {
                'title': 'Test Result 1',
                'href': 'https://example.com/1',
                'body': 'Test content 1'
            },
            {
                'title': 'Test Result 2', 
                'href': 'https://example.com/2',
                'body': 'Test content 2'
            }
        ]
        yield mock_ddgs



@pytest.fixture
def temp_directory(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path

@pytest.fixture(autouse=True)
def setup_test_environment(request):
    """Setup test environment before each test."""
    # Only set test API keys for non-real tests
    # Real tests (marked with @pytest.mark.real) should use actual environment variables
    is_real_test = False
    
    # Check if this test is marked as a real test
    if hasattr(request, 'node') and hasattr(request.node, 'iter_markers'):
        for marker in request.node.iter_markers():
            if marker.name == 'real':
                is_real_test = True
                break
    
    # Store original values to restore later
    original_values = {}
    
    if not is_real_test:
        # Set test environment variables only for mock tests
        test_keys = {
            'OPENAI_API_KEY': 'test-key',
            'ANTHROPIC_API_KEY': 'test-key', 
            'GOOGLE_API_KEY': 'test-key'
        }
        
        for key, value in test_keys.items():
            original_values[key] = os.environ.get(key)
            os.environ[key] = value
    
    yield
    
    # Cleanup after test - restore original values
    if not is_real_test:
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value 