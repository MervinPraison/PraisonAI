"""
Tool execution mixin for the Agent class.

Contains all methods for tool resolution, execution, approval,
cost tracking, and hook integration. Extracted from agent.py
for maintainability.
"""

import os
import time
import json
import logging
import asyncio
import inspect
import concurrent.futures
from typing import List, Optional, Any, Dict, Union, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ToolExecutionMixin:
    """Mixin providing toolexecution methods for the Agent class."""

    def _resolve_tool_names(self, tool_names):
        """Resolve tool names to actual tool instances from registry.
        
        Args:
            tool_names: List of tool name strings
            
        Returns:
            List of resolved tool instances
        """
        resolved = []
        try:
            from ..tools.registry import get_registry
            registry = get_registry()
            
            for name in tool_names:
                tool = registry.get(name)
                if tool is not None:
                    resolved.append(tool)
                else:
                    logging.warning(f"Tool '{name}' not found in registry")
        except ImportError:
            logging.warning("Tool registry not available, cannot resolve tool names")
        
        return resolved

    def _cast_arguments(self, func, arguments):
        """Cast arguments to their expected types based on function signature."""
        if not callable(func) or not arguments:
            return arguments
        
        try:
            sig = inspect.signature(func)
            valid_params = set(sig.parameters.keys()) - {'self'}
            casted_args = {}
            
            # Sanitize argument names: strip trailing '=', whitespace, and
            # other invalid chars that LLMs sometimes hallucinate in kwarg names
            sanitized = {}
            for raw_name, arg_value in arguments.items():
                clean = raw_name.strip().rstrip('=').strip()
                # If the cleaned name matches a valid param, use it;
                # otherwise try case-insensitive match
                if clean in valid_params:
                    sanitized[clean] = arg_value
                elif clean.lower() in {p.lower() for p in valid_params}:
                    # Case-insensitive fuzzy match
                    matched = next(p for p in valid_params if p.lower() == clean.lower())
                    sanitized[matched] = arg_value
                else:
                    sanitized[clean] = arg_value
            arguments = sanitized
            
            for param_name, arg_value in arguments.items():
                if param_name in sig.parameters:
                    param = sig.parameters[param_name]
                    if param.annotation != inspect.Parameter.empty:
                        # Handle common type conversions
                        if param.annotation == int and isinstance(arg_value, (str, float)):
                            try:
                                casted_args[param_name] = int(float(arg_value))
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        elif param.annotation == float and isinstance(arg_value, (str, int)):
                            try:
                                casted_args[param_name] = float(arg_value)
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        elif param.annotation == bool and isinstance(arg_value, str):
                            casted_args[param_name] = arg_value.lower() in ('true', '1', 'yes', 'on')
                        else:
                            casted_args[param_name] = arg_value
                    else:
                        casted_args[param_name] = arg_value
                else:
                    casted_args[param_name] = arg_value
            
            return casted_args
        except Exception as e:
            logging.debug(f"Type casting failed for {getattr(func, '__name__', 'unknown function')}: {e}")
            return arguments

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

    def _execute_tool_with_context(self, function_name, arguments, state, tool_call_id=None):
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
        if hasattr(self, '_Agent__stream_emitter') and getattr(self, "_Agent__stream_emitter", None) is not None and getattr(self, "_Agent__stream_emitter", None).has_callbacks:
            getattr(self, "_Agent__stream_emitter", None).emit(StreamEvent(
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
            
            # Apply tool output truncation to prevent context overflow
            # Uses context manager budget if enabled, otherwise applies default limit
            if result:
                try:
                    result_str = str(result)
                    
                    if self.context_manager:
                        # Use context-aware truncation with configured budget
                        truncated = self._truncate_tool_output(function_name, result_str)
                    else:
                        # Apply default limit even without context management
                        # This prevents runaway tool outputs from causing overflow
                        limit = getattr(self, 'tool_output_limit', 16000)
                        if len(result_str) > limit:
                            # Use smart truncation format that judge recognizes as OK
                            tail_size = min(limit // 5, 2000)
                            head = result_str[:limit - tail_size]
                            tail = result_str[-tail_size:] if tail_size > 0 else ""
                            truncated = f"{head}\n...[{len(result_str):,} chars, showing first/last portions]...\n{tail}"
                        else:
                            truncated = result_str
                    
                    if len(truncated) < len(result_str):
                        logging.debug(f"Truncated {function_name} output from {len(result_str)} to {len(truncated)} chars")
                        # For dicts, truncate large string fields (e.g., raw_content from search)
                        if isinstance(result, dict):
                            max_field_chars = getattr(self, 'tool_output_limit', 16000) if not self.context_manager else None
                            result = self._truncate_dict_fields(result, function_name, max_field_chars)
                        else:
                            result = truncated
                except Exception as e:
                    logging.debug(f"Tool truncation skipped: {e}")
            
            # Emit tool call end event (truncation handled by context_events.py)
            _duration_ms = (_time.time() - _tool_start_time) * 1000
            _trace_emitter.tool_call_end(self.name, function_name, str(result) if result else None, _duration_ms)
            
            # Emit TOOL_CALL_RESULT to stream_emitter (for AIUI/AG-UI consumers)
            # Zero overhead when no callbacks registered
            if hasattr(self, '_Agent__stream_emitter') and getattr(self, "_Agent__stream_emitter", None) is not None and getattr(self, "_Agent__stream_emitter", None).has_callbacks:
                # Truncate result for stream event (keep it reasonable for UI display)
                result_summary = str(result)[:500] if result else None
                getattr(self, "_Agent__stream_emitter", None).emit(StreamEvent(
                    type=StreamEventType.TOOL_CALL_RESULT,
                    timestamp=_time.perf_counter(),
                    tool_call={
                        "name": function_name,
                        "arguments": arguments,
                        "result": result_summary,
                        "id": tool_call_id,  # Now properly threaded through
                    },
                    agent_id=self.name,
                    metadata={"duration_ms": _duration_ms},
                ))
            
            # Trigger AFTER_TOOL hook
            from ..hooks import HookEvent, AfterToolInput
            after_tool_input = AfterToolInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.AFTER_TOOL,
                timestamp=str(_time.time()),
                agent_name=self.name,
                tool_name=function_name,
                tool_input=arguments,
                tool_output=result,
                execution_time_ms=(_time.time() - _tool_start_time) * 1000
            )
            self._hook_runner.execute_sync(HookEvent.AFTER_TOOL, after_tool_input, target=function_name)
            
            # G10 fix: Mark progress after successful tool execution
            # This prevents false doom loop detection when tools succeed
            if self._doom_loop_tracker is not None and result is not None:
                is_error = isinstance(result, dict) and result.get('error')
                if not is_error:
                    self._doom_loop_tracker.mark_progress(f"tool:{function_name}")
            
            # Increment per-turn tool count for no-tool-call detection
            self._autonomy_turn_tool_count = getattr(self, '_autonomy_turn_tool_count', 0) + 1
            
            return result
        except Exception as e:
            # Emit tool call end with error
            _duration_ms = (_time.time() - _tool_start_time) * 1000
            _trace_emitter.tool_call_end(self.name, function_name, None, _duration_ms, str(e))
            
            # Trigger OnError hook if needed (optional future step)
            raise

    def _trigger_after_agent_hook(self, prompt, response, start_time, tools_used=None):
        """Trigger AFTER_AGENT hook and return response."""
        from ..hooks import HookEvent, AfterAgentInput
        after_agent_input = AfterAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.AFTER_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            response=response or "",
            tools_used=tools_used or [],
            total_tokens=0,
            execution_time_ms=(time.time() - start_time) * 1000
        )
        self._hook_runner.execute_sync(HookEvent.AFTER_AGENT, after_agent_input)
        
        # Auto-memory extraction (opt-in via MemoryConfig(auto_memory=True))
        if response:
            prompt_str = prompt if isinstance(prompt, str) else str(prompt)
            self._process_auto_memory(prompt_str, str(response))
        
        # Auto-learning extraction (opt-in via LearnConfig(mode=LearnMode.AGENTIC))
        self._process_auto_learning()
        
        return response

    async def _atrigger_after_agent_hook(self, prompt, response, start_time, tools_used=None):
        """Async version: Trigger AFTER_AGENT hook and return response."""
        from ..hooks import HookEvent, AfterAgentInput
        after_agent_input = AfterAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.AFTER_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            response=response or "",
            tools_used=tools_used or [],
            total_tokens=0,
            execution_time_ms=(time.time() - start_time) * 1000
        )
        await self._hook_runner.execute(HookEvent.AFTER_AGENT, after_agent_input)
        
        # Auto-memory extraction (opt-in via MemoryConfig(auto_memory=True))
        if response:
            prompt_str = prompt if isinstance(prompt, str) else str(prompt)
            self._process_auto_memory(prompt_str, str(response))
        
        # Auto-learning extraction (opt-in via LearnConfig(mode=LearnMode.AGENTIC))
        self._process_auto_learning()
        
        return response

    def _calculate_llm_cost(self, prompt_tokens: int, completion_tokens: int, response: any = None) -> float:
        """Calculate estimated cost for LLM call.
        
        Uses litellm for accurate pricing (1000+ models) when available,
        falls back to built-in pricing table otherwise.
        
        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion
            response: Optional LLM response object for more accurate cost calculation
            
        Returns:
            Estimated cost in USD
        """
        from praisonaiagents.utils.cost_utils import calculate_llm_cost
        return calculate_llm_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=self.llm,
            response=response,
        )

    def _truncate_dict_fields(self, data: dict, tool_name: str, max_field_chars: int = None) -> dict:
        """Truncate large string fields in a dict to prevent context overflow."""
        if max_field_chars is None:
            # Use tool budget from context manager (default 5000 tokens * 4 chars/token = 20000 chars)
            max_tokens = self.context_manager.get_tool_budget(tool_name) if self.context_manager else 5000
            max_field_chars = max_tokens * 4
        
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and len(value) > max_field_chars:
                # Smart truncate large string fields preserving head and tail
                head_limit = int(max_field_chars * 0.8)
                tail_limit = int(max_field_chars * 0.15)
                head = value[:head_limit]
                tail = value[-tail_limit:] if tail_limit > 0 else ""
                result[key] = f"{head}\n...[{len(value):,} chars, showing first/last portions]...\n{tail}"
                logging.debug(f"Smart truncated field '{key}' from {len(value)} to ~{max_field_chars} chars")
            elif isinstance(value, dict):
                result[key] = self._truncate_dict_fields(value, tool_name, max_field_chars)
            elif isinstance(value, list):
                result[key] = [
                    self._truncate_dict_fields(item, tool_name, max_field_chars) if isinstance(item, dict)
                    else (self._smart_truncate_str(item, max_field_chars) if isinstance(item, str) and len(item) > max_field_chars else item)
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _smart_truncate_str(self, text: str, max_chars: int) -> str:
        """Smart truncate a string preserving head and tail."""
        if len(text) <= max_chars:
            return text
        head_limit = int(max_chars * 0.8)
        tail_limit = int(max_chars * 0.15)
        head = text[:head_limit]
        tail = text[-tail_limit:] if tail_limit > 0 else ""
        return f"{head}\n...[{len(text):,} chars, showing first/last portions]...\n{tail}"

    def _resolve_approval_decision(self, tool_name: str, tool_args: dict, is_async: bool = False):
        """Shared approval logic for both sync and async paths.
        
        Args:
            tool_name: Name of the tool to check approval for
            tool_args: Arguments to pass to the tool
            is_async: Whether this is called from async context
            
        Returns:
            ApprovalDecision or coroutine: The approval decision (sync) or coroutine (async)
        """
        from ..approval import get_approval_registry
        from ..approval.protocols import ApprovalRequest, ApprovalDecision
        from ..approval.registry import DEFAULT_DANGEROUS_TOOLS
        
        backend = getattr(self, '_approval_backend', None)
        approve_all = getattr(self, '_approve_all_tools', False)
        
        if backend is not None:
            needs_approval = approve_all or tool_name in DEFAULT_DANGEROUS_TOOLS
            if needs_approval:
                request = ApprovalRequest(
                    tool_name=tool_name,
                    arguments=tool_args,
                    risk_level=DEFAULT_DANGEROUS_TOOLS.get(tool_name, "medium"),
                    agent_name=getattr(self, 'name', None),
                )
                
                if is_async:
                    # Async path - return the coroutine for caller to await
                    cfg_timeout = getattr(self, '_approval_timeout', 0)
                    if cfg_timeout is None:
                        return backend.request_approval(request)
                    elif cfg_timeout > 0:
                        import asyncio
                        return asyncio.wait_for(
                            backend.request_approval(request),
                            timeout=cfg_timeout,
                        )
                    else:
                        return backend.request_approval(request)
                else:
                    # Sync path - handle timeout and sync/async backend compatibility
                    cfg_timeout = getattr(self, '_approval_timeout', 0)
                    orig_timeout = None
                    if cfg_timeout is None:
                        orig_timeout = getattr(backend, '_timeout', None)
                        if orig_timeout is not None:
                            backend._timeout = 86400 * 365
                    elif cfg_timeout > 0:
                        orig_timeout = getattr(backend, '_timeout', None)
                        if orig_timeout is not None:
                            backend._timeout = cfg_timeout
                    
                    try:
                        if hasattr(backend, 'request_approval_sync'):
                            return backend.request_approval_sync(request)
                        else:
                            # Use the shared utility to avoid code duplication and handle timeout correctly
                            from ..approval.utils import run_coroutine_safely
                            
                            # Compute effective timeout from agent configuration
                            if cfg_timeout is None:
                                effective_timeout = None  # indefinite wait
                            elif cfg_timeout > 0:
                                effective_timeout = cfg_timeout
                            else:
                                # cfg_timeout == 0: use backend default or fallback
                                effective_timeout = getattr(backend, '_timeout', 60)
                            
                            return run_coroutine_safely(
                                backend.request_approval(request),
                                timeout=effective_timeout
                            )
                    finally:
                        if orig_timeout is not None and hasattr(backend, '_timeout'):
                            backend._timeout = orig_timeout
            else:
                if is_async:
                    # For async, wrap the decision in a coroutine
                    async def _async_approval():
                        return ApprovalDecision(approved=True, reason="Not a dangerous tool")
                    return _async_approval()
                else:
                    return ApprovalDecision(approved=True, reason="Not a dangerous tool")
        else:
            if is_async:
                return get_approval_registry().approve_async(
                    getattr(self, 'name', None), tool_name, tool_args,
                )
            else:
                return get_approval_registry().approve_sync(
                    getattr(self, 'name', None), tool_name, tool_args,
                )

    def _check_tool_approval_sync(self, function_name, arguments):
        """Check tool approval synchronously. Returns (decision, arguments) or error dict."""
        # Permission tier fast-path (O(1) frozenset lookup, resolved at __init__)
        if self._perm_deny and function_name in self._perm_deny:
            return {"error": f"Tool '{function_name}' blocked by permission policy", "permission_denied": True}
        if self._perm_allow is not None and function_name not in self._perm_allow:
            return {"error": f"Tool '{function_name}' not in allowed tools list", "permission_denied": True}

        decision = self._resolve_approval_decision(function_name, arguments, is_async=False)
        
        if not decision.approved:
            error_msg = f"Tool execution denied: {decision.reason}"
            logging.warning(error_msg)
            return {"error": error_msg, "approval_denied": True}
        
        from ..approval import get_approval_registry
        get_approval_registry().mark_approved(function_name)
        
        if decision.modified_args:
            arguments = decision.modified_args
            logging.info(f"Using modified arguments: {arguments}")
        return None, arguments

    async def _check_tool_approval_async(self, function_name, arguments):
        """Check tool approval asynchronously. Returns (decision, arguments) or error dict."""
        # Permission tier fast-path (O(1) frozenset lookup, resolved at __init__)
        if self._perm_deny and function_name in self._perm_deny:
            return {"error": f"Tool '{function_name}' blocked by permission policy", "permission_denied": True}
        if self._perm_allow is not None and function_name not in self._perm_allow:
            return {"error": f"Tool '{function_name}' not in allowed tools list", "permission_denied": True}

        decision_coro = self._resolve_approval_decision(function_name, arguments, is_async=True)
        decision = await decision_coro
        
        if not decision.approved:
            error_msg = f"Tool execution denied: {decision.reason}"
            logging.warning(error_msg)
            return {"error": error_msg, "approval_denied": True}
        
        from ..approval import get_approval_registry
        get_approval_registry().mark_approved(function_name)
        
        if decision.modified_args:
            arguments = decision.modified_args
            logging.info(f"Using modified arguments: {arguments}")
        return None, arguments

    def _execute_tool_impl(self, function_name, arguments):
        """Internal tool execution implementation."""

        # Check if approval is required for this tool (protocol-driven)
        try:
            result = self._check_tool_approval_sync(function_name, arguments)
            if isinstance(result, dict):
                return result  # Error dict
            _, arguments = result
        except Exception as e:
            error_msg = f"Error during approval process: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg, "approval_error": True}

        # Special handling for MCP tools
        # Check if tools is an MCP instance with the requested function name
        MCP = None
        try:
            from ..mcp.mcp import MCP
        except ImportError:
            pass  # MCP not available
        
        # Helper function to execute MCP tool
        def _execute_mcp_tool(mcp_instance, func_name, args):
            """Execute a tool from an MCP instance."""
            # Handle SSE MCP client
            if hasattr(mcp_instance, 'is_sse') and mcp_instance.is_sse:
                if hasattr(mcp_instance, 'sse_client'):
                    for tool in mcp_instance.sse_client.tools:
                        if tool.name == func_name:
                            logging.debug(f"Found matching SSE MCP tool: {func_name}")
                            return True, tool(**args)
            # Handle HTTP Stream MCP client
            if hasattr(mcp_instance, 'is_http_stream') and mcp_instance.is_http_stream:
                if hasattr(mcp_instance, 'http_stream_client'):
                    for tool in mcp_instance.http_stream_client.tools:
                        if tool.name == func_name:
                            logging.debug(f"Found matching HTTP Stream MCP tool: {func_name}")
                            return True, tool(**args)
            # Handle WebSocket MCP client
            if hasattr(mcp_instance, 'is_websocket') and mcp_instance.is_websocket:
                if hasattr(mcp_instance, 'websocket_client'):
                    for tool in mcp_instance.websocket_client.tools:
                        if tool.name == func_name:
                            logging.debug(f"Found matching WebSocket MCP tool: {func_name}")
                            return True, tool(**args)
            # Handle stdio MCP client
            if hasattr(mcp_instance, 'runner'):
                for mcp_tool in mcp_instance.runner.tools:
                    if hasattr(mcp_tool, 'name') and mcp_tool.name == func_name:
                        logging.debug(f"Found matching MCP tool: {func_name}")
                        return True, mcp_instance.runner.call_tool(func_name, args)
            return False, None
        
        # Check if tools is a single MCP instance
        if MCP is not None and isinstance(self.tools, MCP):
            logging.debug(f"Looking for MCP tool {function_name}")
            found, result = _execute_mcp_tool(self.tools, function_name, arguments)
            if found:
                return result
        
        # Check if tools is a list that may contain MCP instances
        if isinstance(self.tools, (list, tuple)):
            for tool in self.tools:
                if MCP is not None and isinstance(tool, MCP):
                    logging.debug(f"Looking for MCP tool {function_name} in MCP instance")
                    found, result = _execute_mcp_tool(tool, function_name, arguments)
                    if found:
                        return result

        # Try to find the function in the agent's tools list first
        func = None
        for tool in self.tools if isinstance(self.tools, (list, tuple)) else []:
            # Check for BaseTool instances (plugin system)
            from ..tools.base import BaseTool
            if isinstance(tool, BaseTool) and tool.name == function_name:
                func = tool
                break
            # Check for FunctionTool (decorated functions)
            if hasattr(tool, 'name') and getattr(tool, 'name', None) == function_name:
                func = tool
                break
            if (callable(tool) and getattr(tool, '__name__', '') == function_name) or \
               (inspect.isclass(tool) and tool.__name__ == function_name):
                func = tool
                break
        
        if func is None:
            # Check the global tool registry for plugins
            try:
                from ..tools.registry import get_registry
                registry = get_registry()
                func = registry.get(function_name)
            except ImportError:
                pass
        
        if func is None:
            # If not found in tools or registry, try globals and main
            func = globals().get(function_name)
            if not func:
                import __main__
                func = getattr(__main__, function_name, None)

        if func:
            try:
                # BaseTool instances (plugin system) - call run() method
                from ..tools.base import BaseTool
                if isinstance(func, BaseTool):
                    casted_arguments = self._cast_arguments(func.run, arguments)
                    return func.run(**casted_arguments)
                
                # Langchain: If it's a class with run but not _run, instantiate and call run
                if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
                    instance = func()
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance.run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance.run, run_params)
                    return instance.run(**casted_params)

                # CrewAI: If it's a class with an _run method, instantiate and call _run
                elif inspect.isclass(func) and hasattr(func, '_run'):
                    instance = func()
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance._run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance._run, run_params)
                    return instance._run(**casted_params)

                # Otherwise treat as regular function
                elif callable(func):
                    casted_arguments = self._cast_arguments(func, arguments)
                    return func(**casted_arguments)
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Error executing tool {function_name}: {error_msg}")
                return {"error": error_msg}
        
        error_msg = f"Tool '{function_name}' is not callable"
        logging.error(error_msg)
        return {"error": error_msg}

    async def submit_for_approval(self, function_name: str, arguments: Dict[str, Any]) -> str:
        """Fire an approval request in the background without blocking.

        Returns a tracking ID.  The agent can continue other work while the
        approval is pending.  Call :meth:`check_pending_approvals` to poll
        for results and auto-execute approved tools.
        """
        import uuid
        backend = getattr(self, '_approval_backend', None)
        if backend is None:
            raise RuntimeError("No approval backend configured on this agent")

        from ..approval.protocols import ApprovalRequest
        from ..approval.registry import DEFAULT_DANGEROUS_TOOLS

        request = ApprovalRequest(
            tool_name=function_name,
            arguments=arguments,
            risk_level=DEFAULT_DANGEROUS_TOOLS.get(function_name, "medium"),
            agent_name=getattr(self, 'name', None),
        )

        tracking_id = str(uuid.uuid4())[:8]
        task = asyncio.ensure_future(backend.request_approval(request))
        self._pending_approvals[tracking_id] = {
            "task": task,
            "function_name": function_name,
            "arguments": arguments,
            "request": request,
        }
        logging.info(f"Approval request submitted: {tracking_id} for {function_name}")
        return tracking_id

    async def check_pending_approvals(self) -> Dict[str, Any]:
        """Check and process any completed approval requests.

        Returns a dict of ``{tracking_id: result}`` for approvals that
        completed since the last check.  Approved tools are auto-executed
        and their results included.
        """
        results = {}
        completed_ids = []

        for tid, info in self._pending_approvals.items():
            task = info["task"]
            if task.done():
                completed_ids.append(tid)
                try:
                    decision = task.result()
                    if decision.approved:
                        # Auto-execute the approved tool
                        tool_result = await self.execute_tool_async(
                            info["function_name"], info["arguments"],
                        )
                        results[tid] = {
                            "status": "approved_and_executed",
                            "tool_name": info["function_name"],
                            "decision": decision,
                            "result": tool_result,
                        }
                    else:
                        results[tid] = {
                            "status": "denied",
                            "tool_name": info["function_name"],
                            "decision": decision,
                        }
                except Exception as e:
                    results[tid] = {
                        "status": "error",
                        "tool_name": info["function_name"],
                        "error": str(e),
                    }

        for tid in completed_ids:
            del self._pending_approvals[tid]

        return results

    def pending_approval_count(self) -> int:
        """Number of approval requests still waiting."""
        return len(self._pending_approvals)

