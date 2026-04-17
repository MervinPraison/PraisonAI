"""
Base framework adapter protocol for PraisonAI.

This module defines the protocol that all framework adapters must implement,
enabling lazy-loaded, protocol-driven framework support.
"""

from typing import Protocol, Dict, List, Any, Optional
from contextlib import contextmanager


class FrameworkAdapter(Protocol):
    """Protocol for framework adapters."""
    
    name: str
    
    def is_available(self) -> bool:
        """Check if the framework is available for import."""
        ...
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run the framework with given configuration.
        
        Args:
            config: Framework configuration
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        ...
    
    def cleanup(self) -> None:
        """Clean up any resources after execution."""
        ...


class BaseFrameworkAdapter:
    """Base class for framework adapters providing common functionality."""
    
    def __init__(self):
        self._tool_registry: Dict[str, Any] = {}
        
    def register_tool(self, name: str, tool: Any) -> None:
        """Register a tool in the adapter's local registry."""
        self._tool_registry[name] = tool
    
    def get_tool(self, name: str) -> Optional[Any]:
        """Get a tool from the adapter's local registry."""
        return self._tool_registry.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tool_registry.keys())
    
    def cleanup(self) -> None:
        """Clean up resources - default implementation does nothing."""
        pass


@contextmanager
def scoped_telemetry_disable(telemetry_class):
    """
    Context manager to temporarily disable telemetry methods.
    
    This replaces import-time monkey patching with scoped patching
    that is automatically restored after use.
    """
    if not telemetry_class:
        yield
        return
        
    # Store original methods
    originals = {}
    noop = lambda *args, **kwargs: None
    
    for attr_name in dir(telemetry_class):
        attr = getattr(telemetry_class, attr_name)
        if callable(attr) and not attr_name.startswith("__"):
            originals[attr_name] = attr
            setattr(telemetry_class, attr_name, noop)
    
    try:
        yield
    finally:
        # Restore original methods
        for attr_name, original_method in originals.items():
            setattr(telemetry_class, attr_name, original_method)