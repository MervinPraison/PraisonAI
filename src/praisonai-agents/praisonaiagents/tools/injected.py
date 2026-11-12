"""
Injected State for PraisonAI Tools.

Provides a mechanism for tools to receive injected state (agent context)
without exposing it in the tool's public schema.

Zero Performance Impact:
- When no Injected params, no overhead
- Context is thread-local for safety
- Lazy evaluation of state

Usage:
    from praisonaiagents import tool
    from praisonaiagents.tools import Injected
    
    @tool
    def my_tool(query: str, state: Injected[dict]) -> str:
        '''Tool with injected state.'''
        session_id = state.get('session_id')
        return f"Query: {query}, Session: {session_id}"
"""

import weakref
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, TypeVar, get_type_hints, get_origin, get_args
from contextvars import ContextVar
from contextlib import contextmanager


T = TypeVar('T')


class Injected(Generic[T]):
    """Type marker for injected parameters.
    
    Parameters annotated with Injected[T] will:
    - Not appear in the tool's public schema
    - Be automatically injected at runtime with the current agent state
    
    Supported types:
    - Injected[dict] - Receives state as a dictionary
    - Injected[AgentState] - Receives state as AgentState dataclass
    
    Example:
        @tool
        def my_tool(query: str, state: Injected[dict]) -> str:
            return f"session={state.get('session_id')}"
    """
    pass


@dataclass
class AgentState:
    """State object injected into tools.
    
    Contains context about the current agent execution.
    """
    agent_id: str
    run_id: str
    session_id: str
    last_user_message: Optional[str] = None
    last_agent_message: Optional[str] = None
    memory: Optional[Any] = None
    learn_manager: Optional[Any] = None
    previous_tool_results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    cancel_event: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Injected[dict] usage."""
        return {
            'agent_id': self.agent_id,
            'run_id': self.run_id,
            'session_id': self.session_id,
            'last_user_message': self.last_user_message,
            'last_agent_message': self.last_agent_message,
            'previous_tool_results': self.previous_tool_results,
            'metadata': self.metadata,
            'cancel_event': self.cancel_event,
        }


# Thread-local context for current state
_current_state: ContextVar[Optional[AgentState]] = ContextVar('current_state', default=None)


def get_current_state() -> Optional[AgentState]:
    """Get the current injection state."""
    return _current_state.get()


def set_current_state(state: Optional[AgentState]) -> None:
    """Set the current injection state."""
    _current_state.set(state)


@contextmanager
def with_injection_context(state: AgentState):
    """Context manager for setting injection state.
    
    Usage:
        with with_injection_context(state):
            result = my_tool(query="test")
    """
    token = _current_state.set(state)
    try:
        yield
    finally:
        _current_state.reset(token)


def is_injected_type(annotation: Any) -> bool:
    """Check if a type annotation is Injected[T] or bare Injected."""
    # Handle bare Injected class
    if annotation is Injected:
        return True
    # Handle Injected[T] with type parameter
    origin = get_origin(annotation)
    if origin is Injected:
        return True
    # Handle string annotations
    if isinstance(annotation, str) and 'Injected' in annotation:
        return True
    return False


def get_injected_type(annotation: Any) -> Optional[type]:
    """Get the inner type T from Injected[T]."""
    origin = get_origin(annotation)
    if origin is Injected:
        args = get_args(annotation)
        if args:
            return args[0]
    return None


def resolve_injected_value(annotation: Any, state: Optional[AgentState]) -> Any:
    """Resolve the value to inject based on annotation type.
    
    Args:
        annotation: The Injected[T] annotation or bare Injected
        state: The current agent state
        
    Returns:
        The resolved value (dict or AgentState)
    """
    if state is None:
        # Return empty dict if no state available
        return {}
    
    # Handle bare Injected (no type parameter) - default to dict
    if annotation is Injected:
        return state.to_dict()
    
    inner_type = get_injected_type(annotation)
    
    if inner_type is dict or inner_type is Dict:
        return state.to_dict()
    elif inner_type is AgentState:
        return state
    else:
        # Default to dict
        return state.to_dict()


def get_injected_params(func) -> Dict[str, Any]:
    """Get all injected parameters from a function.
    
    Returns:
        Dict mapping param name to its Injected[T] annotation
    """
    try:
        hints = get_type_hints(func)
    except Exception:
        # Same fallback as the schema builder, so a param hidden from the
        # model schema is still filled at runtime.
        hints = getattr(func, "__annotations__", None) or {}
    
    injected = {}
    for name, hint in hints.items():
        if name == 'return':
            continue
        if is_injected_type(hint):
            injected[name] = hint
    
    return injected


# Keyed weakly on the underlying function (bound methods share ``__func__``),
# so per-call LangChain/CrewAI instances are neither pinned nor re-scanned.
_plain_injected_cache: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def inject_into_plain_callable(func, kwargs: Dict[str, Any], state: Optional[AgentState] = None) -> Dict[str, Any]:
    """Fill ``Injected[...]`` params for an undecorated callable.

    ``@tool`` (FunctionTool) injects on its own call, so it is skipped here.
    Detected params are cached per function so the hot path stays cheap.
    """
    if hasattr(func, "injected_params") or not callable(func):
        return kwargs
    key = getattr(func, "__func__", func)
    try:
        params = _plain_injected_cache.get(key)
    except TypeError:  # not weak-referenceable / unhashable
        params = get_injected_params(func)
    else:
        if params is None:
            params = get_injected_params(func)
            _plain_injected_cache[key] = params
    if not params:
        return kwargs
    if state is None:
        return inject_state_into_kwargs(kwargs, params)
    token = _current_state.set(state)
    try:
        return inject_state_into_kwargs(kwargs, params)
    finally:
        _current_state.reset(token)


def inject_state_into_kwargs(kwargs: Dict[str, Any], injected_params: Dict[str, Any]) -> Dict[str, Any]:
    """Inject state values into kwargs for injected parameters.
    
    Args:
        kwargs: The original kwargs
        injected_params: Dict of injected param names to annotations
        
    Returns:
        Updated kwargs with injected values
    """
    if not injected_params:
        return kwargs
    
    state = get_current_state()
    result = kwargs.copy()
    
    for param_name, annotation in injected_params.items():
        # Inside an agent run the framework state is authoritative: a value the
        # model supplied (prompt injection) must never override it. Outside an
        # injection context, an explicit caller value is kept.
        if state is not None or param_name not in result:
            result[param_name] = resolve_injected_value(annotation, state)
    
    return result
