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
    
    # Test basic execution - runtime should handle errors gracefully
    result = await runtime.run_turn("Hello test")
    
    # Always verify result structure, even if there's an error
    assert isinstance(result, RuntimeResult)
    assert isinstance(result.content, str)
    assert isinstance(result.metadata, dict)
    assert result.metadata.get('runtime') == 'praisonai'
    
    # Either we have content or an error, but not neither
    if not result.content:
        assert result.error is not None


@pytest.mark.asyncio
async def test_praisonai_runtime_run_turn_with_params():
    """Test PraisonAI runtime with various parameters."""
    runtime = PraisonAIRuntime()
    
    # Test with system prompt and model
    result = await runtime.run_turn(
        "Hello test",
        system_prompt="You are a helpful assistant",
        model_ref="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=100
    )
    
    assert isinstance(result, RuntimeResult)
    assert isinstance(result.content, str)
    assert isinstance(result.metadata, dict)
    assert result.metadata.get('runtime') == 'praisonai'
    
    # Runtime should handle missing API keys gracefully
    if not result.content:
        assert result.error is not None


@pytest.mark.asyncio
async def test_praisonai_runtime_stream_turn():
    """Test PraisonAI runtime stream_turn method."""
    runtime = PraisonAIRuntime()
    
    deltas = []
    async for delta in runtime.stream_turn(
        "Hello test",
        system_prompt="You are a helpful assistant"
    ):
        assert isinstance(delta, RuntimeDelta)
        assert hasattr(delta, 'type')
        assert hasattr(delta, 'content')
        assert hasattr(delta, 'metadata')
        assert delta.metadata.get('runtime') == 'praisonai'
        deltas.append(delta)
        
        # Limit collection for tests
        if len(deltas) >= 5:
            break
    
    # Should have received at least one delta (even if error)
    assert len(deltas) > 0
    
    # Check if we got an error delta
    error_deltas = [d for d in deltas if d.type == 'error']
    if error_deltas:
        # If error, it should have content explaining the error
        assert any(d.content for d in error_deltas)


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