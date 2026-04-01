"""
Chat and LLM functionality mixin for Agent class.

This module contains all chat/LLM-related methods extracted from the Agent class
for better organization and maintainability.
"""

import os
import time
import json
import logging
import asyncio
from typing import List, Optional, Any, Dict, Union, Literal, Generator, Callable
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class ChatMixin:
    """
    Mixin class containing all chat and LLM-related functionality.
    
    This mixin handles:
    - chat() and achat() methods
    - LLM completion processing
    - Stream handling
    - Tool call processing
    - Response formatting
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
            ...other args...
        """
        # This method will be implemented by moving the actual implementation from agent.py
        # For now, this is a placeholder to maintain the mixin structure
        raise NotImplementedError("chat() method needs to be moved from agent.py")
    
    async def achat(self, prompt: str, temperature=1.0, tools=None, output_json=None, 
                    output_pydantic=None, reasoning_steps=False, task_name=None, 
                    task_description=None, task_id=None, attachments=None):
        """
        Async version of chat method.
        """
        # This method will be implemented by moving the actual implementation from agent.py
        # For now, this is a placeholder to maintain the mixin structure
        raise NotImplementedError("achat() method needs to be moved from agent.py")
    
    def _chat_completion(self, messages, temperature=1.0, tools=None, stream=True, 
                        reasoning_steps=False, task_name=None, task_description=None, 
                        task_id=None, response_format=None):
        """
        Core LLM completion method.
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("_chat_completion() method needs to be moved from agent.py")
    
    def _process_stream_response(self, messages, temperature, start_time, formatted_tools=None, reasoning_steps=False):
        """
        Process streaming LLM response.
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("_process_stream_response() method needs to be moved from agent.py")
    
    def _process_agent_output(self, response: str, prompt: str = "", tools_used: Optional[List[str]] = None) -> str:
        """
        Process and format agent output.
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("_process_agent_output() method needs to be moved from agent.py")
    
    def _format_response(self, response: str) -> str:
        """
        Format agent response for display.
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("_format_response() method needs to be moved from agent.py")
    
    def _handle_tool_calls(self, tool_calls: List[Any], messages: List[Dict], temperature: float) -> tuple:
        """
        Handle tool calls during chat completion.
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("_handle_tool_calls() method needs to be moved from agent.py")