"""
LLM Provider Adapters for Unified Protocol Dispatch.

Implements the adapter pattern to consolidate the dual execution paths
into a single async-first protocol-driven architecture.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union, Iterator, AsyncIterator, Callable, TYPE_CHECKING
from .protocols import UnifiedLLMProtocol

if TYPE_CHECKING:
    from .llm import LLM
    from .openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class LiteLLMAdapter:
    """
    Adapter for LiteLLM-backed LLM instances.
    
    Wraps the existing LLM class to conform to the UnifiedLLMProtocol,
    ensuring all provider interactions go through a single async dispatch.
    """
    
    def __init__(self, llm_instance: 'LLM'):
        """Initialize adapter with existing LLM instance."""
        self.llm = llm_instance
        self.model = llm_instance.model
    
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
        Async chat completion using existing LLM.get_response_async.
        
        This consolidates the custom-LLM path into the unified protocol.
        """
        # Convert messages to prompt format expected by existing LLM
        prompt = self._convert_messages_to_prompt(messages)
        
        # Extract system prompt if present
        system_prompt = None
        if messages and messages[0].get('role') == 'system':
            system_prompt = messages[0].get('content')
            # Use remaining messages as chat history
            chat_history = messages[1:] if len(messages) > 1 else None
        else:
            chat_history = messages[:-1] if len(messages) > 1 else None
            prompt = messages[-1].get('content', '') if messages else ''
        
        # Call existing async method
        response = await self.llm.get_response_async(
            prompt=prompt,
            system_prompt=system_prompt,
            chat_history=chat_history,
            temperature=temperature,
            tools=tools,
            stream=stream,
            verbose=kwargs.get('verbose', False),
            **kwargs
        )
        
        # Convert response to standard format
        if stream:
            # For streaming, wrap in async iterator that yields standard chunks
            return self._convert_stream_response(response)
        else:
            return self._convert_response_to_standard_format(response)
    
    def chat_completion(
        self,
        messages: List[Dict[str, Any]], 
        **kwargs: Any
    ) -> Union[Dict[str, Any], Iterator[Dict[str, Any]]]:
        """
        Sync wrapper around async chat completion.
        
        Uses asyncio.run to execute async method, following the pattern
        of sync methods being thin wrappers around async implementations.
        """
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.achat_completion(messages, **kwargs))
        else:
            # Already in a loop, we need to handle this differently
            # Create a new event loop in a thread
            import concurrent.futures
            import threading
            
            def run_in_thread():
                return asyncio.run(self.achat_completion(messages, **kwargs))
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
    
    def _convert_messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Convert OpenAI-style messages to prompt string."""
        if not messages:
            return ""
        
        # If single message, return its content
        if len(messages) == 1:
            return messages[0].get('content', '')
        
        # For multiple messages, use the last user message as prompt
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                return msg.get('content', '')
        
        return messages[-1].get('content', '') if messages else ''
    
    async def _convert_stream_response(self, response_stream) -> AsyncIterator[Dict[str, Any]]:
        """Convert LLM stream response to standard format."""
        # Implementation depends on the actual stream format from LLM.get_response_async
        # This is a placeholder - would need to be implemented based on actual stream format
        if hasattr(response_stream, '__aiter__'):
            async for chunk in response_stream:
                yield self._convert_chunk_to_standard_format(chunk)
        else:
            # If not async iterable, yield the full response as a single chunk
            yield self._convert_response_to_standard_format(response_stream)
    
    def _convert_response_to_standard_format(self, response: Any) -> Dict[str, Any]:
        """Convert LLM response to standard OpenAI-like format."""
        if isinstance(response, str):
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response
                    },
                    "finish_reason": "stop"
                }]
            }
        return response
    
    def _convert_chunk_to_standard_format(self, chunk: Any) -> Dict[str, Any]:
        """Convert LLM stream chunk to standard format."""
        if isinstance(chunk, str):
            return {
                "choices": [{
                    "delta": {
                        "content": chunk
                    }
                }]
            }
        return chunk


class OpenAIAdapter:
    """
    Adapter for direct OpenAI client interactions.
    
    Wraps the existing OpenAIClient to conform to the UnifiedLLMProtocol,
    consolidating the OpenAI-specific path into the unified dispatch.
    """
    
    def __init__(self, client: 'OpenAIClient', model: str = "gpt-4o-mini"):
        """Initialize adapter with OpenAI client."""
        self.client = client
        self.model = model
    
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
        Async chat completion using OpenAI client.
        
        This consolidates the OpenAI path into the unified protocol.
        """
        # Delegate to the existing OpenAI client's async method with tools
        return await self.client.achat_completion_with_tools(
            messages=messages,
            model=self.model,
            tools=tools,
            temperature=temperature,
            stream=stream,
            execute_tool_fn=kwargs.get('execute_tool_fn'),
            console=kwargs.get('console'),
            display_fn=kwargs.get('display_fn'),
            reasoning_steps=kwargs.get('reasoning_steps', False),
            verbose=kwargs.get('verbose', True),
            max_iterations=kwargs.get('max_iterations', 10),
            **{k: v for k, v in kwargs.items() if k not in ['execute_tool_fn', 'console', 'display_fn', 'reasoning_steps', 'verbose', 'max_iterations']}
        )
    
    def chat_completion(
        self,
        messages: List[Dict[str, Any]], 
        **kwargs: Any
    ) -> Union[Dict[str, Any], Iterator[Dict[str, Any]]]:
        """
        Sync chat completion using OpenAI client.
        
        Uses the existing sync method from OpenAIClient.
        """
        return self.client.chat_completion_with_tools(
            messages=messages,
            model=self.model,
            tools=kwargs.get('tools'),
            temperature=kwargs.get('temperature', 1.0),
            stream=kwargs.get('stream', True),
            execute_tool_fn=kwargs.get('execute_tool_fn'),
            console=kwargs.get('console'),
            display_fn=kwargs.get('display_fn'),
            reasoning_steps=kwargs.get('reasoning_steps', False),
            verbose=kwargs.get('verbose', True),
            max_iterations=kwargs.get('max_iterations', 10),
            **{k: v for k, v in kwargs.items() if k not in ['tools', 'temperature', 'stream', 'execute_tool_fn', 'console', 'display_fn', 'reasoning_steps', 'verbose', 'max_iterations']}
        )


