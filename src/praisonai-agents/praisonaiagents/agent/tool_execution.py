"""
Tool execution functionality for Agent class.

This module contains methods related to tool execution, validation, and calling.
Split from the main agent.py file for better maintainability.
"""

import os
import time
import json
import logging
import asyncio
import concurrent.futures
from typing import Any, Dict, List, Optional, Union


class ToolExecutionMixin:
    """Mixin class containing tool execution methods for the Agent class."""
    
    def execute_tool(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None) -> Any:
        """
        Execute a tool dynamically based on the function name and arguments.
        Injects agent state for tools with Injected[T] parameters.
        
        Args:
            function_name: Name of the tool function to execute
            arguments: Dictionary of arguments to pass to the tool
            tool_call_id: Optional ID from the LLM's tool_call (e.g., 'call_xxxxx')
                         Used for correlating TOOL_CALL_START/RESULT stream events
        """
        logging.debug(f"{self.name} executing tool {function_name} with arguments: {arguments}")
        
        # NOTE: tool_call callback is triggered by display_tool_call in openai_client.py
        # Do NOT call it here to avoid duplicate output
        
        # Set up injection context for tools with Injected parameters
        from ..tools.injected import AgentState
        state = AgentState(
            agent_id=self.name,
            run_id=getattr(self, '_current_run_id', 'unknown'),
            session_id=getattr(self, '_session_id', None) or 'default',
            last_user_message=self.chat_history[-1].get('content') if self.chat_history else None,
            memory=getattr(self, '_memory_instance', None),
            learn_manager=getattr(getattr(self, '_memory_instance', None), 'learn', None),
            metadata={'agent_name': self.name}
        )
        
        # Execute within injection context
        return self._execute_tool_with_context(function_name, arguments, state, tool_call_id)
    
    def _execute_tool_with_context(self, function_name: str, arguments: Dict[str, Any], 
                                 state: Any, tool_call_id: Optional[str] = None) -> Any:
        """Execute tool within injection context, with optional output truncation.
        
        Args:
            function_name: Name of the tool function to execute
            arguments: Dictionary of arguments to pass to the tool
            state: AgentState for injection context
            tool_call_id: Optional ID from the LLM's tool_call (e.g., 'call_xxxxx')
        """
        from ..tools.injected import with_injection_context
        from ..trace.context_events import get_context_emitter
        from ..streaming.events import StreamEvent, StreamEventType
        import time as _time
        
        # Emit tool call start event (zero overhead when not set)
        _trace_emitter = get_context_emitter()
        _trace_emitter.tool_call_start(self.name, function_name, arguments)
        _tool_start_time = _time.time()
        _tool_start_perf = _time.perf_counter()
        
        # Emit TOOL_CALL_START to stream_emitter (for AIUI/AG-UI consumers)
        # Zero overhead when no callbacks registered
        if hasattr(self, '_Agent__stream_emitter') and self.__stream_emitter is not None and self.__stream_emitter.has_callbacks:
            self.__stream_emitter.emit(StreamEvent(
                type=StreamEventType.TOOL_CALL_START,
                timestamp=_tool_start_perf,
                tool_call={
                    "name": function_name,
                    "arguments": arguments,  # PARSED DICT, not JSON string
                    "id": tool_call_id,  # Now properly threaded through
                },
                agent_id=self.name,
            ))
        
        try:
            # Trigger BEFORE_TOOL hook
            from ..hooks import HookEvent, BeforeToolInput
            before_tool_input = BeforeToolInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.BEFORE_TOOL,
                timestamp=str(_time.time()),
                agent_name=self.name,
                tool_name=function_name,
                tool_input=arguments
            )
            tool_hook_results = self._hook_runner.execute_sync(HookEvent.BEFORE_TOOL, before_tool_input, target=function_name)
            if self._hook_runner.is_blocked(tool_hook_results):
                logging.warning(f"Tool {function_name} execution blocked by BEFORE_TOOL hook")
                return f"Execution of {function_name} was blocked by security policy."
            
            # Update arguments if modified by hooks
            for res in tool_hook_results:
                if res.output and res.output.modified_data:
                    arguments.update(res.output.modified_data)

            with with_injection_context(state):
                # P8/G11: Apply tool timeout if configured
                tool_timeout = getattr(self, '_tool_timeout', None)
                if tool_timeout and tool_timeout > 0:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(self._execute_tool_impl, function_name, arguments)
                        try:
                            result = future.result(timeout=tool_timeout)
                        except concurrent.futures.TimeoutError:
                            logging.warning(f"Tool {function_name} timed out after {tool_timeout}s")
                            result = {"error": f"Tool timed out after {tool_timeout}s", "timeout": True}
                else:
                    result = self._execute_tool_impl(function_name, arguments)
                
        except Exception as e:
            # Apply consistent error logging and formatting
            error_msg = f"Error executing tool {function_name}: {str(e)}"
            logging.error(error_msg)
            result = {"error": error_msg}
            
        # Trigger AFTER_TOOL hook and trace events
        try:
            from ..hooks import AfterToolInput
            after_tool_input = AfterToolInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.AFTER_TOOL,
                timestamp=str(_time.time()),
                agent_name=self.name,
                tool_name=function_name,
                tool_input=arguments,
                tool_output=result
            )
            self._hook_runner.execute_sync(HookEvent.AFTER_TOOL, after_tool_input, target=function_name)
        except Exception as hook_error:
            logging.warning(f"Error in AFTER_TOOL hook: {hook_error}")

        # Emit TOOL_CALL_RESULT to stream_emitter 
        if hasattr(self, '_Agent__stream_emitter') and self.__stream_emitter is not None and self.__stream_emitter.has_callbacks:
            self.__stream_emitter.emit(StreamEvent(
                type=StreamEventType.TOOL_CALL_RESULT,
                timestamp=_time.perf_counter(),
                tool_call={
                    "name": function_name,
                    "arguments": arguments,
                    "id": tool_call_id,
                    "result": result,
                },
                agent_id=self.name,
            ))
        
        # Emit trace event
        _trace_emitter.tool_call_end(self.name, function_name, result, _time.time() - _tool_start_time)
        
        return result

    def _execute_tool_impl(self, function_name: str, arguments: Dict[str, Any]) -> Any:
        """Core tool execution implementation."""
        # This method would contain the actual tool execution logic
        # For now, just return a placeholder to demonstrate the pattern
        raise NotImplementedError("Tool execution implementation moved from main Agent class")
    
    async def execute_tool_async(self, function_name: str, arguments: Dict[str, Any]) -> Any:
        """Async tool execution for non-blocking operations."""
        # Async version of execute_tool 
        raise NotImplementedError("Async tool execution implementation moved from main Agent class")