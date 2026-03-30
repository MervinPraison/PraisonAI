"""
LLM Protocol Definitions.

Provides Protocol interfaces that define the minimal contract for LLM implementations.
This enables:
- Protocol-driven core: LLM protocols in core, heavy implementations in wrapper
- Testing: Mock LLM providers without real API calls
- Extensibility: Custom LLM providers (local models, custom APIs)

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Optional, Any, Dict, List, AsyncIterator, Iterator, Union


@runtime_checkable
class LLMProtocol(Protocol):
    """
    Core LLM interface for the Agent system.
    
    This defines the essential methods that any LLM provider must implement.
    Heavy implementations (HTTP clients, streaming parsers, provider-specific logic)
    should be in the wrapper layer, not core SDK.
    
    Example:
        ```python
        # Lightweight protocol implementation
        class MockLLM:
            def __init__(self, model: str = "mock"):
                self.model = model
            
            def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
                return {
                    "choices": [{"message": {"content": "Mock response"}}]
                }
            
            def stream(self, messages: List[Dict], **kwargs) -> Iterator[Dict[str, Any]]:
                yield {"choices": [{"delta": {"content": "Mock"}}]}
                yield {"choices": [{"delta": {"content": " response"}}]}
        
        # Use in agent
        llm: LLMProtocol = MockLLM()
        ```
    """
    
    def chat(
        self, 
        messages: List[Dict[str, Any]], 
        **kwargs
    ) -> Dict[str, Any]:
        """
        Synchronous chat completion.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.)
            
        Returns:
            Completion response in OpenAI-compatible format
        """
        ...
    
    def stream(
        self, 
        messages: List[Dict[str, Any]], 
        **kwargs
    ) -> Iterator[Dict[str, Any]]:
        """
        Streaming chat completion.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            **kwargs: Provider-specific parameters
            
        Yields:
            Stream chunks in OpenAI-compatible format
        """
        ...


@runtime_checkable
class AsyncLLMProtocol(Protocol):
    """
    Async LLM interface for high-performance scenarios.
    
    For LLM providers that support async operations.
    """
    
    async def achat(
        self, 
        messages: List[Dict[str, Any]], 
        **kwargs
    ) -> Dict[str, Any]:
        """Async chat completion."""
        ...
    
    async def astream(
        self, 
        messages: List[Dict[str, Any]], 
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        """Async streaming chat completion."""
        ...


@runtime_checkable
class EmbeddingProtocol(Protocol):
    """
    Protocol for embedding providers.
    
    Defines interface for converting text to vector embeddings.
    """
    
    def embed(
        self, 
        text: Union[str, List[str]], 
        **kwargs
    ) -> Union[List[float], List[List[float]]]:
        """
        Generate embeddings for text.
        
        Args:
            text: Single string or list of strings to embed
            **kwargs: Provider-specific parameters
            
        Returns:
            Single embedding vector or list of embedding vectors
        """
        ...


@runtime_checkable
class LLMConfigProtocol(Protocol):
    """
    Protocol for LLM configuration objects.
    
    Enables type checking and validation of LLM configurations.
    """
    model: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        ...


@runtime_checkable
class ModelCapabilitiesProtocol(Protocol):
    """
    Protocol for querying model capabilities.
    
    Enables feature detection without provider-specific knowledge.
    """
    
    def supports_streaming(self, model: str) -> bool:
        """Check if model supports streaming."""
        ...
    
    def supports_tool_calling(self, model: str) -> bool:
        """Check if model supports tool/function calling."""
        ...
    
    def supports_vision(self, model: str) -> bool:
        """Check if model supports image inputs."""
        ...
    
    def get_context_length(self, model: str) -> int:
        """Get maximum context length for model."""
        ...


@runtime_checkable
class LLMRouterProtocol(Protocol):
    """
    Protocol for intelligent model routing.
    
    Enables routing requests to different models based on criteria.
    """
    
    def route_request(
        self, 
        messages: List[Dict[str, Any]], 
        **kwargs
    ) -> str:
        """
        Determine which model to use for a request.
        
        Args:
            messages: The conversation messages
            **kwargs: Additional routing criteria
            
        Returns:
            Model identifier to use
        """
        ...


__all__ = [
    'LLMProtocol',
    'AsyncLLMProtocol', 
    'EmbeddingProtocol',
    'LLMConfigProtocol',
    'ModelCapabilitiesProtocol',
    'LLMRouterProtocol',
]