class UnifiedLLMDispatcher:
    """
    Unified LLM dispatcher that implements UnifiedLLMProtocol.
    
    This is the single entry point for all LLM interactions,
    routing to the appropriate adapter based on configuration.
    """
    
    def __init__(self, adapter: Union[LiteLLMAdapter, OpenAIAdapter]):
        """Initialize with a specific adapter."""
        self.adapter = adapter
        self.model = adapter.model
    
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
        """Primary async chat completion method."""
        return await self.adapter.achat_completion(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs
        )
    
    def chat_completion(
        self,
        messages: List[Dict[str, Any]], 
        **kwargs: Any
    ) -> Union[Dict[str, Any], Iterator[Dict[str, Any]]]:
        """Sync wrapper around async method."""
        return self.adapter.chat_completion(messages=messages, **kwargs)


def create_llm_dispatcher(
    llm_instance: Optional['LLM'] = None,
    openai_client: Optional['OpenAIClient'] = None,
    model: str = "gpt-4o-mini"
) -> UnifiedLLMDispatcher:
    """
    Factory function to create appropriate LLM dispatcher.
    
    Args:
        llm_instance: Existing LLM instance (for LiteLLM path)
        openai_client: Existing OpenAI client (for OpenAI path)
        model: Model name to use
        
    Returns:
        UnifiedLLMDispatcher configured with appropriate adapter
        
    Raises:
        ValueError: If neither llm_instance nor openai_client provided
    """
    if llm_instance is not None:
        adapter = LiteLLMAdapter(llm_instance)
    elif openai_client is not None:
        adapter = OpenAIAdapter(openai_client, model)
    else:
        raise ValueError("Either llm_instance or openai_client must be provided")
    
    return UnifiedLLMDispatcher(adapter)