"""
Runtime Tool Result Middleware Protocol.

Defines the interface for normalizing tool results from plugin harnesses
before they reach hooks and memory adapters.

Protocol-driven design following AGENTS.md:
- Lightweight protocols only (no implementations)
- Dataclasses for configuration
- Async-first with proper typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Any, Dict, Optional, runtime_checkable
import time


@dataclass
class MiddlewareContext:
    """Context passed to middleware during tool result normalization.
    
    Contains metadata about the tool execution and runtime environment
    to help middleware make informed normalization decisions.
    """
    # Tool execution context
    tool_name: str
    runtime_id: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Execution metadata
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    # Additional context for middleware decision making
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class NormalizedToolResult:
    """Standardized tool result format.
    
    Plugin harnesses should normalize their vendor-specific results
    into this format so hooks and memory adapters see consistent payloads.
    """
    # Core result data
    content: Any  # The actual tool result (can be any type)
    
    # Standardized metadata
    success: bool = True
    error_message: Optional[str] = None
    
    # Rich metadata for downstream consumers
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Execution context
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    # Original raw result for debugging/advanced use cases
    raw_result: Optional[Any] = None


@runtime_checkable
class RuntimeToolResultMiddleware(Protocol):
    """Protocol for runtime-scoped tool result middleware.
    
    Plugin harnesses implement this to normalize their vendor-specific
    tool results into the standard NormalizedToolResult format.
    
    Example:
        class MyHarnessMiddleware:
            def normalize(self, result: Any, tool_name: str, ctx: MiddlewareContext) -> NormalizedToolResult:
                # Convert vendor-specific result format to standard format
                if isinstance(result, MyVendorResult):
                    return NormalizedToolResult(
                        content=result.data,
                        success=result.status == "ok",
                        error_message=result.error if result.status != "ok" else None,
                        metadata={
                            "vendor": "my_vendor",
                            "result_type": type(result).__name__
                        },
                        raw_result=result
                    )
                return NormalizedToolResult(content=result)
    """
    
    def normalize(
        self, 
        result: Any, 
        tool_name: str, 
        ctx: MiddlewareContext
    ) -> NormalizedToolResult:
        """Normalize a tool result into standard format.
        
        Args:
            result: Raw tool result from the plugin harness
            tool_name: Name of the tool that was executed
            ctx: Execution context with metadata
            
        Returns:
            NormalizedToolResult with standardized format
        """
        ...
    
    @property
    def runtime_id(self) -> str:
        """Unique identifier for the runtime this middleware handles.
        
        Used by RuntimeRegistry to route results to the correct middleware.
        Examples: "praisonai", "claude_harness", "openai_harness"
        """
        ...


class PassThroughMiddleware:
    """Default middleware that passes results through without modification.
    
    Used for the native 'praisonai' runtime and as a fallback for
    unregistered runtimes to avoid allocation overhead.
    """
    
    def __init__(self, runtime_id: str = "praisonai"):
        self._runtime_id = runtime_id
    
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    def normalize(
        self, 
        result: Any, 
        tool_name: str, 
        ctx: MiddlewareContext
    ) -> NormalizedToolResult:
        """Pass through result with minimal normalization."""
        return NormalizedToolResult(
            content=result,
            success=True,  # Assume success for native runtime
            raw_result=result
        )