import pytest
import os
import sys
import asyncio
import warnings
import gc
from unittest.mock import Mock, patch

# Register pytest plugins
pytest_plugins = (
    'pytest_asyncio',
    'tests._pytest_plugins.test_gating',
    'tests._pytest_plugins.network_guard',
)

# Suppress aiohttp unclosed session warnings during tests
warnings.filterwarnings("ignore", message="Unclosed client session")
warnings.filterwarnings("ignore", message="Unclosed connector")

@pytest.fixture(scope="function")
def event_loop():
    """Create a function-scoped event loop for async tests.
    
    This matches pytest.ini's asyncio_default_fixture_loop_scope=function.
    Required for fixtures that use async operations.
    """
    policy = asyncio.DefaultEventLoopPolicy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()



@pytest.fixture(autouse=True)
def cleanup_async_resources():
    """Clean up async resources after each test to prevent unclosed session warnings.
    
    Note: We only do garbage collection here. Event loop management is handled
    by pytest-asyncio's event_loop fixture. Calling run_until_complete here
    can corrupt the event loop state and cause subsequent tests to fail.
    """
    yield
    # Force garbage collection to clean up any lingering async resources
    gc.collect()

# Add the source paths to sys.path for imports
# praisonai-agents package (core SDK)
_agents_path = os.path.join(os.path.dirname(__file__), '..', '..', 'praisonai-agents')
if _agents_path not in sys.path:
    sys.path.insert(0, _agents_path)
# praisonai wrapper package
_wrapper_path = os.path.join(os.path.dirname(__file__), '..')
if _wrapper_path not in sys.path:
    sys.path.insert(0, _wrapper_path)

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
            'model': 'gpt-5-nano',
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
    try:
        import duckduckgo_search  # noqa: F401 - Check if available
    except ImportError:
        pytest.skip("duckduckgo_search not installed")
    
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
    
    # Check if this test is marked as a real test, network test, or provider test
    if hasattr(request, 'node') and hasattr(request.node, 'iter_markers'):
        for marker in request.node.iter_markers():
            if marker.name in ('real', 'network', 'e2e') or marker.name.startswith('provider_'):
                is_real_test = True
                break
    
    # Also check if the test file is in the integration/live/e2e directory
    if hasattr(request, 'fspath') and request.fspath:
        test_path = str(request.fspath)
        if '/integration/' in test_path or '\\integration\\' in test_path:
            is_real_test = True
        if '/live/' in test_path or '\\live\\' in test_path:
            is_real_test = True
        if '/e2e/' in test_path or '\\e2e\\' in test_path:
            is_real_test = True
    
    # Store original values to restore later
    original_values = {}
    
    if not is_real_test:
        # Set test environment variables only for mock tests
        test_keys = {
            'OPENAI_API_KEY': 'test-key',
            'ANTHROPIC_API_KEY': 'test-key', 
            'GOOGLE_API_KEY': 'test-key',
            'XAI_API_KEY': 'test-key',
            'GROQ_API_KEY': 'test-key',
            'COHERE_API_KEY': 'test-key',
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


@pytest.fixture(autouse=True)
def fast_sleep(request, monkeypatch):
    """
    Replace time.sleep and asyncio.sleep with near-instant versions for unit tests.
    
    This fixture is automatically applied to all tests but can be disabled by:
    - Marking the test with @pytest.mark.allow_sleep
    - Marking the test with @pytest.mark.integration, @pytest.mark.e2e, or @pytest.mark.local_service
    - Marking the test with @pytest.mark.flaky
    """
    # Check if test should use real sleep
    if hasattr(request, 'node') and hasattr(request.node, 'iter_markers'):
        for marker in request.node.iter_markers():
            if marker.name in ('allow_sleep', 'integration', 'e2e', 'local_service', 'flaky'):
                return  # Don't patch sleep for these tests
    
    # Check path-based exclusions
    if hasattr(request, 'fspath') and request.fspath:
        test_path = str(request.fspath)
        if any(p in test_path for p in ['/integration/', '/e2e/', '/live/']):
            return  # Don't patch sleep for integration/e2e/live tests
    
    import time
    import asyncio
    
    # Patch time.sleep to be near-instant (0.001s max)
    original_sleep = time.sleep
    def fast_time_sleep(seconds):
        original_sleep(min(seconds, 0.001))
    monkeypatch.setattr(time, 'sleep', fast_time_sleep)
    
    # Patch asyncio.sleep to be near-instant
    original_async_sleep = asyncio.sleep
    async def fast_async_sleep(seconds):
        await original_async_sleep(min(seconds, 0.001))
    monkeypatch.setattr(asyncio, 'sleep', fast_async_sleep) 
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        report.duration = call.stop - call.start

def pytest_report_teststatus(report, config):
    """Add duration to the test status output if it's a call report."""
    if report.when == 'call':
        duration = getattr(report, 'duration', 0)
        category, short, verbose = '', '', ''
        if report.passed:
            category = 'passed'
        elif report.failed:
            category = 'failed'
        elif report.skipped:
            category = 'skipped'
        
        if category:
            return category, short, f"{report.outcome.upper()} ({duration:.4f}s)"
    return None
