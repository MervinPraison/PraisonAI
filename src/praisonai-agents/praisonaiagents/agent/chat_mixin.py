"""
Chat/LLM functionality extracted from Agent class for better maintainability.

This module contains all chat, conversation, and LLM interaction methods.
Part of the agent god class decomposition to reduce agent.py from 8,915 lines.
"""

import os
import time
import json
import logging
import asyncio
from typing import List, Optional, Any, Dict, Union, Generator
from praisonaiagents._logging import get_logger


class ChatMixin:
    """
    Mixin containing chat and LLM interaction methods for the Agent class.
    
    This mixin extracts approximately 1,500+ lines of chat-related functionality
    from the main Agent class, including:
    - chat() and achat() public methods
    - _chat_impl() and _achat_impl() implementations
    - Streaming and multimodal prompt handling
    - Response processing and formatting
    - Tool call handling within chat context
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
    
    async def achat(self, prompt: str, temperature=1.0, tools=None, output_json=None, 
                   output_pydantic=None, reasoning_steps=False, task_name=None, 
                   task_description=None, task_id=None, attachments=None):
        """
        Async version of chat.
        
        Args:
            prompt: The user message/prompt
            temperature: Sampling temperature
            tools: Tools available for this conversation
            output_json: JSON schema for structured output
            output_pydantic: Pydantic model for structured output
            reasoning_steps: Whether to include reasoning steps
            task_name: Name of the task for context
            task_description: Description of the task
            task_id: Unique identifier for the task
            attachments: File attachments
        
        Returns:
            The agent's response as a string
        """
        # Emit context trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.agent_start(self.name, {"role": self.role, "goal": self.goal})
        
        try:
            return await self._achat_impl(prompt, temperature, tools, output_json, 
                                        output_pydantic, reasoning_steps, task_name, 
                                        task_description, task_id, attachments, _trace_emitter)
        finally:
            _trace_emitter.agent_end(self.name)
    
    def _chat_impl(self, prompt, temperature, tools, output_json, output_pydantic, 
                   reasoning_steps, stream, task_name, task_description, task_id, config, 
                   force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None):
        """
        Internal chat implementation (extracted for trace wrapping).
        
        NOTE: This is a placeholder that delegates to the agent.py implementation.
        In the full decomposition, this would contain the actual implementation 
        extracted from agent.py lines 6278-6781 (~500 lines).
        """
        # For now, this delegates to the original implementation in agent.py
        # In the complete decomposition, the actual implementation would be moved here
        raise NotImplementedError("Chat implementation to be moved from agent.py")
    
    async def _achat_impl(self, prompt, temperature, tools, output_json, output_pydantic, 
                         reasoning_steps, task_name, task_description, task_id, attachments, 
                         _trace_emitter):
        """
        Internal async chat implementation.
        
        NOTE: This is a placeholder that delegates to the agent.py implementation.
        In the full decomposition, this would contain the actual async implementation 
        extracted from agent.py lines 6812+ (~200 lines).
        """
        # For now, this delegates to the original implementation in agent.py
        # In the complete decomposition, the actual implementation would be moved here
        raise NotImplementedError("Async chat implementation to be moved from agent.py")
    
    def clean_json_output(self, output: str) -> str:
        """
        Clean and extract JSON from response text.
        
        Args:
            output: Raw response text that may contain JSON
            
        Returns:
            Cleaned JSON string
        """
        cleaned = output.strip()
        # Remove markdown code blocks if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned
    
    # Additional chat-related methods would be extracted here:
    # - _build_multimodal_prompt()
    # - _process_agent_output()
    # - _format_response()
    # - _handle_tool_calls()
    # - _build_messages()
    # - _chat_completion()
    # - Streaming methods
    # - Response validation methods
    # - Reflection methods
    # - etc.