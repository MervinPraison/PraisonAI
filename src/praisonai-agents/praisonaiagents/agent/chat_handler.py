"""
Chat and conversation handling functionality for Agent class.

This module contains methods related to chat, streaming, and conversation management.
Split from the main agent.py file for better maintainability.
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional, Union, Generator


class ChatHandlerMixin:
    """Mixin class containing chat handling methods for the Agent class."""
    
    def chat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None, 
             output_json: Optional[str] = None, output_pydantic: Optional[Any] = None,
             reasoning_steps: bool = False, stream: Optional[bool] = None, 
             task_name: Optional[str] = None, task_description: Optional[str] = None,
             task_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None,
             force_retrieval: bool = False, skip_retrieval: bool = False,
             attachments: Optional[List[Any]] = None, tool_choice: Optional[str] = None) -> str:
        """
        Chat with the agent using a prompt.
        
        Args:
            prompt: The user message/prompt
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
            attachments: File attachments
            tool_choice: Tool selection strategy
            
        Returns:
            The agent's response as a string
        """
        return self._chat_impl(
            prompt=prompt,
            temperature=temperature, 
            tools=tools,
            output_json=output_json,
            output_pydantic=output_pydantic,
            reasoning_steps=reasoning_steps,
            stream=stream,
            task_name=task_name,
            task_description=task_description,
            task_id=task_id,
            config=config,
            force_retrieval=force_retrieval,
            skip_retrieval=skip_retrieval,
            attachments=attachments,
            _trace_emitter=None,
            tool_choice=tool_choice
        )
    
    def _chat_impl(self, prompt: str, temperature: float, tools: Optional[List[Any]], 
                  output_json: Optional[str], output_pydantic: Optional[Any],
                  reasoning_steps: bool, stream: Optional[bool], 
                  task_name: Optional[str], task_description: Optional[str],
                  task_id: Optional[str], config: Optional[Dict[str, Any]],
                  force_retrieval: bool, skip_retrieval: bool,
                  attachments: Optional[List[Any]], _trace_emitter: Optional[Any],
                  tool_choice: Optional[str] = None) -> str:
        """Internal chat implementation with full parameter control."""
        raise NotImplementedError("Chat implementation moved from main Agent class")

    async def achat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None,
                   output_json: Optional[str] = None, output_pydantic: Optional[Any] = None,
                   reasoning_steps: bool = False, task_name: Optional[str] = None,
                   task_description: Optional[str] = None, task_id: Optional[str] = None,
                   attachments: Optional[List[Any]] = None) -> str:
        """Async version of chat method."""
        return await self._achat_impl(
            prompt=prompt,
            temperature=temperature,
            tools=tools,
            output_json=output_json,
            output_pydantic=output_pydantic,
            reasoning_steps=reasoning_steps,
            task_name=task_name,
            task_description=task_description,
            task_id=task_id,
            attachments=attachments,
            _trace_emitter=None
        )
    
    async def _achat_impl(self, prompt: str, temperature: float, tools: Optional[List[Any]],
                         output_json: Optional[str], output_pydantic: Optional[Any],
                         reasoning_steps: bool, task_name: Optional[str],
                         task_description: Optional[str], task_id: Optional[str],
                         attachments: Optional[List[Any]], _trace_emitter: Optional[Any]) -> str:
        """Internal async chat implementation."""
        raise NotImplementedError("Async chat implementation moved from main Agent class")
    
    def iter_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Stream chat response as an iterator."""
        raise NotImplementedError("Stream iteration implementation moved from main Agent class")
    
    def _start_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Internal streaming implementation."""
        raise NotImplementedError("Stream implementation moved from main Agent class")
    
    def clear_history(self) -> None:
        """Clear the chat history."""
        if hasattr(self, 'chat_history'):
            self.chat_history.clear()
        logging.info(f"{self.name}: Chat history cleared")
    
    def prune_history(self, keep_last: int = 5) -> int:
        """
        Prune chat history to keep only the last N messages.
        
        Args:
            keep_last: Number of recent messages to keep
            
        Returns:
            Number of messages removed
        """
        if not hasattr(self, 'chat_history'):
            return 0
            
        original_length = len(self.chat_history)
        if original_length <= keep_last:
            return 0
            
        self.chat_history = self.chat_history[-keep_last:]
        removed_count = original_length - len(self.chat_history)
        logging.info(f"{self.name}: Pruned {removed_count} messages from history")
        return removed_count
    
    def get_history_size(self) -> int:
        """Get the current chat history size."""
        if hasattr(self, 'chat_history'):
            return len(self.chat_history)
        return 0