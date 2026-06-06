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
    
    def resolve_variant(
        self,
        config: Dict[str, Any],
        registry: "FrameworkAdapterRegistry",
    ) -> "FrameworkAdapter":
        """Resolve to the appropriate adapter variant based on config.
        
        Default implementation returns self. Adapters with multiple versions
        (e.g., AutoGen v0.2 vs v0.4) should override this to select the
        appropriate concrete implementation.
        
        Args:
            config: Framework configuration that may contain version hints
            registry: The adapter registry for creating other adapters if needed
            
        Returns:
            The resolved FrameworkAdapter instance (may be self or another adapter)
        """
        return self


class BaseFrameworkAdapter:
    """Base class for framework adapters providing common functionality."""
    
    DEFAULT_MODEL = "openai/gpt-4o-mini"
    
    def __init__(self):
        pass
    
    def resolve_variant(self, config: Dict[str, Any], registry: Any) -> "BaseFrameworkAdapter":
        """Default implementation returns self."""
        return self
    
    def _resolve_llm(self, spec, llm_config):
        """Build a PraisonAIModel from a per-agent llm/function_calling_llm spec.
        Accepts str, dict, or None. Single source of truth for all adapters."""
        from ..inc import PraisonAIModel
        import os
        
        base = llm_config[0].get('base_url') if (llm_config and len(llm_config) > 0) else None
        key = llm_config[0].get('api_key') if (llm_config and len(llm_config) > 0) else None

        if isinstance(spec, str) and spec.strip():
            model = spec.strip()
        elif isinstance(spec, dict) and spec.get('model'):
            model = spec['model']
        else:
            model = os.environ.get("MODEL_NAME") or self.DEFAULT_MODEL

        return PraisonAIModel(model=model, base_url=base, api_key=key).get_model()
    
    def _format_template(self, template: str, **kwargs) -> str:
        """Safely format template string with given kwargs, preserving JSON-like braces."""
        if not isinstance(template, str):
            return template
        
        import re
        
        def _sub(m):
            name = m.group(1)
            return str(kwargs[name]) if name in kwargs else m.group(0)
        
        # Only substitute simple variable names like {topic}, not JSON like {"level":2}
        return re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', _sub, template)
    
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
        Safe default: run sync implementation in a worker thread.
        
        Framework adapters with native async support should override this method.
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