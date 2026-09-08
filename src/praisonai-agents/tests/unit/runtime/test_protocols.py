"""Tests for runtime protocols."""

import pytest
from typing import AsyncIterator
from praisonaiagents.runtime.capabilities import RuntimeCapabilityMatrix
from praisonaiagents.runtime.protocols import AgentRuntimeProtocol, RuntimeConfig, RuntimeResult, RuntimeDelta


class MockRuntime:
    """Mock runtime implementation for testing protocol compliance.

    AgentRuntimeProtocol is @runtime_checkable, so isinstance() checks that
    EVERY member is present. runtime_name, runtime_version and capabilities were
    added to the protocol after this mock was written, so
    test_protocol_compliance failed on a bare "assert False" -- the mock had
    stopped implementing the protocol it exists to demonstrate.
    """

    @property
    def runtime_name(self) -> str:
        return "mock"

    @property
    def runtime_version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> "RuntimeCapabilityMatrix":
        return RuntimeCapabilityMatrix(basic_chat=True, simple_tools=True)

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
            content=f"Response to: {prompt}",
            metadata={'model': model_ref or 'default'}
        )
    
    async def stream_turn(
        self, 
        prompt: str, 
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        # Simple streaming simulation
        words = f"Response to: {prompt}".split()
        for word in words:
            yield RuntimeDelta(type="text", content=word + " ")

    async def execute_agent(
        self, agent_config: dict, prompt: str, **kwargs
    ) -> dict:
        return {"content": f"Response to: {prompt}", "metadata": agent_config}

    async def stream_agent(self, agent_config: dict, prompt: str, **kwargs):
        async for delta in self.stream_turn(prompt, **kwargs):
            yield delta

    async def validate_config(self, agent_config: dict) -> list:
        return []

    async def health_check(self) -> dict:
        return {"status": "ok", "latency_ms": 0, "errors": []}


def test_runtime_config():
    """Test RuntimeConfig dataclass."""
    config = RuntimeConfig(runtime_id="test")
    assert config.runtime_id == "test"
    assert config.metadata == {}
    
    config_with_metadata = RuntimeConfig(
        runtime_id="test2",
        metadata={"key": "value"}
    )
    assert config_with_metadata.metadata == {"key": "value"}


def test_runtime_result():
    """Test RuntimeResult dataclass."""
    result = RuntimeResult(content="test response")
    assert result.content == "test response"
    assert result.metadata == {}
    assert result.error is None
    
    result_with_error = RuntimeResult(
        content="",
        error="Something went wrong"
    )
    assert result_with_error.error == "Something went wrong"


def test_runtime_delta():
    """Test RuntimeDelta dataclass."""
    delta = RuntimeDelta(type="text", content="hello")
    assert delta.type == "text"
    assert delta.content == "hello"
    assert delta.metadata == {}
    
    delta_with_metadata = RuntimeDelta(
        type="tool_call",
        content="function_call",
        metadata={"function": "test"}
    )
    assert delta_with_metadata.metadata == {"function": "test"}


def test_protocol_compliance():
    """Test that our mock runtime implements the protocol correctly."""
    runtime = MockRuntime()
    
    # Check that it's recognized as implementing the protocol
    assert isinstance(runtime, AgentRuntimeProtocol)
    
    # Check method signatures exist
    assert hasattr(runtime, 'supports')
    assert hasattr(runtime, 'run_turn')
    assert hasattr(runtime, 'stream_turn')


@pytest.mark.asyncio
async def test_mock_runtime_run_turn():
    """Test mock runtime run_turn method."""
    runtime = MockRuntime()
    
    result = await runtime.run_turn("Hello world")
    assert isinstance(result, RuntimeResult)
    assert result.content == "Response to: Hello world"
    assert result.metadata == {'model': 'default'}
    
    # Test with model_ref
    result_with_model = await runtime.run_turn(
        "Hello world", 
        model_ref="gpt-4"
    )
    assert result_with_model.metadata == {'model': 'gpt-4'}


@pytest.mark.asyncio
async def test_mock_runtime_stream_turn():
    """Test mock runtime stream_turn method."""
    runtime = MockRuntime()
    
    deltas = []
    async for delta in runtime.stream_turn("Hello world"):
        assert isinstance(delta, RuntimeDelta)
        deltas.append(delta)
    
    # Should have one delta per word plus spaces
    assert len(deltas) == 4  # ["Response", "to:", "Hello", "world"]
    assert all(delta.type == "text" for delta in deltas)
    
    # Reconstruct content
    full_content = "".join(delta.content for delta in deltas)
    assert full_content == "Response to: Hello world "


def test_runtime_supports():
    """Test runtime supports method."""
    runtime = MockRuntime()
    
    assert runtime.supports() is True
    assert runtime.supports("gpt-4") is True
    assert runtime.supports("claude-3") is True