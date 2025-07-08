"""
OpenAI Client Module

This module provides a unified interface for OpenAI API interactions,
supporting both synchronous and asynchronous operations.
"""

import os
import logging
from typing import Any, Dict, List, Optional, Union, AsyncIterator, Iterator
from openai import OpenAI, AsyncOpenAI
from openai.types.chat import ChatCompletionChunk
import asyncio
from pydantic import BaseModel

# Constants
LOCAL_SERVER_API_KEY_PLACEHOLDER = "not-needed"

class OpenAIClient:
    """
    Unified OpenAI client wrapper for sync/async operations.
    
    This class encapsulates all OpenAI-specific logic, providing a clean
    interface for chat completions, streaming, and structured outputs.
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize the OpenAI client with proper API key handling.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom base URL for API endpoints (defaults to OPENAI_API_BASE env var)
        """
        # Use provided values or fall back to environment variables
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL")
        
        # For local servers like LM Studio, allow minimal API key
        if self.base_url and not self.api_key:
            self.api_key = LOCAL_SERVER_API_KEY_PLACEHOLDER
        elif not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for the default OpenAI service. "
                "If you are targeting a local server (e.g., LM Studio), ensure OPENAI_API_BASE is set "
                f"(e.g., 'http://localhost:1234/v1') and you can use a placeholder API key by setting OPENAI_API_KEY='{LOCAL_SERVER_API_KEY_PLACEHOLDER}'"
            )
        
        # Initialize synchronous client (lazy loading for async)
        self._sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self._async_client = None
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
    
    @property
    def sync_client(self) -> OpenAI:
        """Get the synchronous OpenAI client."""
        return self._sync_client
    
    @property
    def async_client(self) -> AsyncOpenAI:
        """Get the asynchronous OpenAI client (lazy initialization)."""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._async_client
    
    def create_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[Any, Iterator[ChatCompletionChunk]]:
        """
        Create a chat completion using the synchronous client.
        
        Args:
            messages: List of message dictionaries
            model: Model to use for completion
            temperature: Sampling temperature
            stream: Whether to stream the response
            tools: List of tools/functions available
            tool_choice: Tool selection preference
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            ChatCompletion object or stream iterator
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        
        try:
            return self._sync_client.chat.completions.create(**params)
        except Exception as e:
            self.logger.error(f"Error creating completion: {e}")
            raise
    
    async def acreate_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[Any, AsyncIterator[ChatCompletionChunk]]:
        """
        Create a chat completion using the asynchronous client.
        
        Args:
            messages: List of message dictionaries
            model: Model to use for completion
            temperature: Sampling temperature
            stream: Whether to stream the response
            tools: List of tools/functions available
            tool_choice: Tool selection preference
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            ChatCompletion object or async stream iterator
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
        
        try:
            return await self.async_client.chat.completions.create(**params)
        except Exception as e:
            self.logger.error(f"Error creating async completion: {e}")
            raise
    
    def parse_structured_output(
        self,
        messages: List[Dict[str, Any]],
        response_format: BaseModel,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        **kwargs
    ) -> Any:
        """
        Parse structured output using the beta.chat.completions.parse API.
        
        Args:
            messages: List of message dictionaries
            response_format: Pydantic model for response validation
            model: Model to use for completion
            temperature: Sampling temperature
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            Parsed response according to the response_format
        """
        try:
            response = self._sync_client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                **kwargs
            )
            return response.choices[0].message.parsed
        except Exception as e:
            self.logger.error(f"Error parsing structured output: {e}")
            raise
    
    async def aparse_structured_output(
        self,
        messages: List[Dict[str, Any]],
        response_format: BaseModel,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        **kwargs
    ) -> Any:
        """
        Parse structured output using the async beta.chat.completions.parse API.
        
        Args:
            messages: List of message dictionaries
            response_format: Pydantic model for response validation
            model: Model to use for completion
            temperature: Sampling temperature
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            Parsed response according to the response_format
        """
        try:
            response = await self.async_client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                **kwargs
            )
            return response.choices[0].message.parsed
        except Exception as e:
            self.logger.error(f"Error parsing async structured output: {e}")
            raise
    
    def close(self):
        """Close the OpenAI clients."""
        if hasattr(self._sync_client, 'close'):
            self._sync_client.close()
        if self._async_client and hasattr(self._async_client, 'close'):
            self._async_client.close()
    
    async def aclose(self):
        """Asynchronously close the OpenAI clients."""
        if hasattr(self._sync_client, 'close'):
            await asyncio.to_thread(self._sync_client.close)
        if self._async_client and hasattr(self._async_client, 'aclose'):
            await self._async_client.aclose()


# Global client instance (similar to main.py pattern)
_global_client = None

def get_openai_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAIClient:
    """
    Get or create a global OpenAI client instance.
    
    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        base_url: Custom base URL for API endpoints
        
    Returns:
        OpenAIClient instance
    """
    global _global_client
    
    if _global_client is None:
        _global_client = OpenAIClient(api_key=api_key, base_url=base_url)
    
    return _global_client