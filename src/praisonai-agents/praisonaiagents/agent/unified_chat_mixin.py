"""
Unified Chat Mixin for Agent class.

This module consolidates the dual execution paths (custom LLM vs OpenAI)
into a single async-first protocol-driven implementation, eliminating
the DRY violation and maintenance burden described in Issue #1304.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union

from ..llm import create_llm_dispatcher, UnifiedLLMDispatcher


class UnifiedChatMixin:
    """
    Unified chat implementation that replaces dual execution paths.
    
    This mixin consolidates:
    - Path A: LLM.get_response() / LLM.get_response_async() 
    - Path B: OpenAIClient chat completion
    
    Into a single async-first protocol-driven dispatch using UnifiedLLMDispatcher.
    """
    
    def _get_unified_dispatcher(self) -> UnifiedLLMDispatcher:
        """
        Get or create the unified LLM dispatcher for this agent.
        
        This method implements the provider selection logic that was
        previously scattered in _chat_completion() method.
        """
        if hasattr(self, '_unified_dispatcher') and self._unified_dispatcher is not None:
            return self._unified_dispatcher
        
        # Determine which adapter to use based on existing agent configuration
        if self._using_custom_llm and hasattr(self, 'llm_instance'):
            # Use LiteLLM adapter for custom LLM instances
            dispatcher = create_llm_dispatcher(llm_instance=self.llm_instance)
        else:
            # Use OpenAI adapter for direct OpenAI access
            if not hasattr(self, '_openai_client') or self._openai_client is None:
                # Initialize OpenAI client if not present
                from ..llm import get_openai_client
                self._openai_client = get_openai_client(api_key=getattr(self, 'api_key', None))
            dispatcher = create_llm_dispatcher(openai_client=self._openai_client, model=self.llm)
        
        # Cache the dispatcher
        self._unified_dispatcher = dispatcher
        return dispatcher
    
    def _unified_chat_completion(
        self, 
        messages: List[Dict[str, Any]], 
        temperature: float = 1.0, 
        tools: Optional[List[Dict[str, Any]]] = None, 
        stream: bool = True,
        reasoning_steps: bool = False,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Unified sync chat completion method.
        
        This replaces the existing _chat_completion() method's dual dispatch logic
        with a single path through UnifiedLLMDispatcher.
        """
        start_time = time.time()
        
        # Get unified dispatcher (handles provider selection)
        dispatcher = self._get_unified_dispatcher()
        
        # Use the same message processing logic but route through unified dispatcher
        formatted_tools = self._format_tools_for_completion(tools)
        
        try:
            # Single dispatch path for all providers
            final_response = dispatcher.chat_completion(
                messages=messages,
                tools=formatted_tools,
                temperature=temperature,
                max_tokens=getattr(self, 'max_tokens', None),
                stream=stream,
                response_format=response_format,
                **{
                    'reasoning_steps': reasoning_steps,
                    'task_name': task_name,
                    'task_description': task_description,
                    'task_id': task_id,
                }
            )
            
            return final_response
            
        except Exception as e:
            logging.error(f"Unified chat completion failed: {e}")
            # Apply the same error handling as the original implementation
            raise
    
    async def _unified_achat_completion(
        self, 
        messages: List[Dict[str, Any]], 
        temperature: float = 1.0, 
        tools: Optional[List[Dict[str, Any]]] = None, 
        stream: bool = True,
        reasoning_steps: bool = False,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Unified async chat completion method.
        
        This provides native async implementation, eliminating the need
        for separate async/sync implementations in the LLM layer.
        """
        start_time = time.time()
        
        # Get unified dispatcher (handles provider selection)
        dispatcher = self._get_unified_dispatcher()
        
        # Use the same message processing logic but route through unified dispatcher
        formatted_tools = self._format_tools_for_completion(tools)
        
        try:
            # Single async dispatch path for all providers
            final_response = await dispatcher.achat_completion(
                messages=messages,
                tools=formatted_tools,
                temperature=temperature,
                max_tokens=getattr(self, 'max_tokens', None),
                stream=stream,
                response_format=response_format,
                **{
                    'reasoning_steps': reasoning_steps,
                    'task_name': task_name,
                    'task_description': task_description,
                    'task_id': task_id,
                }
            )
            
            return final_response
            
        except Exception as e:
            logging.error(f"Unified async chat completion failed: {e}")
            # Apply the same error handling as the original implementation
            raise