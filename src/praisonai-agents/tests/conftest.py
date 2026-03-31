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


# =============================================================================
# GLOBAL STATE CLEANUP FIXTURES (autouse)
# =============================================================================
# These fixtures prevent test pollution from global mutable state.
# They run automatically before each test to reset shared registries.
# =============================================================================

@pytest.fixture(autouse=True)
def _reset_circuit_breaker_registry():
    """Reset the global circuit breaker registry between tests.
    
    CircuitBreaker._registry is a class-level dict that persists across tests.
    Tests that create circuit breakers pollute the registry for later tests.
    """
    yield
    try:
        from praisonaiagents.llm.circuit_breaker import CircuitBreaker
        CircuitBreaker._registry.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def _reset_display_callbacks():
    """Restore display callback dicts between tests.
    
    sync_display_callbacks and async_display_callbacks are module-level dicts
    that get mutated by enable_editor_output() and similar functions.
    Tests that register callbacks pollute the dict for later tests.
    """
    try:
        import praisonaiagents.main as _main
        saved_sync = dict(_main.sync_display_callbacks)
        saved_async = dict(_main.async_display_callbacks)
    except (ImportError, AttributeError):
        yield
        return
    
    yield
    
    _main.sync_display_callbacks.clear()
    _main.sync_display_callbacks.update(saved_sync)
    _main.async_display_callbacks.clear()
    _main.async_display_callbacks.update(saved_async)

@pytest.fixture(autouse=True)
def _reset_module_shadowing():
    """Remove submodules from praisonaiagents namespace after tests to restore __getattr__.
    
    If 'from praisonaiagents.embedding import xyz' is called, Python adds the 'embedding'
    module object to praisonaiagents.__dict__, which overrides the __getattr__ proxy for
    lazy loading. This resets it so proxy tests don't fail mysteriously depending on run order.
    """
    yield
    import sys
    try:
        import praisonaiagents
        # Remove embedding module shadowing
        if hasattr(praisonaiagents, 'embedding') and isinstance(praisonaiagents.embedding, type(sys)):
            delattr(praisonaiagents, 'embedding')
    except (ImportError, AttributeError):
        pass
