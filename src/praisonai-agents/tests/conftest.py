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

# Keep the test suite off the network for things it never meant to fetch.
# These are set before any praisonaiagents/litellm import so they take effect.
#
#   litellm downloads model_prices_and_context_window.json from
#   raw.githubusercontent.com the first time it prices a response, so even a
#   fully-mocked LLM test reached out. Its bundled copy is equivalent for
#   tests, and using it also stops the suite failing or stalling when offline.
#
#   huggingface_hub downloads tokenizers on first use, which pulled
#   huggingface.co into knowledge tests that only construct a config.
#
# A test that genuinely needs live data opts back in with monkeypatch.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

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
    """Skip live and network tests unless explicitly enabled.

    PRAISONAI_ALLOW_NETWORK was already set to '0' by two workflows and by the
    praisonai-code test CLI, but nothing on this side read it -- a switch wired
    to nothing, while network-marked tests ran anyway. Honouring it here makes
    "unit: pure unit tests - no network" (pytest.ini) actually hold, and stops
    the suite depending on a reachable third-party service.
    """
    if os.environ.get("PRAISONAI_LIVE_TESTS") != "1":
        skip_live = pytest.mark.skip(reason="Live tests disabled. Set PRAISONAI_LIVE_TESTS=1 to enable.")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)

    if os.environ.get("PRAISONAI_ALLOW_NETWORK") != "1":
        skip_net = pytest.mark.skip(
            reason="Network tests disabled. Set PRAISONAI_ALLOW_NETWORK=1 to enable."
        )
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_net)


_ALLOWED_HOST_PREFIXES = ("127.", "10.", "192.168.", "169.254.")
_ALLOWED_HOSTS = {"::1", "localhost", "0.0.0.0", ""}


def _is_local(host):
    if not isinstance(host, str):
        return False
    return host in _ALLOWED_HOSTS or host.startswith(_ALLOWED_HOST_PREFIXES)


@pytest.fixture(autouse=True)
def _no_unmarked_network(request, monkeypatch):
    """Fail a unit test that reaches the internet instead of letting it bill.

    Several tests here made real, billed provider calls on every run simply
    because nothing stopped them -- a module-level skipif on key *presence*
    reads as "we have a key, so go ahead" rather than "the operator asked for
    this". Silent egress is the failure mode: the test passes, the bill grows,
    and nobody looks. Anything genuinely needing the network says so with the
    `network` or `live` marker (both gated by env in
    pytest_collection_modifyitems above), and is exempt here.

    Loopback and private ranges stay open, so local servers, fixtures and
    sandboxes are unaffected.
    """
    if request.node.get_closest_marker("network") or request.node.get_closest_marker("live"):
        return
    if os.environ.get("PRAISONAI_ALLOW_NETWORK") == "1":
        return

    import socket

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _blocked(addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        return not _is_local(host)

    def _explain(addr):
        return (
            f"{request.node.nodeid} tried to connect to {addr!r}. Unit tests must "
            "not reach the network: stub the call, or mark the test "
            "@pytest.mark.network (or @pytest.mark.live for a paid provider) so "
            "it is skipped unless explicitly enabled."
        )

    def guarded_connect(self, addr):
        if _blocked(addr):
            raise RuntimeError(_explain(addr))
        return real_connect(self, addr)

    def guarded_connect_ex(self, addr):
        if _blocked(addr):
            raise RuntimeError(_explain(addr))
        return real_connect_ex(self, addr)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)


@pytest.fixture(autouse=True)
def _clear_warning_registries():
    """Let a test see a warning an earlier test already triggered.

    Python records each (message, category, lineno) it has warned about in the
    emitting module's __warningregistry__ and stays silent thereafter. So a
    test asserting `pytest.warns(DeprecationWarning)` passed alone and failed
    in a full run purely because some earlier test had already tripped the same
    warning -- five tests across test_parameter_naming, test_param_consolidation
    and test_gap_closure behaved that way, with nothing wrong in either the
    test or the code.

    Clearing the registries before each test makes the assertion depend on the
    code under test rather than on what ran before it.
    """
    import sys

    for module in list(sys.modules.values()):
        registry = getattr(module, "__warningregistry__", None)
        if registry:
            registry.clear()

    # praisonaiagents.utils.deprecation keeps its own "warn once per process"
    # set (_warned_params) to keep Agent.__init__ off a hot path. That is the
    # right production behaviour, but it means only the FIRST test in a process
    # can ever observe a given parameter deprecation. Clear it too, so these
    # tests assert the code's behaviour rather than their position in the run.
    try:
        from praisonaiagents.utils import deprecation as _deprecation
        _deprecation._warned_params.clear()
    except Exception:  # noqa: BLE001 - never let test setup fail on this
        pass

    yield


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
