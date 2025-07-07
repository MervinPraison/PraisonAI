"""Lightweight OpenAI-only provider"""

import os
from typing import Dict, List, Optional, Union, AsyncIterator, Iterator
from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """Lightweight OpenAI-only provider using OpenAI SDK directly."""
    
    # Minimal context windows for OpenAI models (75% of actual for safety)
    MODEL_WINDOWS = {
        "gpt-4": 6144,                    # 8,192 actual
        "gpt-4-32k": 24576,              # 32,768 actual
        "gpt-4-turbo": 96000,            # 128,000 actual
        "gpt-4-turbo-preview": 96000,    # 128,000 actual
        "gpt-4o": 96000,                 # 128,000 actual
        "gpt-4o-mini": 96000,            # 128,000 actual
        "gpt-3.5-turbo": 12288,          # 16,385 actual
        "gpt-3.5-turbo-16k": 12288,      # 16,385 actual
        "o1-preview": 96000,             # 128,000 actual
        "o1-mini": 96000,                # 128,000 actual
    }
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        """
        Initialize with minimal dependencies.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Base URL for API calls (defaults to OPENAI_API_BASE env var)
            **kwargs: Additional OpenAI client parameters
        """
        try:
            from openai import OpenAI, AsyncOpenAI
        except ImportError:
            raise ImportError(
                "OpenAI SDK is required. Install with: pip install openai"
            )
        
        # Use environment variables as defaults
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        base_url = base_url or os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
        
        # Handle local server case
        if base_url and not api_key:
            api_key = "not-needed"  # Placeholder for local servers
        
        if not api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter."
            )
        
        # Initialize both sync and async clients
        self.client = OpenAI(api_key=api_key, base_url=base_url, **kwargs)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url, **kwargs)
    
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
        Direct OpenAI completion - no extra dependencies.
        
        Args:
            messages: List of message dictionaries
            model: OpenAI model name
            temperature: Sampling temperature
            tools: Optional tool definitions
            stream: Whether to stream response
            **kwargs: Additional OpenAI parameters
            
        Returns:
            OpenAI ChatCompletion response or stream
        """
        # Build parameters
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
        
        # Add any additional OpenAI-specific parameters
        for key in ['max_tokens', 'top_p', 'frequency_penalty', 'presence_penalty',
                    'response_format', 'seed', 'stop', 'logprobs', 'top_logprobs']:
            if key in kwargs:
                params[key] = kwargs[key]
        
        # Make the API call
        response = self.client.chat.completions.create(**params)
        
        # Convert to standard dict format if not streaming
        if not stream:
            return response.model_dump()
        
        return response
    
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
        Async OpenAI completion.
        
        Args:
            messages: List of message dictionaries
            model: OpenAI model name
            temperature: Sampling temperature
            tools: Optional tool definitions
            stream: Whether to stream response
            **kwargs: Additional OpenAI parameters
            
        Returns:
            OpenAI ChatCompletion response or async stream
        """
        # Build parameters
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
        
        # Add any additional OpenAI-specific parameters
        for key in ['max_tokens', 'top_p', 'frequency_penalty', 'presence_penalty',
                    'response_format', 'seed', 'stop', 'logprobs', 'top_logprobs']:
            if key in kwargs:
                params[key] = kwargs[key]
        
        # Make the async API call
        response = await self.async_client.chat.completions.create(**params)
        
        # Convert to standard dict format if not streaming
        if not stream:
            return response.model_dump()
        
        return response
    
    def get_context_window(self, model: str) -> int:
        """
        Get context window for OpenAI model.
        
        Args:
            model: OpenAI model name
            
        Returns:
            Context window size in tokens
        """
        # Check exact matches first
        if model in self.MODEL_WINDOWS:
            return self.MODEL_WINDOWS[model]
        
        # Check prefix matches
        for prefix, window in self.MODEL_WINDOWS.items():
            if model.startswith(prefix):
                return window
        
        # Default to 4k tokens (safe default for unknown models)
        return 4000