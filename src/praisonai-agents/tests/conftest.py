"""
Pytest configuration for PraisonAI Agents tests.

Provides fixtures and markers for testing, including:
- live: Tests that require real API keys (opt-in)
- slow: Tests that take longer to run
- asyncio: Async test support (works with or without pytest-asyncio)
"""

import asyncio
import inspect
import os
import sys
import pytest

# Add the local package to the path for development testing
_package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _package_root not in sys.path:
    sys.path.insert(0, _package_root)

# Check if pytest-asyncio is installed (without importing it)
import importlib.util
_PYTEST_ASYNCIO_INSTALLED = importlib.util.find_spec("pytest_asyncio") is not None


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """
    Run async test functions using asyncio.run() when pytest-asyncio is not installed.
    This allows async tests to work in minimal environments without pytest-asyncio.
    When pytest-asyncio IS installed, defer to it by returning None.
    """
    if _PYTEST_ASYNCIO_INSTALLED:
        # Let pytest-asyncio handle it
        return None
    
    # Check if this is an async function
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        # Get the function and its arguments
        testfunction = pyfuncitem.obj
        funcargs = pyfuncitem.funcargs
        
        # Filter to only include parameters the function accepts
        sig = inspect.signature(testfunction)
        filtered_args = {
            k: v for k, v in funcargs.items() 
            if k in sig.parameters
        }
        
        # Run the async function
        asyncio.run(testfunction(**filtered_args))
        return True
    
    return None


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live: mark test as requiring real API keys (deselect with '-m \"not live\"')"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (handled by local plugin when pytest-asyncio not installed)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless PRAISONAI_LIVE_TESTS=1 is set."""
    if os.environ.get("PRAISONAI_LIVE_TESTS") != "1":
        skip_live = pytest.mark.skip(reason="Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable.")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment, skip if not available."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.fixture
def live_test_enabled():
    """Check if live tests are enabled."""
    if os.environ.get("PRAISONAI_LIVE_TESTS") != "1":
        pytest.skip("Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable.")
    return True
