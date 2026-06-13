"""
Runtime Resolution Logic for Auto-Selection.

Implements the auto runtime selection algorithm based on provider/model
support and priority ranking, with fallback to default praisonai runtime.
"""

import logging
from typing import Optional, List, Tuple, Union
from .protocols import AgentRuntimeProtocol
from .registry import get_all_runtime_factories
from .._logging import get_logger

logger = get_logger(__name__)


def resolve_runtime(
    provider: str, 
    model: str, 
    mode: str = "auto",
    runtime_id: Optional[str] = None
) -> AgentRuntimeProtocol:
    """Resolve runtime based on provider/model and selection mode.
    
    Args:
        provider: LLM provider name (e.g., "openai", "anthropic")  
        model: Model name (e.g., "gpt-4", "claude-3-opus")
        mode: Selection mode - "auto" for intelligent selection, 
              or explicit runtime_id
        runtime_id: Explicit runtime ID when mode is not "auto"
        
    Returns:
        AgentRuntimeProtocol instance ready for execution
        
    Raises:
        ValueError: If explicit runtime_id is not found
        RuntimeError: If no suitable runtime found in auto mode
    """
    if mode != "auto" and runtime_id:
        return _resolve_explicit_runtime(runtime_id)
    elif mode != "auto":
        # Mode is explicit runtime ID
        return _resolve_explicit_runtime(mode) 
    else:
        return _resolve_auto_runtime(provider, model)


def _resolve_explicit_runtime(runtime_id: str) -> AgentRuntimeProtocol:
    """Resolve runtime by explicit ID."""
    from .registry import resolve_runtime_factory
    
    try:
        factory = resolve_runtime_factory(runtime_id)
        runtime = factory()
        
        if not runtime.is_available:
            logger.warning(f"Runtime '{runtime_id}' is not available, using anyway")
            
        logger.debug(f"Resolved explicit runtime: {runtime_id}")
        return runtime
        
    except ValueError as e:
        raise ValueError(f"Failed to resolve runtime '{runtime_id}': {e}")


def _resolve_auto_runtime(provider: str, model: str) -> AgentRuntimeProtocol:
    """Auto-select best runtime based on provider/model support and priority."""
    factories = get_all_runtime_factories()
    
    if not factories:
        raise RuntimeError("No runtimes available for auto-selection")
    
    # Collect supporting runtimes with priority
    candidates: List[Tuple[int, str, AgentRuntimeProtocol]] = []
    
    for runtime_id, factory in factories.items():
        try:
            runtime = factory()
            
            # Skip unavailable runtimes
            if not runtime.is_available:
                logger.debug(f"Skipping unavailable runtime: {runtime_id}")
                continue
                
            # Check provider/model support
            if runtime.supports(provider, model):
                priority = runtime.selection_priority()
                candidates.append((priority, runtime_id, runtime))
                logger.debug(f"Runtime '{runtime_id}' supports {provider}/{model} (priority: {priority})")
            else:
                logger.debug(f"Runtime '{runtime_id}' does not support {provider}/{model}")
                
        except Exception as e:
            logger.warning(f"Error checking runtime '{runtime_id}': {e}")
            continue
    
    if not candidates:
        logger.warning(f"No runtimes support {provider}/{model}, falling back to default")
        return _get_fallback_runtime()
    
    # Sort by priority (lower values first), then by runtime_id for stability
    candidates.sort(key=lambda x: (x[0], x[1]))
    
    priority, runtime_id, runtime = candidates[0]
    logger.info(f"Auto-selected runtime '{runtime_id}' for {provider}/{model} (priority: {priority})")
    
    return runtime


def _get_fallback_runtime() -> AgentRuntimeProtocol:
    """Get fallback praisonai runtime when auto-selection fails."""
    from .registry import resolve_runtime_factory
    
    try:
        factory = resolve_runtime_factory("praisonai")
        runtime = factory()
        logger.debug("Using fallback praisonai runtime")
        return runtime
    except ValueError:
        raise RuntimeError(
            "No suitable runtime found and praisonai fallback unavailable. "
            "Ensure praisonai runtime is properly configured."
        )


def get_supporting_runtimes(provider: str, model: str) -> List[str]:
    """Get list of runtime IDs that support the provider/model pair.
    
    Args:
        provider: LLM provider name
        model: Model name
        
    Returns:
        List of runtime IDs that support this provider/model
    """
    factories = get_all_runtime_factories()
    supporting = []
    
    for runtime_id, factory in factories.items():
        try:
            runtime = factory()
            if runtime.is_available and runtime.supports(provider, model):
                supporting.append(runtime_id)
        except Exception:
            continue
            
    return supporting