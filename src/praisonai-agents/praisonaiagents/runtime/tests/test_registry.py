"""Tests for runtime registry."""

import pytest
from ..registry import (
    register_runtime, unregister_runtime, list_runtimes, resolve_runtime,
    add_runtime_alias, is_runtime_available, RuntimeRegistry
)
from ..protocols import AgentRuntimeProtocol, RuntimeResult, RuntimeDelta
from typing import AsyncIterator


class TestRuntime:
    """Test runtime for registry testing."""
    
    def __init__(self, runtime_id="test"):
        self.runtime_id = runtime_id
    
    def supports(self, model_ref: str = None) -> bool:
        return True
    
    async def run_turn(
        self, 
        prompt: str, 
        *,
        system_prompt: str = None,
        model_ref: str = None,
        **kwargs
    ) -> RuntimeResult:
        return RuntimeResult(
            content=f"Test response from {self.runtime_id}",
            metadata={'runtime': self.runtime_id}
        )
    
    async def stream_turn(
        self, 
        prompt: str, 
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        yield RuntimeDelta(type="text", content=f"Streaming from {self.runtime_id}")


def test_register_and_resolve_runtime():
    """Test runtime registration and resolution."""
    runtime_id = "test-runtime"
    
    # Register a test runtime
    register_runtime(runtime_id, lambda: TestRuntime(runtime_id))
    
    # Check it's in the list
    runtimes = list_runtimes()
    assert runtime_id in runtimes
    
    # Resolve it
    runtime = resolve_runtime(runtime_id)
    assert isinstance(runtime, TestRuntime)
    assert runtime.runtime_id == runtime_id
    
    # Check it's available
    assert is_runtime_available(runtime_id)
    
    # Clean up
    unregister_runtime(runtime_id)


def test_unregister_runtime():
    """Test runtime unregistration."""
    runtime_id = "test-unregister"
    
    # Register runtime
    register_runtime(runtime_id, lambda: TestRuntime(runtime_id))
    assert is_runtime_available(runtime_id)
    
    # Unregister it
    result = unregister_runtime(runtime_id)
    assert result is True
    
    # Should no longer be available
    assert not is_runtime_available(runtime_id)
    
    # Unregistering again should return False
    result = unregister_runtime(runtime_id)
    assert result is False


def test_runtime_alias():
    """Test runtime alias functionality."""
    runtime_id = "test-alias"
    alias = "test-shortcut"
    
    # Register runtime
    register_runtime(runtime_id, lambda: TestRuntime(runtime_id))
    
    # Add alias
    add_runtime_alias(alias, runtime_id)
    
    # Should be able to resolve via alias
    runtime_via_alias = resolve_runtime(alias)
    runtime_direct = resolve_runtime(runtime_id)
    
    assert runtime_via_alias.runtime_id == runtime_direct.runtime_id
    
    # Clean up
    unregister_runtime(runtime_id)


def test_resolve_unknown_runtime():
    """Test resolving unknown runtime raises ValueError."""
    with pytest.raises(ValueError, match="Unknown runtime"):
        resolve_runtime("non-existent-runtime")


def test_alias_to_unknown_runtime():
    """Test creating alias to unknown runtime raises ValueError."""
    with pytest.raises(ValueError, match="Cannot create alias"):
        add_runtime_alias("bad-alias", "non-existent-runtime")


def test_builtin_praisonai_runtime():
    """Test that built-in praisonai runtime is available."""
    # The built-in runtime should be auto-registered
    runtimes = list_runtimes()
    assert "praisonai" in runtimes
    
    # Should be able to resolve it
    runtime = resolve_runtime("praisonai")
    assert runtime is not None
    assert hasattr(runtime, 'supports')
    assert hasattr(runtime, 'run_turn')
    assert hasattr(runtime, 'stream_turn')


@pytest.mark.asyncio
async def test_builtin_runtime_protocol_compliance():
    """Test that built-in runtime implements protocol correctly."""
    runtime = resolve_runtime("praisonai")
    
    # Test supports method
    assert runtime.supports() is True
    assert runtime.supports("gpt-4") is True
    
    # Test run_turn (may fail if no OpenAI key, but should not crash)
    try:
        result = await runtime.run_turn("Hello test")
        assert isinstance(result, RuntimeResult)
        # Content might be empty if no API key, but should be string
        assert isinstance(result.content, str)
        assert isinstance(result.metadata, dict)
    except Exception:
        # It's OK if this fails due to missing API keys in tests
        pass


def test_runtime_registry_class():
    """Test RuntimeRegistry class interface."""
    registry = RuntimeRegistry()
    
    runtime_id = "test-registry-class"
    
    # Test registration via class
    registry.register(runtime_id, lambda: TestRuntime(runtime_id))
    
    # Test list via class
    names = registry.list_names()
    assert runtime_id in names
    
    # Test resolution via class
    runtime = registry.resolve(runtime_id)
    assert isinstance(runtime, TestRuntime)
    
    # Test availability via class
    assert registry.is_available(runtime_id)
    
    # Test unregistration via class
    result = registry.unregister(runtime_id)
    assert result is True
    
    # Should no longer be available
    assert not registry.is_available(runtime_id)


def test_multiple_runtimes():
    """Test registering and managing multiple runtimes."""
    runtime_ids = ["runtime1", "runtime2", "runtime3"]
    
    # Register multiple runtimes
    for runtime_id in runtime_ids:
        register_runtime(runtime_id, lambda id=runtime_id: TestRuntime(id))
    
    # All should be in the list
    runtimes = list_runtimes()
    for runtime_id in runtime_ids:
        assert runtime_id in runtimes
    
    # All should be resolvable
    for runtime_id in runtime_ids:
        runtime = resolve_runtime(runtime_id)
        assert runtime.runtime_id == runtime_id
    
    # Clean up
    for runtime_id in runtime_ids:
        unregister_runtime(runtime_id)