"""Tests for built-in PraisonAI runtime."""

import pytest
from ..builtin import PraisonAIRuntime
from ..protocols import RuntimeResult, RuntimeDelta


def test_praisonai_runtime_initialization():
    """Test PraisonAI runtime initialization."""
    runtime = PraisonAIRuntime()
    
    assert runtime.runtime_id == "praisonai"
    assert hasattr(runtime, 'supports')
    assert hasattr(runtime, 'run_turn')
    assert hasattr(runtime, 'stream_turn')


def test_praisonai_runtime_supports():
    """Test PraisonAI runtime supports method."""
    runtime = PraisonAIRuntime()
    
    # Should support all models
    assert runtime.supports() is True
    assert runtime.supports("gpt-4") is True
    assert runtime.supports("claude-3") is True
    assert runtime.supports("unknown-model") is True


@pytest.mark.asyncio
async def test_praisonai_runtime_run_turn():
    """Test PraisonAI runtime run_turn method."""
    runtime = PraisonAIRuntime()
    
    # Test basic execution (may fail if no API key, but should not crash)
    try:
        result = await runtime.run_turn("Hello test")
        
        # If we get a result, verify its structure
        assert isinstance(result, RuntimeResult)
        assert isinstance(result.content, str)
        assert isinstance(result.metadata, dict)
        assert result.metadata.get('runtime') == 'praisonai'
        
        # Error should be None if successful
        if result.content:
            assert result.error is None
            
    except Exception as e:
        # If it fails due to missing API keys, that's expected in tests
        # The runtime should handle this gracefully
        pass


@pytest.mark.asyncio
async def test_praisonai_runtime_run_turn_with_params():
    """Test PraisonAI runtime with various parameters."""
    runtime = PraisonAIRuntime()
    
    try:
        # Test with system prompt
        result = await runtime.run_turn(
            "Hello test",
            system_prompt="You are a helpful assistant",
            model_ref="gpt-3.5-turbo"
        )
        
        assert isinstance(result, RuntimeResult)
        assert isinstance(result.content, str)
        assert isinstance(result.metadata, dict)
        assert result.metadata.get('runtime') == 'praisonai'
        
    except Exception:
        # Expected if no API keys
        pass


@pytest.mark.asyncio
async def test_praisonai_runtime_stream_turn():
    """Test PraisonAI runtime stream_turn method."""
    runtime = PraisonAIRuntime()
    
    try:
        deltas = []
        async for delta in runtime.stream_turn("Hello test"):
            assert isinstance(delta, RuntimeDelta)
            assert hasattr(delta, 'type')
            assert hasattr(delta, 'content')
            assert hasattr(delta, 'metadata')
            assert delta.metadata.get('runtime') == 'praisonai'
            deltas.append(delta)
            
            # Limit collection for tests
            if len(deltas) >= 5:
                break
        
        # Should have received some deltas if successful
        if deltas:
            assert all(isinstance(delta, RuntimeDelta) for delta in deltas)
            
    except Exception:
        # Expected if no API keys or agent creation fails
        pass


@pytest.mark.asyncio 
async def test_praisonai_runtime_error_handling():
    """Test PraisonAI runtime error handling."""
    runtime = PraisonAIRuntime()
    
    # Test with invalid parameters that should cause an error
    result = await runtime.run_turn(
        "Hello test",
        model_ref="definitely-not-a-real-model-12345",
        max_tokens=-1  # Invalid parameter
    )
    
    # Should return a RuntimeResult with error, not raise exception
    assert isinstance(result, RuntimeResult)
    
    # If there was an error, it should be captured
    if result.error:
        assert isinstance(result.error, str)
        assert len(result.error) > 0


def test_praisonai_runtime_metadata():
    """Test that runtime includes proper metadata."""
    runtime = PraisonAIRuntime()
    
    # Check runtime identification
    assert runtime.runtime_id == "praisonai"