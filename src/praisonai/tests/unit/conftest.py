import pytest
import os
import sys
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock, mock_open
from typing import Dict, Any, List
from pathlib import Path

# Dynamically add the source path to sys.path for imports
current_dir = Path(__file__).parent
src_path = current_dir.parent.parent / 'praisonai-agents'
if src_path.exists():
    sys.path.insert(0, str(src_path))

# Common test constants
TEST_API_KEY = 'test-api-key-123'
TEST_MODEL = 'gpt-4o-mini'
TEST_TIMEOUT = 5  # seconds

@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return {
        'choices': [{'message': {'content': 'Test response from LLM'}}]
    }

@pytest.fixture
def mock_llm_streaming_response():
    """Mock streaming LLM response for testing."""
    def stream_generator():
        chunks = ["Test ", "streaming ", "response"]
        for chunk in chunks:
            yield {'choices': [{'delta': {'content': chunk}}]}
    return stream_generator()

@pytest.fixture
def sample_agent_config():
    """Sample agent configuration for testing."""
    return {
        'name': 'TestAgent',
        'role': 'Test Specialist',
        'goal': 'Perform testing tasks',
        'backstory': 'An expert testing agent',
        'llm': {
            'model': TEST_MODEL,
            'api_key': TEST_API_KEY
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
def mock_file_system():
    """Mock file system operations."""
    mock_file = mock_open(read_data="test file content")
    with patch('builtins.open', mock_file):
        yield mock_file

@pytest.fixture
def mock_async_sleep():
    """Mock asyncio.sleep to speed up tests."""
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        mock_sleep.return_value = None
        yield mock_sleep

@pytest.fixture
def mock_time_sleep():
    """Mock time.sleep to speed up tests."""
    with patch('time.sleep') as mock_sleep:
        mock_sleep.return_value = None
        yield mock_sleep

@pytest.fixture
def mock_subprocess():
    """Mock subprocess calls."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout='Success',
            stderr=''
        )
        yield mock_run

@pytest.fixture
def mock_network_calls():
    """Mock common network libraries."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post, \
         patch('httpx.AsyncClient') as mock_httpx:
        
        # Setup default responses
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'status': 'success'},
            text='Success'
        )
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {'status': 'success'}
        )
        
        yield {
            'get': mock_get,
            'post': mock_post,
            'httpx': mock_httpx
        }

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client with proper spec."""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="Test response"))],
        usage=Mock(total_tokens=100)
    )
    return mock_client

@pytest.fixture
def mock_litellm():
    """Mock LiteLLM for LLM operations."""
    with patch('litellm.completion') as mock_completion:
        mock_completion.return_value = Mock(
            choices=[Mock(message=Mock(content="Test response"))],
            usage=Mock(total_tokens=100)
        )
        yield mock_completion

@pytest.fixture
def temp_directory(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path

@pytest.fixture(autouse=True)
def setup_test_environment(request, monkeypatch):
    """Setup test environment before each test."""
    # Check if this test is marked as a real test
    is_real_test = request.node.get_closest_marker('real') is not None
    
    if not is_real_test:
        # Set test environment variables only for mock tests
        test_env_vars = {
            'OPENAI_API_KEY': TEST_API_KEY,
            'ANTHROPIC_API_KEY': TEST_API_KEY, 
            'GOOGLE_API_KEY': TEST_API_KEY,
            'OLLAMA_API_BASE': 'http://localhost:11434',
            'PRAISON_LOG_LEVEL': 'ERROR',  # Reduce log noise in tests
            'PRAISON_TEST_MODE': 'true'
        }
        
        for key, value in test_env_vars.items():
            monkeypatch.setenv(key, value)
    
    # Mock external services that shouldn't run in tests
    with patch('posthog.capture') as mock_posthog:
        mock_posthog.return_value = None
        yield

@pytest.fixture
def mock_all_external_services(
    mock_vector_store,
    mock_duckduckgo,
    mock_file_system,
    mock_network_calls,
    mock_subprocess,
    mock_litellm
):
    """Convenience fixture that mocks all external services."""
    return {
        'vector_store': mock_vector_store,
        'duckduckgo': mock_duckduckgo,
        'file_system': mock_file_system,
        'network': mock_network_calls,
        'subprocess': mock_subprocess,
        'litellm': mock_litellm
    }

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks after each test."""
    yield
    # This runs after each test
    patch.stopall()

@pytest.fixture
def async_test_timeout():
    """Set a timeout for async tests to prevent hanging."""
    return TEST_TIMEOUT

# Test markers
pytest_markers = [
    "real: mark test as using real external services",
    "slow: mark test as slow running",
    "integration: mark test as integration test",
    "unit: mark test as unit test",
]

def pytest_configure(config):
    """Register custom markers."""
    for marker in pytest_markers:
        config.addinivalue_line("markers", marker)