"""
Chat and LLM interaction mixin for Agent class.

This module contains methods related to chat, streaming, LLM interactions, and response processing.
Extracted from the main agent.py file as part of the god class decomposition.
"""

import os
import time
import json
import asyncio
import threading
from typing import List, Optional, Any, Dict, Union, Callable, Generator
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

# Lazy-loaded modules (same pattern as agent.py)
_lazy_import_lock = threading.Lock()
_llm_module = None
_main_module = None

def _get_llm_functions():
    """Lazy load LLM functions (thread-safe)."""
    global _llm_module
    if _llm_module is None:
        with _lazy_import_lock:
            if _llm_module is None:
                from ..llm import get_openai_client, process_stream_chunks
                _llm_module = {
                    'get_openai_client': get_openai_client,
                    'process_stream_chunks': process_stream_chunks,
                }
    return _llm_module

def _get_display_functions():
    """Lazy load display functions from main module (thread-safe)."""
    global _main_module
    if _main_module is None:
        with _lazy_import_lock:
            if _main_module is None:
                from ..main import (
                    display_error,
                    display_instruction,
                    display_interaction,
                    display_generating,
                    display_self_reflection,
                    ReflectionOutput,
                    adisplay_instruction,
                    execute_sync_callback
                )
                _main_module = {
                    'display_error': display_error,
                    'display_instruction': display_instruction,
                    'display_interaction': display_interaction,
                    'display_generating': display_generating,
                    'display_self_reflection': display_self_reflection,
                    'ReflectionOutput': ReflectionOutput,
                    'adisplay_instruction': adisplay_instruction,
                    'execute_sync_callback': execute_sync_callback,
                }
    return _main_module


