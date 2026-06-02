"""
Base framework adapter protocol for PraisonAI.

This module defines the protocol that all framework adapters must implement,
enabling lazy-loaded, protocol-driven framework support.
"""

from typing import Protocol, Dict, List, Any, Optional, Callable
from contextlib import contextmanager


class FrameworkAdapter(Protocol):
    """Protocol for framework adapters."""
    
    name: str
    install_hint: str
    requires_tools_extra: bool
    
    def is_available(self) -> bool:
        """Check if the framework is available for import."""
        ...
    
    def resolve(self) -> "FrameworkAdapter":
        """Pick the concrete adapter variant (e.g. autogen v0.2 vs v0.4).
        
        Returns:
            The resolved adapter instance (self or a different adapter)
        """
        ...
    
    def setup(self, *, framework_tag: str) -> None:
        """Framework-specific pre-run hooks (observability, sdk init, etc.).
        
        Args:
            framework_tag: Framework name for observability tagging
        """
        ...
    
    def run(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None,
        cli_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Run the framework with given configuration.
        
        Args:
            config: Framework configuration
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
        Returns:
            Execution result as string
        """
        ...

    async def arun(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None,
        cli_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Async-native execution. Default = offload sync run() to a thread.
        
        Args:
            config: Framework configuration
            llm_config: LLM configuration list
            topic: Topic for the tasks
            tools_dict: Available tools dictionary
            agent_callback: Callback for agent events
            task_callback: Callback for task events
            cli_config: CLI configuration
            
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
    
    def _format_template(self, template: str, **kwargs) -> str:
        """Safely format template string with given kwargs."""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            # Import logger here to avoid circular imports
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Template formatting failed for key %s; returning original template", e)
            return template
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Template formatting error: %s; returning original template", e)
            return template
    
    def resolve(self) -> "FrameworkAdapter":
        """Default implementation returns self."""
        return self
    
    def setup(self, *, framework_tag: str) -> None:
        """Default implementation does nothing."""
        pass
    
    async def arun(
        self,
        config: Dict[str, Any],
        llm_config: List[Dict],
        topic: str,
        *,
        tools_dict: Optional[Dict[str, Any]] = None,
        agent_callback: Optional[Callable] = None,
        task_callback: Optional[Callable] = None,
        cli_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Safe default for sync-only adapters (crewai, autogen v0.2):
        run the sync implementation in a worker thread, freeing the loop.
        """
        import asyncio
        return await asyncio.to_thread(
            self.run, config, llm_config, topic,
            tools_dict=tools_dict,
            agent_callback=agent_callback,
            task_callback=task_callback,
            cli_config=cli_config
        )
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