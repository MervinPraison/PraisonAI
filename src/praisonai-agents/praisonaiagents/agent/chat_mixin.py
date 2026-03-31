"""
Chat and LLM functionality for Agent class.

This module contains methods related to chat, LLM communication, streaming,
and conversation processing. Extracted from the main agent.py file for better maintainability.

Round 1 of agent god class decomposition - targeting ~1500 lines reduction.
"""

import os
import time
import json
import logging
import asyncio
import contextlib
from typing import List, Optional, Any, Dict, Union, Literal, Callable, Generator

from praisonaiagents._logging import get_logger


class ChatMixin:
    """Mixin class containing chat and LLM communication methods for the Agent class.
    
    This mixin handles:
    - Main chat() and achat() methods
    - LLM response processing and formatting  
    - Streaming functionality
    - Tool call handling in chat context
    - Response templating and formatting
    """

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
            attachments: Optional list of image/file paths that are ephemeral
                        (used for THIS turn only, NEVER stored in history).
                        Supports: file paths, URLs, or data URIs.
            tool_choice: Optional tool choice mode ('auto', 'required', 'none').
                        'required' forces the LLM to call a tool before responding.
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
        
        Returns:
            The agent's response as a string, or None if blocked by hooks
        """
        # This method needs to be implemented by moving logic from agent.py
        # Placeholder for now - actual implementation will be moved from main agent.py
        return self._chat_impl(
            prompt, temperature, tools, output_json, output_pydantic, 
            reasoning_steps, stream, task_name, task_description, task_id, 
            config, force_retrieval, skip_retrieval, attachments, None, tool_choice
        )
    
    def _chat_impl(self, prompt, temperature, tools, output_json, output_pydantic, 
                   reasoning_steps, stream, task_name, task_description, task_id, 
                   config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None):
        """Internal chat implementation (extracted for trace wrapping).
        
        This method will contain the full chat logic moved from agent.py.
        """
        raise NotImplementedError("This method needs to be moved from agent.py")

    async def achat(self, prompt: str, temperature=1.0, tools=None, output_json=None, 
                   output_pydantic=None, reasoning_steps=False, task_name=None, 
                   task_description=None, task_id=None, attachments=None):
        """Async version of chat method.
        
        This method will contain the async chat logic moved from agent.py.
        """
        raise NotImplementedError("This method needs to be moved from agent.py")

    def _process_agent_output(self, response: Any) -> str:
        """Process and format agent output from LLM.
        
        This method will contain output processing logic moved from agent.py.
        """
        raise NotImplementedError("This method needs to be moved from agent.py")

    def _format_response(self, response: str, **kwargs) -> str:
        """Format agent response according to configured templates.
        
        This method will contain response formatting logic moved from agent.py.
        """
        raise NotImplementedError("This method needs to be moved from agent.py")

    def _handle_tool_calls(self, tool_calls: List[Any]) -> Any:
        """Handle tool calls from LLM in chat context.
        
        This method will contain tool call handling logic moved from agent.py.
        """
        raise NotImplementedError("This method needs to be moved from agent.py")

    def _build_multimodal_prompt(self, prompt: str, attachments: Optional[List[str]] = None) -> Union[str, List[Dict[str, Any]]]:
        """Build multimodal prompt from text and attachments.
        
        This method will contain multimodal prompt building logic moved from agent.py.
        """
        if not attachments:
            return prompt
        # Placeholder - actual implementation to be moved
        raise NotImplementedError("This method needs to be moved from agent.py")

    def chat_with_context(self, prompt: str, context: Optional[Dict[str, Any]] = None, **kwargs) -> Optional[str]:
        """Chat with additional context information.
        
        This method will contain context-aware chat logic moved from agent.py.
        """
        raise NotImplementedError("This method needs to be moved from agent.py")