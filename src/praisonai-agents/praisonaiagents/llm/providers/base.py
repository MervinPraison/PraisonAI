"""Abstract base class for LLM providers"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union, AsyncIterator, Iterator
from pydantic import BaseModel


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[Dict, Iterator[Dict]]:
        """
        Execute completion request.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature
            tools: Optional list of tool definitions
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Completion response dict or stream iterator
        """
        pass
    
    @abstractmethod
    async def acompletion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[Dict, AsyncIterator[Dict]]:
        """
        Execute async completion request.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature
            tools: Optional list of tool definitions
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Completion response dict or async stream iterator
        """
        pass
    
    @abstractmethod
    def get_context_window(self, model: str) -> int:
        """
        Get context window size for model.
        
        Args:
            model: Model name
            
        Returns:
            Context window size in tokens
        """
        pass
    
    def is_context_limit_error(self, error_message: str) -> bool:
        """
        Check if error is related to context length.
        
        Args:
            error_message: Error message string
            
        Returns:
            True if context limit error, False otherwise
        """
        context_limit_phrases = [
            "maximum context length",
            "context window is too long",
            "context length exceeded",
            "context_length_exceeded",
            "max_tokens",
            "too many tokens"
        ]
        return any(phrase in error_message.lower() for phrase in context_limit_phrases)