"""
LLM Provider Protocols for PraisonAI Agents.

Defines minimal protocol interfaces for LLM providers to enable
extensibility without vendor lock-in to litellm or any specific provider.

No heavy imports - only stdlib and typing.
"""

from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Protocol, Union, runtime_checkable


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """
    Protocol defining the interface that LLM providers must implement.
    
    This enables switching between different LLM backends (litellm, openai,
    anthropic, local models, etc.) without modifying core agent code.
    
    Implementations must provide both sync and async variants for
    production flexibility.
    """
    
    model: str
    
    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[Dict[str, Any], Iterator[Dict[str, Any]]]:
        """
        Generate chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool schemas for function calling
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to return streaming iterator
            **kwargs: Provider-specific options
            
        Returns:
            Single response dict or streaming iterator of response chunks
        """
        ...
    
    async def achat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[Dict[str, Any], AsyncIterator[Dict[str, Any]]]:
        """
        Async version of chat.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool schemas for function calling
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to return async streaming iterator
            **kwargs: Provider-specific options
            
        Returns:
            Single response dict or async streaming iterator of response chunks
        """
        ...
    
    def get_token_count(self, text: str) -> int:
        """
        Count tokens in text for the current model.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        ...
    
    def get_context_length(self) -> int:
        """
        Get maximum context length for the current model.
        
        Returns:
            Maximum context length in tokens
        """
        ...


@runtime_checkable
class ModelCapabilitiesProtocol(Protocol):
    """
    Protocol for querying model capabilities.
    
    Enables runtime capability detection for different models
    without hardcoded capability tables.
    """
    
    def supports_streaming(self, model: str) -> bool:
        """Check if model supports streaming responses."""
        ...
    
    def supports_function_calling(self, model: str) -> bool:
        """Check if model supports function/tool calling."""
        ...
    
    def supports_structured_output(self, model: str) -> bool:
        """Check if model supports structured JSON output."""
        ...
    
    def supports_vision(self, model: str) -> bool:
        """Check if model supports vision/image inputs."""
        ...
    
    def get_max_tokens(self, model: str) -> Optional[int]:
        """Get maximum context length for model."""
        ...


@runtime_checkable
class LLMRateLimiterProtocol(Protocol):
    """
    Protocol for LLM request rate limiting.
    
    Enables different rate limiting strategies without
    coupling to specific implementations.
    """
    
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire permission to make request.
        
        Args:
            tokens: Number of tokens in the request
            
        Raises:
            RateLimitError: If rate limit would be exceeded
        """
        ...
    
    def can_proceed(self, tokens: int = 1) -> bool:
        """
        Check if request can proceed without blocking.
        
        Args:
            tokens: Number of tokens in the request
            
        Returns:
            True if request can proceed immediately
        """
        ...
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """
        Get seconds to wait before request can proceed.
        
        Args:
            tokens: Number of tokens in the request
            
        Returns:
            Seconds to wait (0.0 if can proceed immediately)
        """
        ...


@runtime_checkable
class LLMFailoverProtocol(Protocol):
    """
    Protocol for LLM failover strategies.
    
    Enables automatic fallback to alternative models
    when primary models fail or are unavailable.
    """
    
    def get_fallback_model(self, failed_model: str, error: Exception) -> Optional[str]:
        """
        Get fallback model for failed request.
        
        Args:
            failed_model: Model that failed
            error: Exception that occurred
            
        Returns:
            Alternative model name or None if no fallback available
        """
        ...
    
    def should_retry(self, error: Exception) -> bool:
        """
        Check if error indicates retryable failure.
        
        Args:
            error: Exception that occurred
            
        Returns:
            True if should retry with fallback
        """
        ...
    
    def get_retry_delay(self, attempt: int) -> float:
        """
        Get delay before retry attempt.
        
        Args:
            attempt: Retry attempt number (1-based)
            
        Returns:
            Seconds to wait before retry
        """
        ...


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    
    def __init__(self, message: str, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider
        self.model = model
        super().__init__(message)


class RateLimitError(LLMProviderError):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: Optional[str] = None, retry_after: Optional[float] = None, provider: Optional[str] = None, model: Optional[str] = None):
        self.retry_after = retry_after
        super().__init__(message or "Rate limit exceeded", provider=provider, model=model)


class ModelNotAvailableError(LLMProviderError):
    """Raised when requested model is not available."""
    
    def __init__(self, model: str, provider: Optional[str] = None):
        message = f"Model '{model}' is not available{f' from provider {provider}' if provider else ''}"
        super().__init__(message, provider=provider, model=model)


class ContextLengthExceededError(LLMProviderError):
    """Raised when input exceeds model's context length."""
    
    def __init__(self, tokens: int, max_tokens: int, provider: Optional[str] = None, model: Optional[str] = None):
        self.tokens = tokens
        self.max_tokens = max_tokens
        super().__init__(f"Input length ({tokens} tokens) exceeds model limit ({max_tokens} tokens)", provider=provider, model=model)


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """
    Protocol for provider-specific LLM adaptations.
    
    This replaces scattered provider dispatch logic throughout the core.
    Each provider implements these hooks to handle provider-specific quirks
    without requiring if/elif branching in the core chat loop.
    
    Example:
        ```python
        class OllamaAdapter:
            def supports_prompt_caching(self) -> bool:
                return False
            
            def should_summarize_tools(self, iter_count: int) -> bool:
                return iter_count >= 3  # Ollama-specific threshold
            
            def format_tools(self, tools) -> list:
                return tools  # No special formatting needed
            
            def post_tool_iteration(self, state) -> None:
                if state.get('empty_response') and state.get('tools'):
                    # Add Ollama-specific tool summary
                    state['summary'] = "Tool results processed"
        ```
    """
    
    def supports_prompt_caching(self) -> bool:
        """Check if this provider supports prompt caching."""
        ...
    
    def should_summarize_tools(self, iter_count: int) -> bool:
        """Check if tools should be summarized at this iteration count."""
        ...
    
    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for this provider's requirements."""
        ...
    
    def post_tool_iteration(self, state: Dict[str, Any]) -> None:
        """Handle provider-specific post-tool processing."""
        ...
    
    def supports_structured_output(self) -> bool:
        """Check if provider supports structured JSON output."""
        ...
    
    def supports_streaming(self) -> bool:
        """Check if provider supports streaming responses."""
        ...


@runtime_checkable  
class UnifiedLLMProtocol(Protocol):
    """
    Unified protocol for LLM dispatch that consolidates the dual execution paths.
    
    This replaces the separate custom-LLM path (LLM.get_response) and OpenAI path 
    (OpenAIClient) with a single async-first protocol that all providers implement.
    
    Sync implementations must not call asyncio.run() from library internals.
    Provide native sync implementations or convert streaming responses
    to real Iterator[Dict[str, Any]] objects.
    """
    
    async def achat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[Dict[str, Any], AsyncIterator[Dict[str, Any]]]:
        """
        Primary async chat completion method.
        All LLM interactions go through this single path.
        """
        ...
    
    def chat_completion(
        self,
        messages: List[Dict[str, Any]], 
        **kwargs: Any
    ) -> Union[Dict[str, Any], Iterator[Dict[str, Any]]]:
        """
        Synchronous chat completion entry point.
        For streaming, implementations must return a real Iterator[Dict[str, Any]].
        """
        ...