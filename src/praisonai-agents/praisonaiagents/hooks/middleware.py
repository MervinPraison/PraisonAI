"""
Middleware System for PraisonAI Agents.

Provides wrap_model_call and wrap_tool_call patterns for intercepting
and modifying agent behavior at model/tool call boundaries.

Zero Performance Impact:
- All middleware is optional
- Empty middleware chain is O(1) fast path
- No overhead when middleware not registered

Usage:
    from praisonaiagents.hooks import before_model, wrap_model_call, wrap_tool_call
    
    @before_model
    def add_context(request):
        request.messages.append({"role": "system", "content": "Extra"})
        return request
    
    @wrap_model_call
    def retry_on_error(request, call_next):
        for _ in range(3):
            try:
                return call_next(request)
            except Exception:
                pass
        raise RuntimeError("All retries failed")
    
    agent = Agent(name="Test", hooks=[add_context, retry_on_error])
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from functools import wraps


@dataclass
class InvocationContext:
    """Context passed through middleware chain.
    
    Contains identifiers for multi-agent safety and optional metadata.
    """
    agent_id: str
    run_id: str
    session_id: str
    tool_name: Optional[str] = None
    model_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRequest:
    """Request data for model calls."""
    messages: List[Dict[str, Any]]
    model: str
    temperature: float = 1.0
    context: Optional[InvocationContext] = None
    tools: Optional[List[Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Response data from model calls."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    context: Optional[InvocationContext] = None
    tool_calls: Optional[List[Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolRequest:
    """Request data for tool calls."""
    tool_name: str
    arguments: Dict[str, Any]
    context: Optional[InvocationContext] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResponse:
    """Response data from tool calls."""
    tool_name: str
    result: Any
    error: Optional[str] = None
    context: Optional[InvocationContext] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# Type aliases for middleware functions
T = TypeVar('T')
BeforeModelFn = Callable[[ModelRequest], ModelRequest]
AfterModelFn = Callable[[ModelResponse], ModelResponse]
WrapModelCallFn = Callable[[ModelRequest, Callable[[ModelRequest], ModelResponse]], ModelResponse]
BeforeToolFn = Callable[[ToolRequest], ToolRequest]
AfterToolFn = Callable[[ToolResponse], ToolResponse]
WrapToolCallFn = Callable[[ToolRequest, Callable[[ToolRequest], ToolResponse]], ToolResponse]


class MiddlewareChain:
    """Synchronous middleware chain executor.
    
    Composes middleware functions in registration order.
    First registered middleware wraps all subsequent ones.
    """
    
    def __init__(self, middlewares: Optional[List[Callable]] = None):
        self._middlewares = middlewares or []
    
    def execute(self, request: Any, final_handler: Callable[[Any], Any]) -> Any:
        """Execute the middleware chain with a final handler.
        
        Args:
            request: The request object to pass through
            final_handler: The actual operation to perform
            
        Returns:
            The result from the chain
        """
        if not self._middlewares:
            return final_handler(request)
        
        # Build the chain from inside out
        # Last middleware wraps final_handler
        # First middleware is outermost
        def build_chain(index: int) -> Callable[[Any], Any]:
            if index >= len(self._middlewares):
                return final_handler
            
            middleware = self._middlewares[index]
            next_handler = build_chain(index + 1)
            
            def handler(req: Any) -> Any:
                return middleware(req, next_handler)
            
            return handler
        
        chain = build_chain(0)
        return chain(request)
    
    def __len__(self) -> int:
        return len(self._middlewares)


class AsyncMiddlewareChain:
    """Asynchronous middleware chain executor.
    
    Same as MiddlewareChain but for async middleware and handlers.
    """
    
    def __init__(self, middlewares: Optional[List[Callable]] = None):
        self._middlewares = middlewares or []
    
    async def execute(self, request: Any, final_handler: Callable) -> Any:
        """Execute the async middleware chain.
        
        Args:
            request: The request object to pass through
            final_handler: The actual async operation to perform
            
        Returns:
            The result from the chain
        """
        if not self._middlewares:
            return await final_handler(request)
        
        # Build the chain from inside out
        def build_chain(index: int) -> Callable:
            if index >= len(self._middlewares):
                return final_handler
            
            middleware = self._middlewares[index]
            next_handler = build_chain(index + 1)
            
            async def handler(req: Any) -> Any:
                return await middleware(req, next_handler)
            
            return handler
        
        chain = build_chain(0)
        return await chain(request)
    
    def __len__(self) -> int:
        return len(self._middlewares)


# Decorator functions for tagging middleware

def before_model(func: BeforeModelFn) -> BeforeModelFn:
    """Decorator to mark a function as a before_model hook.
    
    The function receives a ModelRequest and should return a (possibly modified) ModelRequest.
    
    Example:
        @before_model
        def add_context(request):
            request.messages.append({"role": "system", "content": "Extra"})
            return request
    """
    func._hook_type = 'before_model'
    return func


def after_model(func: AfterModelFn) -> AfterModelFn:
    """Decorator to mark a function as an after_model hook.
    
    The function receives a ModelResponse and should return a (possibly modified) ModelResponse.
    
    Example:
        @after_model
        def log_response(response):
            print(f"Model returned: {response.content[:50]}")
            return response
    """
    func._hook_type = 'after_model'
    return func


def wrap_model_call(func: WrapModelCallFn) -> WrapModelCallFn:
    """Decorator to mark a function as a wrap_model_call middleware.
    
    The function receives (request, call_next) and should call call_next(request)
    to continue the chain, or return early to short-circuit.
    
    Example:
        @wrap_model_call
        def retry_on_error(request, call_next):
            for _ in range(3):
                try:
                    return call_next(request)
                except Exception:
                    pass
            raise RuntimeError("All retries failed")
    """
    func._hook_type = 'wrap_model_call'
    return func


def before_tool(func: BeforeToolFn) -> BeforeToolFn:
    """Decorator to mark a function as a before_tool hook.
    
    The function receives a ToolRequest and should return a (possibly modified) ToolRequest.
    
    Example:
        @before_tool
        def validate_args(request):
            if 'dangerous' in request.arguments:
                raise ValueError("Dangerous argument detected")
            return request
    """
    func._hook_type = 'before_tool'
    return func


def after_tool(func: AfterToolFn) -> AfterToolFn:
    """Decorator to mark a function as an after_tool hook.
    
    The function receives a ToolResponse and should return a (possibly modified) ToolResponse.
    
    Example:
        @after_tool
        def log_result(response):
            print(f"Tool {response.tool_name} returned: {response.result}")
            return response
    """
    func._hook_type = 'after_tool'
    return func


def wrap_tool_call(func: WrapToolCallFn) -> WrapToolCallFn:
    """Decorator to mark a function as a wrap_tool_call middleware.
    
    The function receives (request, call_next) and should call call_next(request)
    to continue the chain, or return early to short-circuit.
    
    Example:
        @wrap_tool_call
        def retry_flaky_tool(request, call_next):
            last_error = None
            for _ in range(3):
                try:
                    return call_next(request)
                except Exception as e:
                    last_error = e
            raise last_error
    """
    func._hook_type = 'wrap_tool_call'
    return func


def get_hook_type(func: Callable) -> Optional[str]:
    """Get the hook type of a decorated function."""
    return getattr(func, '_hook_type', None)


def is_middleware(func: Callable) -> bool:
    """Check if a function is a middleware (wrap_* type)."""
    hook_type = get_hook_type(func)
    return hook_type in ('wrap_model_call', 'wrap_tool_call')


def categorize_hooks(hooks: List[Callable]) -> Dict[str, List[Callable]]:
    """Categorize hooks by their type.
    
    Returns:
        Dict with keys: before_model, after_model, wrap_model_call,
                       before_tool, after_tool, wrap_tool_call
    """
    categories = {
        'before_model': [],
        'after_model': [],
        'wrap_model_call': [],
        'before_tool': [],
        'after_tool': [],
        'wrap_tool_call': [],
    }
    
    for hook in hooks or []:
        hook_type = get_hook_type(hook)
        if hook_type and hook_type in categories:
            categories[hook_type].append(hook)
    
    return categories


class MiddlewareManager:
    """Manages middleware for an agent.
    
    Provides methods to execute before/after hooks and middleware chains
    for both model and tool calls.
    """
    
    def __init__(self, hooks: Optional[List[Callable]] = None):
        self._hooks = hooks or []
        self._categorized = categorize_hooks(self._hooks)
        
        # Pre-build chains for efficiency
        self._model_chain = MiddlewareChain(self._categorized['wrap_model_call'])
        self._tool_chain = MiddlewareChain(self._categorized['wrap_tool_call'])
    
    @property
    def has_model_hooks(self) -> bool:
        """Check if any model hooks are registered."""
        return bool(
            self._categorized['before_model'] or
            self._categorized['after_model'] or
            self._categorized['wrap_model_call']
        )
    
    @property
    def has_tool_hooks(self) -> bool:
        """Check if any tool hooks are registered."""
        return bool(
            self._categorized['before_tool'] or
            self._categorized['after_tool'] or
            self._categorized['wrap_tool_call']
        )
    
    def run_before_model(self, request: ModelRequest) -> ModelRequest:
        """Run all before_model hooks."""
        for hook in self._categorized['before_model']:
            request = hook(request)
        return request
    
    def run_after_model(self, response: ModelResponse) -> ModelResponse:
        """Run all after_model hooks (in reverse order)."""
        for hook in reversed(self._categorized['after_model']):
            response = hook(response)
        return response
    
    def run_before_tool(self, request: ToolRequest) -> ToolRequest:
        """Run all before_tool hooks."""
        for hook in self._categorized['before_tool']:
            request = hook(request)
        return request
    
    def run_after_tool(self, response: ToolResponse) -> ToolResponse:
        """Run all after_tool hooks (in reverse order)."""
        for hook in reversed(self._categorized['after_tool']):
            response = hook(response)
        return response
    
    def execute_model_call(
        self,
        request: ModelRequest,
        model_fn: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        """Execute a model call with all hooks and middleware.
        
        Order:
        1. before_model hooks (in order)
        2. wrap_model_call middleware chain
        3. actual model call
        4. after_model hooks (in reverse order)
        """
        # Fast path: no hooks
        if not self.has_model_hooks:
            return model_fn(request)
        
        # Run before hooks
        request = self.run_before_model(request)
        
        # Build wrapped handler that includes after hooks
        def wrapped_model_fn(req: ModelRequest) -> ModelResponse:
            response = model_fn(req)
            return self.run_after_model(response)
        
        # Execute through middleware chain
        return self._model_chain.execute(request, wrapped_model_fn)
    
    def execute_tool_call(
        self,
        request: ToolRequest,
        tool_fn: Callable[[ToolRequest], ToolResponse]
    ) -> ToolResponse:
        """Execute a tool call with all hooks and middleware.
        
        Order:
        1. before_tool hooks (in order)
        2. wrap_tool_call middleware chain
        3. actual tool call
        4. after_tool hooks (in reverse order)
        """
        # Fast path: no hooks
        if not self.has_tool_hooks:
            return tool_fn(request)
        
        # Run before hooks
        request = self.run_before_tool(request)
        
        # Build wrapped handler that includes after hooks
        def wrapped_tool_fn(req: ToolRequest) -> ToolResponse:
            response = tool_fn(req)
            return self.run_after_tool(response)
        
        # Execute through middleware chain
        return self._tool_chain.execute(request, wrapped_tool_fn)
