"""
Observability interface for PraisonAI Agents.

This module provides the protocol and types for observability/tracing.
Implementations are provided by the wrapper layer (praisonai_tools.observability).

Usage (simplest - recommended):
    from praisonaiagents import Agent, obs
    
    agent = Agent(
        name="Assistant",
        observability=obs.auto(),  # Auto-detect from env vars
    )
    agent.chat("Hello!")  # Auto-traces to configured provider

Alternative (explicit provider):
    observability=obs.langfuse()     # Langfuse
    observability=obs.langsmith()    # LangSmith
    observability=obs.agentops()     # AgentOps
    observability=obs.arize()        # Arize Phoenix
    observability=obs.datadog()      # Datadog
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
import time


@dataclass
class Span:
    """Represents a span in a trace."""
    span_id: str
    trace_id: str
    name: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"


@dataclass
class Trace:
    """Represents a complete trace."""
    trace_id: str
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    user_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    spans: List[Span] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"


@runtime_checkable
class ObservabilityAdapter(Protocol):
    """Protocol for observability adapters."""
    
    def on_trace_start(
        self,
        trace_id: str,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a trace starts."""
        ...
    
    def on_trace_end(
        self,
        trace_id: str,
        status: str = "ok",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a trace ends."""
        ...
    
    def on_span_start(
        self,
        span_id: str,
        trace_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a span starts."""
        ...
    
    def on_span_end(
        self,
        span_id: str,
        status: str = "ok",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a span ends."""
        ...
    
    def on_llm_call(
        self,
        span_id: str,
        model: str,
        messages: List[Dict[str, Any]],
        response: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Called when an LLM call is made."""
        ...
    
    def on_tool_call(
        self,
        span_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Called when a tool is invoked."""
        ...
    
    def flush(self) -> None:
        """Flush any pending data."""
        ...
    
    def close(self) -> None:
        """Close the adapter and release resources."""
        ...


class _LazyObsModule:
    """
    Lazy proxy for observability backends.
    
    Allows `from praisonaiagents import obs` without importing heavy deps.
    Actual provider classes are loaded only when accessed.
    """
    
    _PROVIDERS = {
        "langfuse": "praisonai_tools.observability.providers.langfuse_provider",
        "langsmith": "praisonai_tools.observability.providers.langsmith_provider",
        "agentops": "praisonai_tools.observability.providers.agentops_provider",
        "arize": "praisonai_tools.observability.providers.arize_phoenix_provider",
        "phoenix": "praisonai_tools.observability.providers.arize_phoenix_provider",
        "datadog": "praisonai_tools.observability.providers.datadog_provider",
        "mlflow": "praisonai_tools.observability.providers.mlflow_provider",
        "openlit": "praisonai_tools.observability.providers.openlit_provider",
        "opik": "praisonai_tools.observability.providers.opik_provider",
        "portkey": "praisonai_tools.observability.providers.portkey_provider",
        "traceloop": "praisonai_tools.observability.providers.traceloop_provider",
        "weave": "praisonai_tools.observability.providers.weave_provider",
        "braintrust": "praisonai_tools.observability.providers.braintrust_provider",
        "langtrace": "praisonai_tools.observability.providers.langtrace_provider",
        "langwatch": "praisonai_tools.observability.providers.langwatch_provider",
        "maxim": "praisonai_tools.observability.providers.maxim_provider",
    }
    
    def __getattr__(self, name: str):
        if name in self._PROVIDERS:
            return self._create_provider_factory(name)
        raise AttributeError(f"module 'obs' has no attribute {name!r}")
    
    def _create_provider_factory(self, provider_name: str):
        """Create a factory function for a provider."""
        def factory(**kwargs):
            try:
                import importlib
                module = importlib.import_module(self._PROVIDERS[provider_name])
                # Get the provider class (naming convention: XxxProvider)
                class_name = f"{provider_name.title().replace('_', '')}Provider"
                provider_cls = getattr(module, class_name, None)
                if provider_cls:
                    return provider_cls(**kwargs)
                # Fallback: try to find any class ending with Provider
                for attr_name in dir(module):
                    if attr_name.endswith("Provider"):
                        return getattr(module, attr_name)(**kwargs)
                raise AttributeError(f"No provider class found in {module}")
            except ImportError as e:
                raise ImportError(
                    f"Observability provider '{provider_name}' requires praisonai-tools. "
                    f"Install with: pip install praisonai-tools\n"
                    f"Original error: {e}"
                ) from e
        return factory
    
    def auto(self, **kwargs):
        """
        Auto-detect observability provider from environment variables.
        
        Checks for common env vars like LANGFUSE_PUBLIC_KEY, LANGSMITH_API_KEY, etc.
        Returns None if no provider is detected.
        """
        import os
        
        # Check for common provider env vars
        provider_env_map = {
            "LANGFUSE_PUBLIC_KEY": "langfuse",
            "LANGSMITH_API_KEY": "langsmith",
            "AGENTOPS_API_KEY": "agentops",
            "ARIZE_API_KEY": "arize",
            "DATADOG_API_KEY": "datadog",
            "MLFLOW_TRACKING_URI": "mlflow",
            "OPENLIT_API_KEY": "openlit",
            "OPIK_API_KEY": "opik",
            "PORTKEY_API_KEY": "portkey",
            "TRACELOOP_API_KEY": "traceloop",
            "WANDB_API_KEY": "weave",
            "BRAINTRUST_API_KEY": "braintrust",
        }
        
        for env_var, provider in provider_env_map.items():
            if os.getenv(env_var):
                return self._create_provider_factory(provider)(**kwargs)
        
        return None
    
    def __repr__(self):
        return "<module 'praisonaiagents.obs' (lazy observability backends)>"
    
    def __call__(self, provider: str = "auto", **kwargs):
        """
        Shortcut: obs("langfuse") or obs() for auto-detection.
        """
        if provider == "auto":
            return self.auto(**kwargs)
        return self._create_provider_factory(provider)(**kwargs)


# Singleton lazy module instance
obs = _LazyObsModule()


__all__ = [
    "ObservabilityAdapter",
    "Span",
    "Trace",
    "obs",
]
