"""
Comprehensive mock management for PraisonAI unit tests.

This module provides centralized mock management to ensure proper isolation
of external dependencies and consistent mocking across the test suite.
"""
import os
from typing import Any, Dict, List, Optional, Callable
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from contextlib import contextmanager
import pytest


class ExternalServiceMocker:
    """Centralized management of external service mocks."""
    
    @staticmethod
    @contextmanager
    def mock_all_external_services():
        """Context manager that mocks all external services."""
        with ExternalServiceMocker.mock_posthog(), \
             ExternalServiceMocker.mock_litellm(), \
             ExternalServiceMocker.mock_network_calls(), \
             ExternalServiceMocker.mock_file_operations(), \
             ExternalServiceMocker.mock_subprocess_calls(), \
             ExternalServiceMocker.mock_database_operations():
            yield
    
    @staticmethod
    @contextmanager
    def mock_posthog():
        """Mock PostHog analytics to prevent tracking in tests."""
        with patch('posthog.capture') as mock_capture, \
             patch('posthog.identify') as mock_identify, \
             patch('posthog.alias') as mock_alias:
            mock_capture.return_value = None
            mock_identify.return_value = None
            mock_alias.return_value = None
            yield {
                'capture': mock_capture,
                'identify': mock_identify,
                'alias': mock_alias
            }
    
    @staticmethod
    @contextmanager
    def mock_litellm():
        """Mock LiteLLM for all LLM operations."""
        mock_response = Mock(
            choices=[Mock(
                message=Mock(content="Mocked LLM response"),
                finish_reason="stop"
            )],
            usage=Mock(total_tokens=100, prompt_tokens=50, completion_tokens=50),
            model="gpt-4o-mini"
        )
        
        with patch('litellm.completion') as mock_completion, \
             patch('litellm.acompletion') as mock_acompletion, \
             patch('litellm.stream_chunk_builder') as mock_stream:
            mock_completion.return_value = mock_response
            mock_acompletion.return_value = mock_response
            mock_stream.return_value = [mock_response]
            yield {
                'completion': mock_completion,
                'acompletion': mock_acompletion,
                'stream': mock_stream
            }
    
    @staticmethod
    @contextmanager
    def mock_network_calls():
        """Mock all network-related calls."""
        mock_response = Mock(
            status_code=200,
            json=lambda: {"status": "success"},
            text="Success",
            content=b"Success"
        )
        
        with patch('requests.get', return_value=mock_response) as mock_get, \
             patch('requests.post', return_value=mock_response) as mock_post, \
             patch('requests.put', return_value=mock_response) as mock_put, \
             patch('requests.delete', return_value=mock_response) as mock_delete, \
             patch('httpx.AsyncClient') as mock_httpx, \
             patch('urllib.request.urlopen') as mock_urlopen:
            
            # Setup httpx mock
            mock_httpx_instance = AsyncMock()
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance
            mock_httpx_instance.get.return_value = mock_response
            mock_httpx_instance.post.return_value = mock_response
            
            # Setup urlopen mock
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b"Success"
            
            yield {
                'requests': {
                    'get': mock_get,
                    'post': mock_post,
                    'put': mock_put,
                    'delete': mock_delete
                },
                'httpx': mock_httpx,
                'urlopen': mock_urlopen
            }
    
    @staticmethod
    @contextmanager
    def mock_file_operations():
        """Mock file system operations."""
        from unittest.mock import mock_open
        
        mock_file_content = "Mock file content"
        mock_file = mock_open(read_data=mock_file_content)
        
        with patch('builtins.open', mock_file) as mock_open_func, \
             patch('os.path.exists', return_value=True) as mock_exists, \
             patch('os.makedirs') as mock_makedirs, \
             patch('os.remove') as mock_remove, \
             patch('shutil.rmtree') as mock_rmtree, \
             patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('pathlib.Path.exists', return_value=True) as mock_path_exists:
            
            yield {
                'open': mock_open_func,
                'exists': mock_exists,
                'makedirs': mock_makedirs,
                'remove': mock_remove,
                'rmtree': mock_rmtree,
                'mkdir': mock_mkdir,
                'path_exists': mock_path_exists
            }
    
    @staticmethod
    @contextmanager
    def mock_subprocess_calls():
        """Mock subprocess operations."""
        mock_result = Mock(
            returncode=0,
            stdout="Success",
            stderr="",
            communicate=lambda: ("Success", "")
        )
        
        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch('subprocess.Popen', return_value=mock_result) as mock_popen, \
             patch('subprocess.check_output', return_value=b"Success") as mock_check_output:
            
            yield {
                'run': mock_run,
                'popen': mock_popen,
                'check_output': mock_check_output
            }
    
    @staticmethod
    @contextmanager
    def mock_database_operations():
        """Mock database operations for various backends."""
        with patch('chromadb.Client') as mock_chromadb, \
             patch('sqlite3.connect') as mock_sqlite, \
             patch('psycopg2.connect') as mock_postgres, \
             patch('pymongo.MongoClient') as mock_mongo:
            
            # Setup ChromaDB mock
            mock_collection = Mock()
            mock_collection.query.return_value = {
                'documents': [['Mock document']],
                'metadatas': [[{'source': 'test'}]]
            }
            mock_chromadb.return_value.get_or_create_collection.return_value = mock_collection
            
            # Setup SQLite mock
            mock_sqlite_conn = Mock()
            mock_sqlite_cursor = Mock()
            mock_sqlite_conn.cursor.return_value = mock_sqlite_cursor
            mock_sqlite.return_value = mock_sqlite_conn
            
            yield {
                'chromadb': mock_chromadb,
                'sqlite': mock_sqlite,
                'postgres': mock_postgres,
                'mongo': mock_mongo
            }


