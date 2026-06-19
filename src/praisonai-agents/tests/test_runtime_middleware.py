"""
Integration tests for runtime-scoped tool result middleware.

Tests that middleware is properly invoked during tool execution
and normalizes results before hooks fire.
"""

import pytest
import json
from dataclasses import dataclass
from typing import Any, Dict

from praisonaiagents.runtime.middleware import (
    RuntimeToolResultMiddleware, 
    NormalizedToolResult, 
    MiddlewareContext
)
from praisonaiagents.runtime.registry import RuntimeRegistry, get_default_registry


@dataclass
class StubHarnessResult:
    """Stub result format from a fictional plugin harness."""
    status: str
    data: Any
    error_code: int = 0
    vendor_metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.vendor_metadata is None:
            self.vendor_metadata = {}


class StubHarnessMiddleware:
    """Stub middleware that normalizes StubHarnessResult to standard format."""
    
    @property
    def runtime_id(self) -> str:
        return "stub_harness"
    
    def normalize(
        self, 
        result: Any, 
        tool_name: str, 
        ctx: MiddlewareContext
    ) -> NormalizedToolResult:
        """Normalize stub harness results."""
        # Handle StubHarnessResult format
        if isinstance(result, StubHarnessResult):
            return NormalizedToolResult(
                content=result.data,
                success=result.status == "success",
                error_message=result.vendor_metadata.get("error_msg") if result.status != "success" else None,
                metadata={
                    "vendor": "stub_harness",
                    "error_code": result.error_code,
                    "tool_name": tool_name,
                    **result.vendor_metadata
                },
                execution_time_ms=ctx.execution_time_ms,
                raw_result=result
            )
        
        # Pass through other result types with minimal normalization
        return NormalizedToolResult(
            content=result,
            success=True,
            metadata={"vendor": "stub_harness", "normalized": False}
        )


def test_middleware_registry():
    """Test basic middleware registry functionality."""
    registry = RuntimeRegistry()
    middleware = StubHarnessMiddleware()
    
    # Test registration
    registry.register("stub_harness", middleware)
    assert registry.has_middleware("stub_harness")
    assert "stub_harness" in registry.list_runtimes()
    
    # Test retrieval
    retrieved = registry.get_middleware("stub_harness")
    assert retrieved is middleware
    
    # Test unregistered runtime returns default middleware
    default = registry.get_middleware("unknown_runtime")
    assert default.runtime_id == "praisonai"  # PassThroughMiddleware
    
    # Test unregistration
    assert registry.unregister("stub_harness")
    assert not registry.has_middleware("stub_harness")
    assert not registry.unregister("nonexistent")


def test_middleware_normalization():
    """Test that middleware normalizes vendor-specific results correctly."""
    middleware = StubHarnessMiddleware()
    
    # Test successful result normalization
    stub_result = StubHarnessResult(
        status="success",
        data={"message": "Hello world"},
        vendor_metadata={"execution_id": "123", "version": "1.0"}
    )
    
    ctx = MiddlewareContext(
        tool_name="test_tool",
        runtime_id="stub_harness",
        agent_id="test_agent",
        execution_time_ms=150.0
    )
    
    normalized = middleware.normalize(stub_result, "test_tool", ctx)
    
    assert isinstance(normalized, NormalizedToolResult)
    assert normalized.content == {"message": "Hello world"}
    assert normalized.success is True
    assert normalized.error_message is None
    assert normalized.metadata["vendor"] == "stub_harness"
    assert normalized.metadata["execution_id"] == "123"
    assert normalized.metadata["tool_name"] == "test_tool"
    assert normalized.execution_time_ms == 150.0
    assert normalized.raw_result is stub_result
    
    # Test error result normalization
    error_result = StubHarnessResult(
        status="error",
        data=None,
        error_code=404,
        vendor_metadata={"error_msg": "Tool not found"}
    )
    
    normalized_error = middleware.normalize(error_result, "missing_tool", ctx)
    
    assert normalized_error.success is False
    assert normalized_error.error_message == "Tool not found"
    assert normalized_error.metadata["error_code"] == 404
    assert normalized_error.content is None


def test_middleware_integration():
    """Test middleware integration with agent tool execution."""
    from praisonaiagents.agent.tool_execution import ToolExecutionMixin
    
    # Create a mock agent with the tool execution mixin
    class MockAgent(ToolExecutionMixin):
        def __init__(self):
            self.name = "test_agent"
            self._runtime_id = "stub_harness"
            self._session_id = "test_session"
            self.tools = []
            
            # Initialize hooks system
            from praisonaiagents.hooks.runner import HookRunner
            self._hook_runner = HookRunner()
            
            # Register stub middleware
            registry = get_default_registry()
            registry.register("stub_harness", StubHarnessMiddleware())
    
    # Test that middleware is applied during tool execution
    agent = MockAgent()
    
    # Mock the actual tool execution to return a stub result
    original_execute_tool_impl = agent._execute_tool_impl
    
    def mock_execute_tool_impl(function_name, arguments):
        # Return a vendor-specific result that needs normalization
        return StubHarnessResult(
            status="success", 
            data=f"Tool {function_name} executed with {arguments}",
            vendor_metadata={"mock": True}
        )
    
    agent._execute_tool_impl = mock_execute_tool_impl
    
    # Mock other methods to avoid complex setup
    agent._check_tool_approval_sync = lambda fn, args: (None, args)
    agent._get_existing_stream_emitter = lambda: None
    agent._doom_loop_tracker = None
    
    try:
        # Execute tool - should apply middleware normalization
        result = agent._execute_tool_with_context("test_tool", {"arg": "value"}, None)
        
        # Result should be normalized content, not the original StubHarnessResult
        assert isinstance(result, str)
        assert "Tool test_tool executed" in result
        assert not isinstance(result, StubHarnessResult)
        
    finally:
        # Cleanup - only unregister our test middleware, not all middleware
        get_default_registry().unregister("stub_harness")


def test_native_runtime_bypass():
    """Test that native praisonai runtime bypasses middleware for performance."""
    from praisonaiagents.agent.tool_execution import ToolExecutionMixin
    
    class MockNativeAgent(ToolExecutionMixin):
        def __init__(self):
            self.name = "native_agent"
            self._runtime_id = "praisonai"  # Native runtime
            self.tools = []
            
            from praisonaiagents.hooks.runner import HookRunner
            self._hook_runner = HookRunner()
    
    agent = MockNativeAgent()
    
    # Mock tool execution
    original_result = {"native": True, "data": "test"}
    agent._execute_tool_impl = lambda fn, args: original_result
    agent._check_tool_approval_sync = lambda fn, args: (None, args)
    agent._get_existing_stream_emitter = lambda: None
    agent._doom_loop_tracker = None
    
    # Execute tool - should NOT apply middleware for native runtime
    result = agent._execute_tool_with_context("test_tool", {}, None)
    
    # Result should be unchanged from original
    assert result is original_result
    assert result["native"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])