"""
Streaming Protocol Extension - implements Gap 3 from Issue #1392.

This module completes the streaming adapter pattern by extending LLM adapters
with comprehensive streaming capabilities, removing provider-specific conditionals
from the core LLM loop.

Architecture:
- Extends existing LLMProviderAdapterProtocol with streaming interface
- Each adapter owns its streaming decisions and error recovery  
- Core llm.py contains no provider-name conditionals for streaming
- StreamEvent protocol is used consistently for all streaming deltas
- Observable fallback events instead of silent streaming->non-streaming fallback

Design principles:
- Protocol-driven: complete the existing adapter pattern
- DRY: eliminate scattered streaming conditionals
- Extensibility: new providers = new adapter only (no core changes)
- Observable: emit events for streaming capability decisions
"""

import logging
from typing import Optional, Dict, Any, List, AsyncIterator, Union, Protocol
from abc import abstractmethod
from ..streaming.events import StreamEvent, StreamEventType, StreamEventEmitter

logger = logging.getLogger(__name__)


class StreamingCapableAdapter(Protocol):
    """
    Extended protocol for LLM adapters with comprehensive streaming support.
    
    This extends the base LLMProviderAdapterProtocol with streaming-specific
    methods that encapsulate all provider quirks and decisions.
    """
    
    def can_stream(self, *, tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> bool:
        """
        Determine if this provider can stream in the requested configuration.
        
        Args:
            tools: Optional list of tools that will be used
            **kwargs: Additional LLM parameters that might affect streaming
            
        Returns:
            True if streaming is possible with these parameters, False otherwise
        """
        ...
    
    async def stream_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 1.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream_emitter: Optional[StreamEventEmitter] = None,
        **kwargs
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream LLM completion using this provider's native streaming API.
        
        Args:
            messages: Chat messages
            model: Model identifier
            temperature: Sampling temperature
            tools: Optional tools for function calling
            stream_emitter: Optional emitter for additional event handling
            **kwargs: Additional provider-specific parameters
            
        Yields:
            StreamEvent instances with standardized streaming data
            
        Raises:
            StreamingNotSupportedError: If streaming not available in this configuration
            StreamingError: If streaming fails and cannot recover
        """
        ...
    
    def is_stream_error_recoverable(self, exc: Exception) -> bool:
        """
        Determine if a streaming error can be recovered by falling back to non-streaming.
        
        Args:
            exc: Exception that occurred during streaming
            
        Returns:
            True if fallback to non-streaming should be attempted, False otherwise
        """
        ...
    
    def create_stream_unavailable_event(self, reason: str, **metadata) -> StreamEvent:
        """
        Create a StreamEvent indicating why streaming is not available.
        
        This enables observable fallback instead of silent streaming -> non-streaming.
        
        Args:
            reason: Human-readable reason why streaming is unavailable
            **metadata: Additional context for the unavailability
            
        Returns:
            StreamEvent with type STREAM_UNAVAILABLE and reason
        """
        ...


class StreamingNotSupportedError(Exception):
    """Raised when streaming is not supported in the current configuration."""
    pass


class StreamingError(Exception):
    """Raised when streaming fails unrecoverably.""" 
    pass


class DefaultStreamingAdapter:
    """
    Default streaming adapter with sensible fallbacks.
    
    Provides baseline streaming support for most providers that follow
    OpenAI-style streaming APIs.
    """
    
    def can_stream(self, *, tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> bool:
        """Most providers support streaming, even with tools."""
        return True
    
    async def stream_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 1.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream_emitter: Optional[StreamEventEmitter] = None,
        **kwargs
    ) -> AsyncIterator[StreamEvent]:
        """
        Default streaming implementation using litellm.
        
        This is the baseline implementation that most providers can use.
        Provider-specific adapters override this for custom behavior.
        """
        import litellm
        import time
        
        # Emit request start event
        start_time = time.perf_counter()
        request_start_event = StreamEvent(
            type=StreamEventType.REQUEST_START,
            timestamp=start_time,
            metadata={"model": model, "provider": "default"}
        )
        
        # Yield the event to consumers and emit to optional stream_emitter
        yield request_start_event
        if stream_emitter:
            await stream_emitter.emit_async(request_start_event)
        
        try:
            # Build completion parameters
            completion_params = {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "stream": True,
                **kwargs
            }
            
            if tools:
                completion_params["tools"] = tools
            
            response_text = ""
            tool_calls = []
            first_token_emitted = False
            
            # Stream the completion
            async for chunk in litellm.acompletion(**completion_params):
                if chunk and chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    
                    # Handle text content
                    if delta.content:
                        if not first_token_emitted:
                            yield StreamEvent(
                                type=StreamEventType.FIRST_TOKEN,
                                timestamp=time.perf_counter(),
                                content=delta.content
                            )
                            first_token_emitted = True
                        else:
                            yield StreamEvent(
                                type=StreamEventType.DELTA_TEXT,
                                timestamp=time.perf_counter(),
                                content=delta.content
                            )
                        response_text += delta.content
                    
                    # Handle tool calls
                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            yield StreamEvent(
                                type=StreamEventType.DELTA_TOOL_CALL,
                                timestamp=time.perf_counter(),
                                tool_call={
                                    "id": tool_call.id,
                                    "name": tool_call.function.name if tool_call.function else None,
                                    "arguments": tool_call.function.arguments if tool_call.function else None
                                }
                            )
                            tool_calls.append(tool_call)
            
            # Emit stream completion
            yield StreamEvent(
                type=StreamEventType.STREAM_END,
                timestamp=time.perf_counter(),
                metadata={
                    "response_text": response_text,
                    "tool_calls": [tc.to_dict() if hasattr(tc, 'to_dict') else tc for tc in tool_calls]
                }
            )
            
        except Exception as e:
            # Emit error event
            yield StreamEvent(
                type=StreamEventType.ERROR,
                timestamp=time.perf_counter(),
                error=str(e),
                metadata={"exception_type": type(e).__name__}
            )
            
            if not self.is_stream_error_recoverable(e):
                raise StreamingError(f"Unrecoverable streaming error: {e}") from e
    
    def is_stream_error_recoverable(self, exc: Exception) -> bool:
        """
        Default error recovery logic.
        
        Most JSON parsing errors and timeout errors are recoverable.
        """
        error_str = str(exc).lower()
        recoverable_patterns = [
            "json",
            "parsing",
            "timeout",
            "connection"
        ]
        return any(pattern in error_str for pattern in recoverable_patterns)
    
    def create_stream_unavailable_event(self, reason: str, **metadata) -> StreamEvent:
        """Create standard stream unavailable event."""
        import time
        return StreamEvent(
            type=StreamEventType.STREAM_UNAVAILABLE,
            timestamp=time.perf_counter(),
            error=f"Streaming unavailable: {reason}",
            metadata={
                "reason": reason,
                **metadata
            }
        )


class OllamaStreamingAdapter(DefaultStreamingAdapter):
    """
    Ollama-specific streaming adapter.
    
    Handles Ollama's streaming limitations:
    - Doesn't support streaming with tools reliably
    - Has specific error patterns that need different recovery
    """
    
    def can_stream(self, *, tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> bool:
        """Ollama can stream, but not reliably with tools."""
        if tools:
            return False  # Disable streaming when tools are present
        return True
    
    def is_stream_error_recoverable(self, exc: Exception) -> bool:
        """Ollama-specific error recovery patterns."""
        error_str = str(exc).lower()
        ollama_recoverable = [
            "json",
            "parsing", 
            "connection reset",
            "incomplete",
            "tool"  # Tool-related errors are often recoverable by disabling tools
        ]
        return any(pattern in error_str for pattern in ollama_recoverable)


class AnthropicStreamingAdapter(DefaultStreamingAdapter):
    """
    Anthropic/Claude streaming adapter.
    
    Handles the known litellm/async-generator bug with Anthropic streaming.
    """
    
    def can_stream(self, *, tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> bool:
        """
        Anthropic streaming is disabled due to litellm bug.
        
        Issue: litellm.acompletion with stream=True returns a ModelResponse (not async generator)
        for Anthropic in the async path, causing 'async for requires __aiter__' error.
        """
        return False  # Disable until litellm bug is fixed
    
    def create_stream_unavailable_event(self, reason: Optional[str] = None, **metadata) -> StreamEvent:
        """Create Anthropic-specific unavailable event with bug details."""
        return super().create_stream_unavailable_event(
            reason or "litellm async generator bug",
            provider="anthropic",
            # TODO: Add actual bug reference when litellm issue is filed
            **metadata
        )


class GeminiStreamingAdapter(DefaultStreamingAdapter):
    """
    Google Gemini streaming adapter.
    
    Handles Gemini's streaming issues with tools and JSON parsing.
    """
    
    def can_stream(self, *, tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> bool:
        """Gemini has issues with streaming + tools."""
        if tools:
            return False  # Disable streaming when tools are present due to JSON parsing issues
        return True
    
    def create_stream_unavailable_event(self, reason: Optional[str] = None, **metadata) -> StreamEvent:
        """Create Gemini-specific unavailable event."""
        return super().create_stream_unavailable_event(
            reason or "JSON parsing issues with tools",
            provider="gemini",
            **metadata
        )


# Streaming adapter registry
_streaming_adapters: Dict[str, StreamingCapableAdapter] = {}

# Register core streaming adapters
_streaming_adapters['default'] = DefaultStreamingAdapter()
_streaming_adapters['ollama'] = OllamaStreamingAdapter()
_streaming_adapters['anthropic'] = AnthropicStreamingAdapter()
_streaming_adapters['claude'] = AnthropicStreamingAdapter()  # Alias
_streaming_adapters['gemini'] = GeminiStreamingAdapter()


def get_streaming_adapter(provider_name: str) -> StreamingCapableAdapter:
    """
    Get streaming adapter for provider with fallback to default.
    
    Args:
        provider_name: Provider name (e.g., "anthropic", "ollama", "gemini")
        
    Returns:
        StreamingCapableAdapter instance
    """
    name_lower = provider_name.lower()
    
    # Exact match first
    if name_lower in _streaming_adapters:
        return _streaming_adapters[name_lower]
        
    # Provider prefixes or substrings
    if "ollama" in name_lower:
        return _streaming_adapters["ollama"]
    if "claude" in name_lower or "anthropic" in name_lower:
        return _streaming_adapters["anthropic"]
    if "gemini" in name_lower:
        return _streaming_adapters["gemini"]
        
    return _streaming_adapters["default"]


def add_streaming_adapter(name: str, adapter: StreamingCapableAdapter) -> None:
    """Register a custom streaming adapter."""
    _streaming_adapters[name] = adapter


def list_streaming_adapters() -> List[str]:
    """List all registered streaming adapter names."""
    return sorted(_streaming_adapters.keys())