class EnvironmentManager:
    """Manage environment variables for tests."""
    
    @staticmethod
    @contextmanager
    def test_environment(custom_vars: Optional[Dict[str, str]] = None):
        """Set up test environment variables."""
        default_vars = {
            'OPENAI_API_KEY': 'test-openai-key',
            'ANTHROPIC_API_KEY': 'test-anthropic-key',
            'GOOGLE_API_KEY': 'test-google-key',
            'OLLAMA_API_BASE': 'http://localhost:11434',
            'PRAISON_TEST_MODE': 'true',
            'PRAISON_LOG_LEVEL': 'ERROR',
            'POSTHOG_API_KEY': 'test-posthog-key',
            'DISABLE_TELEMETRY': 'true'
        }
        
        if custom_vars:
            default_vars.update(custom_vars)
        
        # Store original values
        original_values = {}
        for key in default_vars:
            original_values[key] = os.environ.get(key)
        
        # Set test values
        for key, value in default_vars.items():
            os.environ[key] = value
        
        try:
            yield default_vars
        finally:
            # Restore original values
            for key, original_value in original_values.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value


class MockValidator:
    """Validate mock usage and prevent common mistakes."""
    
    @staticmethod
    def assert_no_real_api_calls(mock_dict: Dict[str, Any]):
        """Ensure no real API calls were made."""
        network_mocks = mock_dict.get('network', {})
        
        if isinstance(network_mocks, dict):
            for method, mock in network_mocks.items():
                if hasattr(mock, 'called') and mock.called:
                    # Check if the call was to a real API endpoint
                    for call in mock.call_args_list:
                        url = call[0][0] if call[0] else None
                        if url and any(domain in str(url) for domain in [
                            'openai.com', 'anthropic.com', 'google.com', 
                            'api.github.com', 'pypi.org'
                        ]):
                            pytest.fail(f"Real API call detected to: {url}")
    
    @staticmethod
    def assert_mocks_called_correctly(mocks: Dict[str, Any], expected_calls: Dict[str, int]):
        """Verify mocks were called the expected number of times."""
        for mock_name, expected_count in expected_calls.items():
            if mock_name in mocks:
                mock_obj = mocks[mock_name]
                actual_count = mock_obj.call_count if hasattr(mock_obj, 'call_count') else 0
                assert actual_count == expected_count, \
                    f"Mock '{mock_name}' called {actual_count} times, expected {expected_count}"


# Pytest fixtures using the mock management

@pytest.fixture
def mock_external_services():
    """Fixture that mocks all external services."""
    with ExternalServiceMocker.mock_all_external_services():
        yield


@pytest.fixture
def test_env():
    """Fixture that sets up test environment variables."""
    with EnvironmentManager.test_environment() as env:
        yield env


@pytest.fixture
def mock_llm_only():
    """Fixture that only mocks LLM services."""
    with ExternalServiceMocker.mock_litellm() as mocks:
        yield mocks


@pytest.fixture
def mock_with_validation():
    """Fixture that provides mocks with validation capabilities."""
    all_mocks = {}
    
    with ExternalServiceMocker.mock_all_external_services():
        # Collect all mocks for validation
        with ExternalServiceMocker.mock_network_calls() as network_mocks:
            all_mocks['network'] = network_mocks
            
            yield all_mocks, MockValidator()


# Decorators for common test patterns

def mock_all_external(test_func: Callable) -> Callable:
    """Decorator to mock all external services for a test."""
    def wrapper(*args, **kwargs):
        with ExternalServiceMocker.mock_all_external_services():
            return test_func(*args, **kwargs)
    return wrapper


def with_test_env(**env_vars):
    """Decorator to set test environment variables."""
    def decorator(test_func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            with EnvironmentManager.test_environment(env_vars):
                return test_func(*args, **kwargs)
        return wrapper
    return decorator