class ChatMixin:
    """
    Mixin class containing chat and LLM interaction methods for the Agent class.
    
    This mixin handles:
    - chat() and achat() methods
    - LLM communication and streaming
    - Response formatting and processing
    - Tool call handling in chat context
    - Multimodal prompt building
    """

    @property
    def stream_emitter(self) -> Optional[Any]:
        """Get the current stream emitter."""
        return getattr(self, '_stream_emitter', None)

    @stream_emitter.setter
    def stream_emitter(self, value: Optional[Any]) -> None:
        """Set the stream emitter."""
        setattr(self, '_stream_emitter', value)

    def chat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None, 
             output_json: Optional[Any] = None, output_pydantic: Optional[Any] = None, 
             reasoning_steps: bool = False, stream: Optional[bool] = None, 
             task_name: Optional[str] = None, task_description: Optional[str] = None,
             task_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None,
             force_retrieval: bool = False, skip_retrieval: bool = False,
             attachments: Optional[List[str]] = None, tool_choice: Optional[str] = None) -> Optional[str]:
        """
        Chat with the agent.
        
        Args:
            prompt: Text query that WILL be stored in chat_history
            temperature: Sampling temperature (0.0-2.0)
            tools: Tools available for this conversation
            output_json: JSON schema for structured output
            output_pydantic: Pydantic model for structured output
            reasoning_steps: Whether to include reasoning steps
            stream: Whether to stream the response
            task_name: Name of the task for context
            task_description: Description of the task
            task_id: Unique identifier for the task
            config: Additional configuration
            force_retrieval: Force knowledge retrieval
            skip_retrieval: Skip knowledge retrieval
            attachments: Optional list of image/file paths that are ephemeral
                        (used for THIS turn only, NEVER stored in history).
                        Supports: file paths, URLs, or data URIs.
            tool_choice: Optional tool choice mode ('auto', 'required', 'none').
                        'required' forces the LLM to call a tool before responding.
        
        Returns:
            The agent's response as a string
        """
        # Emit context trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.agent_start(self.name, {"role": self.role, "goal": self.goal})
        
        try:
            return self._chat_impl(prompt, temperature, tools, output_json, output_pydantic, 
                                 reasoning_steps, stream, task_name, task_description, task_id, 
                                 config, force_retrieval, skip_retrieval, attachments, 
                                 _trace_emitter, tool_choice)
        finally:
            _trace_emitter.agent_end(self.name)
    
    def _chat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, 
                   stream, task_name, task_description, task_id, config, force_retrieval, 
                   skip_retrieval, attachments, _trace_emitter, tool_choice=None):
        """
        Internal chat implementation (extracted for trace wrapping).
        
        NOTE: This is a placeholder implementation. The actual implementation would need to be
        moved from agent.py, including all the complex logic for:
        - Rate limiting
        - Multimodal prompts
        - Template processing
        - LLM calls
        - Tool handling
        - Response processing
        """
        logger.debug(f"{self.name}: Chat implementation called with prompt: {prompt[:100]}...")
        
        # TODO: Move actual implementation from agent.py lines 6278-6793
        # This includes:
        # - Rate limiter logic
        # - Multimodal prompt building
        # - Template processing
        # - Knowledge retrieval
        # - LLM client calls
        # - Streaming handling
        # - Tool processing
        # - Response formatting
        
        raise NotImplementedError("Chat implementation needs to be moved from agent.py")

    async def achat(self, prompt: str, temperature=1.0, tools=None, output_json=None, 
                    output_pydantic=None, reasoning_steps=False, task_name=None, 
                    task_description=None, task_id=None, attachments=None):
        """
        Async version of chat.
        
        Args:
            prompt: Text query for the agent
            temperature: Sampling temperature
            tools: Available tools
            output_json: JSON schema for output
            output_pydantic: Pydantic model for output
            reasoning_steps: Include reasoning steps
            task_name: Task name for context
            task_description: Task description
            task_id: Task identifier
            attachments: Ephemeral file attachments
            
        Returns:
            Agent's response as string
        """
        logger.debug(f"{self.name}: Async chat called with prompt: {prompt[:100]}...")
        
        # TODO: Move actual async implementation from agent.py lines 6794+
        # Should be similar to sync chat but with async/await patterns
        
        raise NotImplementedError("Async chat implementation needs to be moved from agent.py")

    def _build_multimodal_prompt(self, prompt: str, attachments: Optional[List[str]] = None) -> Union[str, List[Dict[str, Any]]]:
        """
        Build a multimodal prompt from text and attachments.
        
        Args:
            prompt: Text prompt
            attachments: List of file paths, URLs, or data URIs
            
        Returns:
            Either a string (text-only) or list of content objects (multimodal)
        """
        if not attachments:
            return prompt
            
        # TODO: Move actual implementation from agent.py lines 5555+
        # This includes logic for:
        # - File reading and encoding
        # - URL fetching
        # - Data URI processing
        # - Image/file type detection
        # - Content formatting for LLM
        
        logger.debug(f"{self.name}: Building multimodal prompt with {len(attachments)} attachments")
        raise NotImplementedError("Multimodal prompt building needs to be moved from agent.py")

    def chat_with_context(self, *args, **kwargs):
        """
        Chat with additional context management.
        
        TODO: Move actual implementation from agent.py lines 4155+
        """
        logger.debug(f"{self.name}: Chat with context called")
        raise NotImplementedError("Chat with context implementation needs to be moved from agent.py")

    def _format_response(self, response: str, **kwargs) -> str:
        """
        Format the agent's response according to templates and configurations.
        
        Args:
            response: Raw response from LLM
            **kwargs: Additional formatting parameters
            
        Returns:
            Formatted response
        """
        # TODO: Move response formatting logic from agent.py
        # This includes template application, markdown formatting, etc.
        
        logger.debug(f"{self.name}: Formatting response of length {len(response)}")
        return response

    def _process_agent_output(self, output: Any, **kwargs) -> Any:
        """
        Process the agent's output through various transformations.
        
        Args:
            output: Raw output from agent processing
            **kwargs: Processing parameters
            
        Returns:
            Processed output
        """
        # TODO: Move output processing logic from agent.py
        # This includes validation, transformation, and cleanup
        
        logger.debug(f"{self.name}: Processing agent output")
        return output

    def _handle_tool_calls(self, tool_calls: List[Dict[str, Any]], **kwargs) -> List[Any]:
        """
        Handle tool calls in the context of chat interactions.
        
        Args:
            tool_calls: List of tool call objects from LLM
            **kwargs: Additional handling parameters
            
        Returns:
            List of tool call results
        """
        # TODO: Move tool call handling logic from agent.py
        # This includes tool execution, result formatting, and error handling
        
        logger.debug(f"{self.name}: Handling {len(tool_calls)} tool calls")
        return []

    # Additional streaming and chat-related methods would go here
    # These would be extracted from agent.py as part of the full implementation