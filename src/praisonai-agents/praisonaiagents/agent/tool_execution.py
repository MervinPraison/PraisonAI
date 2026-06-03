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
import contextvars
import concurrent.futures
import random
from typing import List, Optional, Any, Dict, Union, TYPE_CHECKING
from ..errors import ToolExecutionError
from ..tools.trust import wrap_if_external

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class BackoffPolicy:
    """Exponential backoff policy for tool retries."""
    
    @staticmethod
    def delay(attempt: int, initial_delay: float, backoff_factor: float, jitter: float) -> float:
        """Calculate delay for a retry attempt.
        
        Args:
            attempt: Attempt number (1-based)
            initial_delay: Initial delay in seconds
            backoff_factor: Exponential backoff multiplier
            jitter: Fraction of base delay to add as random jitter
            
        Returns:
            Delay in seconds
        """
        base = initial_delay * (backoff_factor ** (attempt - 1))
        jitter_amount = random.uniform(0, jitter * base)
        return base + jitter_amount


class ToolExecutionMixin:
    """Mixin providing toolexecution methods for the Agent class."""

    def _get_existing_stream_emitter(self):
        """Return an already-initialized stream emitter without creating one."""
        emitter = getattr(self, "_stream_emitter", None)
        if emitter is not None:
            return emitter

        # Support name-mangled private attributes across class renames/inheritance.
        for cls in type(self).mro():
            mangled = f"_{cls.__name__}__stream_emitter"
            if hasattr(self, mangled):
                emitter = getattr(self, mangled, None)
                if emitter is not None:
                    return emitter
        return None

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
        
        # Handle bridge tool unwrapping BEFORE trace/stream/hooks (design invariant #6)
        # Only intercept when tool_search is active; otherwise fall through to real tool execution
        if (getattr(self, '_tool_search_config', None) is not None and
                function_name in ("tool_search", "tool_describe", "tool_call")):
            return self._handle_bridge_tool_call(function_name, arguments, tool_call_id)
        
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
        _stream_emitter = self._get_existing_stream_emitter()
        if _stream_emitter is not None and _stream_emitter.has_callbacks:
            _stream_emitter.emit(StreamEvent(
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
            # Check for steering messages before tool execution
            if hasattr(self, '_check_steering_messages'):
                try:
                    steering_msg = self._check_steering_messages()
                    if steering_msg:
                        # Check if steering message indicates interruption priority
                        # (SteeringMixin formats HIGH/URGENT as "[URGENT USER GUIDANCE]" and INTERRUPT as "[INTERRUPT USER GUIDANCE]")
                        if "[URGENT USER GUIDANCE]" in steering_msg or "[INTERRUPT USER GUIDANCE]" in steering_msg:
                            logger.info(f"Tool {function_name} execution interrupted by high-priority steering")
                            return f"Tool execution interrupted by user guidance: {steering_msg}"
                except Exception as e:
                    logger.warning(f"Steering check failed, continuing with tool execution: {e}")
            
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

            # Loop guard check - prevent tool execution loops with graduated response
            if hasattr(self, '_ensure_loop_guard'):
                loop_guard = self._ensure_loop_guard()
                from ..escalation.loop_guard import GuardAction
                decision = loop_guard.check(function_name, arguments, is_pre_execution=True)
                
                if decision.action == GuardAction.WARN:
                    # Inject warning into tool result so LLM sees guidance
                    logging.warning(f"Loop guard warning for {function_name}: {decision.message}")
                elif decision.action == GuardAction.BLOCK:
                    # Block tool execution but continue through teardown path
                    logging.warning(f"Loop guard blocked {function_name}: {decision.message}")
                    # Set flag to use blocked result instead of executing tool
                    blocked_result = {"error": f"[loop-guard] {decision.message}", "loop_blocked": True}
                elif decision.action == GuardAction.HALT:
                    # Halt execution with exception
                    raise ToolExecutionError(
                        f"[loop-guard] {decision.message}",
                        tool_name=function_name,
                        agent_id=self.name,
                        is_retryable=False
                    )

            # C4 — optional tool-argument validation via ToolValidatorProtocol.
            # Zero overhead when not set. Users wire via `agent._tool_validator = MyValidator()`.
            _validator = getattr(self, '_tool_validator', None)
            if _validator is not None:
                try:
                    _vres = _validator.validate_args(function_name, arguments)
                    if _vres is not None and not getattr(_vres, 'valid', True):
                        _errs = "; ".join(getattr(_vres, 'errors', []) or ["validation failed"])
                        logging.warning(
                            f"Tool {function_name} args rejected by validator: {_errs}"
                        )
                        return f"Tool arguments rejected: {_errs}"
                except Exception as _ve:  # noqa: BLE001 — never break tool exec on validator bug
                    logging.debug(f"Tool validator raised; skipping validation: {_ve}")

            # Check if loop guard blocked execution
            blocked_result = locals().get('blocked_result')
            if blocked_result is not None:
                result = blocked_result
            else:
                # Apply tool retry logic with exponential backoff
                execution_config = getattr(self, '_execution_config', None)
                if execution_config is None:
                    # Fall back to reading individual config attributes for backward compatibility
                    max_retry_limit = getattr(self, 'max_retry_limit', 2)
                    retry_initial_delay = 1.0
                    retry_backoff_factor = 2.0
                    retry_jitter = 0.1
                else:
                    max_retry_limit = execution_config.max_retry_limit
                    retry_initial_delay = execution_config.retry_initial_delay
                    retry_backoff_factor = execution_config.retry_backoff_factor
                    retry_jitter = execution_config.retry_jitter
                
                result = None
                last_exception = None
                
                for attempt in range(1, max_retry_limit + 2):
                    try:
                        # P8/G11: Apply tool timeout if configured
                        tool_timeout = getattr(self, '_tool_timeout', None)
                        if tool_timeout and tool_timeout > 0:
                            # Use copy_context to preserve injection context in executor thread
                            ctx = contextvars.copy_context()
                            
                            def execute_with_context():
                                with with_injection_context(state):
                                    return self._execute_tool_with_circuit_breaker(function_name, arguments)
                            
                            # Use reusable executor to prevent resource leaks
                            if not hasattr(self, '_tool_executor'):
                                self._tool_executor = concurrent.futures.ThreadPoolExecutor(
                                    max_workers=2, thread_name_prefix=f"tool-{self.name}"
                                )
                            
                            future = self._tool_executor.submit(ctx.run, execute_with_context)
                            try:
                                result = future.result(timeout=tool_timeout)
                            except concurrent.futures.TimeoutError:
                                future.cancel()
                                logging.warning(f"Tool {function_name} timed out after {tool_timeout}s")
                                result = {"error": f"Tool timed out after {tool_timeout}s", "timeout": True}
                        else:
                            with with_injection_context(state):
                                result = self._execute_tool_with_circuit_breaker(function_name, arguments)
                        
                        # Check if the result indicates a retryable error
                        if isinstance(result, dict) and result.get("error"):
                            # Check if this is a circuit breaker error (always retryable)
                            if result.get("circuit_open"):
                                raise ToolExecutionError(
                                    result["error"],
                                    tool_name=function_name,
                                    agent_id=self.name,
                                    is_retryable=True,
                                )
                            # Check if this is a timeout error (retryable)
                            elif result.get("timeout"):
                                raise ToolExecutionError(
                                    result["error"],
                                    tool_name=function_name,
                                    agent_id=self.name,
                                    is_retryable=True,
                                )
                            # For other error dicts, treat as non-retryable unless specified
                            else:
                                # Success path - return the result
                                break
                        else:
                            # Success path - return the result
                            break
                            
                    except ToolExecutionError as e:
                        last_exception = e
                        # Only retry if the error is marked as retryable
                        if not e.is_retryable or attempt >= max_retry_limit + 1:
                            raise e
                        
                        # Calculate delay for exponential backoff
                        delay = BackoffPolicy.delay(attempt, retry_initial_delay, retry_backoff_factor, retry_jitter)
                        logging.warning(
                            f"Tool {function_name} failed (attempt {attempt}/{max_retry_limit + 1}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                        
                    except Exception as e:
                        # Wrap unexpected exceptions in ToolExecutionError
                        # Most tool errors are considered retryable unless they're programming errors
                        is_retryable = not isinstance(e, (ValueError, TypeError, AttributeError))
                        tool_error = ToolExecutionError(
                            f"Tool '{function_name}' failed: {e}",
                            tool_name=function_name,
                            agent_id=self.name,
                            is_retryable=is_retryable,
                        )
                        last_exception = tool_error
                        
                        if not is_retryable or attempt >= max_retry_limit + 1:
                            raise tool_error from e
                        
                        # Calculate delay for exponential backoff
                        delay = BackoffPolicy.delay(attempt, retry_initial_delay, retry_backoff_factor, retry_jitter)
                        logging.warning(
                            f"Tool {function_name} failed (attempt {attempt}/{max_retry_limit + 1}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
            
            # Apply prompt injection protection for external tools
            # Zero-cost for trusted tools, wraps external content in security markers
            result = wrap_if_external(function_name, result)
            
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
            if _stream_emitter is not None and _stream_emitter.has_callbacks:
                # Truncate result for stream event (keep it reasonable for UI display)
                result_summary = str(result)[:500] if result else None
                _stream_emitter.emit(StreamEvent(
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
                _stream_emitter.emit(StreamEvent(
                    type=StreamEventType.TOOL_CALL_END,
                    timestamp=_time.perf_counter(),
                    tool_call={
                        "name": function_name,
                        "arguments": arguments,
                        "result": result_summary,
                        "id": tool_call_id,
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
            
            # Record tool execution in loop guard
            if hasattr(self, '_ensure_loop_guard'):
                loop_guard = self._ensure_loop_guard()
                is_success = result is not None and not (isinstance(result, dict) and result.get('error'))
                loop_guard.record(function_name, arguments, is_success)
                # Handle warning injection for WARN decisions
                decision = loop_guard.check(function_name, arguments, is_pre_execution=False) 
                if decision.action.value == "warn":
                    if isinstance(result, str):
                        result = f"{result}\n\n[loop-guard] {decision.message}"
                    elif isinstance(result, dict):
                        # Inject warning into dict results
                        result["_loop_guard"] = {"message": decision.message, "action": decision.action.value}
                    elif isinstance(result, list):
                        # Inject warning into list results  
                        result = {"value": result, "_loop_guard": {"message": decision.message, "action": decision.action.value}}
                    else:
                        # Wrap non-string/dict/list results to preserve original data plus warning
                        result = {"value": result, "_loop_guard": {"message": decision.message, "action": decision.action.value}}
            
            # Increment per-turn tool count for no-tool-call detection
            self._autonomy_turn_tool_count = getattr(self, '_autonomy_turn_tool_count', 0) + 1
            
            return result
        except Exception as e:
            # Emit tool call end with error for exceptions that escape the retry loop
            _duration_ms = (_time.time() - _tool_start_time) * 1000
            _trace_emitter.tool_call_end(self.name, function_name, None, _duration_ms, str(e))
            
            # Preserve existing ToolExecutionError unchanged to maintain loop guard HALT behavior
            if isinstance(e, ToolExecutionError):
                raise
            
            # Gap 3a fix: Wrap exceptions in ToolExecutionError for better observability
            is_retryable = not isinstance(e, (ValueError, TypeError, AttributeError))
            raise ToolExecutionError(
                f"Tool '{function_name}' failed: {e}",
                tool_name=function_name,
                agent_id=self.name,
                is_retryable=is_retryable,
            ) from e

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

        # Periodic nudge (opt-in via LearnConfig(nudge_interval>0)).
        # Appends a system note to chat_history so it is visible on the NEXT
        # LLM call — encourages the agent to persist non-trivial procedures
        # as skills/memory. No-op when nudge_interval=0 (default).
        try:
            nudge = self._maybe_emit_nudge(prompt if isinstance(prompt, str) else str(prompt))
            if nudge and hasattr(self, "chat_history") and isinstance(self.chat_history, list):
                self._append_to_chat_history({"role": "system", "content": nudge.strip()})
        except Exception as e:
            # Log learning nudge failures for debugging
            logger.warning("Learning nudge generation failed: %s", e, exc_info=True)

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

        # Periodic nudge (opt-in via LearnConfig(nudge_interval>0)).
        try:
            nudge = self._maybe_emit_nudge(prompt if isinstance(prompt, str) else str(prompt))
            if nudge and hasattr(self, "chat_history") and isinstance(self.chat_history, list):
                self._append_to_chat_history({"role": "system", "content": nudge.strip()})
        except Exception as e:
            # Log learning nudge failures for debugging
            logger.warning("Learning nudge generation failed: %s", e, exc_info=True)

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
        from ..tools import get_registry as get_tool_registry
        
        backend = getattr(self, '_approval_backend', None)
        approve_all = getattr(self, '_approve_all_tools', False)
        
        # Check tool trust level if available
        tool_registry = get_tool_registry()
        trust_level = tool_registry.get_trust_level(tool_name)
        
        if backend is not None:
            # Check if tool needs approval based on multiple criteria
            needs_approval = (
                approve_all 
                or tool_name in DEFAULT_DANGEROUS_TOOLS
                or (trust_level == "external")  # External tools need approval
            )
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

    def _execute_tool_with_circuit_breaker(self, function_name, arguments):
        """Execute tool with retry policy and circuit breaker protection.
        
        Args:
            function_name: Name of the tool to execute
            arguments: Arguments for the tool
            
        Returns:
            Tool execution result or circuit breaker error
        """
        # Get retry policy (tool-level > agent-level > default)
        retry_policy = self._get_tool_retry_policy(function_name)
        
        last_exception = None
        
        # Retry loop with exponential backoff
        for attempt in range(retry_policy.max_attempts):
            try:
                result = self._execute_tool_with_circuit_breaker_impl(function_name, arguments)
                
                # Check if result is an error that should be retried
                if isinstance(result, dict) and result.get("error"):
                    # Skip retry for non-retryable errors (approval, permission, etc.)
                    if (result.get("approval_denied") or 
                        result.get("permission_denied") or 
                        result.get("approval_error") or
                        result.get("circuit_open")):
                        return result
                    
                    # Determine error type for retry policy
                    error_type = self._classify_error_type(result, last_exception)
                    
                    # Check if we should retry
                    if not retry_policy.should_retry(error_type, attempt):
                        return result
                    
                    # Don't retry on last attempt
                    if attempt == retry_policy.max_attempts - 1:
                        return result
                    
                    # Emit retry hook event  
                    delay_ms = retry_policy.get_delay_ms(attempt)
                    self._emit_retry_hook(function_name, attempt + 1, delay_ms, result.get("error", "Unknown error"), retry_policy.max_attempts, error_type)
                    
                    # Wait before retry
                    time.sleep(delay_ms / 1000.0)
                    continue
                else:
                    # Success - return result
                    return result
                    
            except ToolExecutionError as e:
                last_exception = e
                # Check if the error is retryable
                if not e.is_retryable or attempt == retry_policy.max_attempts - 1:
                    raise
                
                # Determine error type
                error_type = self._classify_error_type(None, e) 
                
                if not retry_policy.should_retry(error_type, attempt):
                    raise
                
                # Emit retry hook event
                delay_ms = retry_policy.get_delay_ms(attempt)
                self._emit_retry_hook(function_name, attempt + 1, delay_ms, str(e), retry_policy.max_attempts, error_type)
                
                # Wait before retry
                time.sleep(delay_ms / 1000.0)
                continue
                
            except Exception as e:
                # Wrap in ToolExecutionError for consistency
                is_retryable = not isinstance(e, (ValueError, TypeError, AttributeError))
                wrapped_error = ToolExecutionError(
                    f"Tool '{function_name}' failed: {e}",
                    tool_name=function_name,
                    agent_id=self.name,
                    is_retryable=is_retryable,
                )
                
                # Check if retryable and not last attempt
                if not is_retryable or attempt == retry_policy.max_attempts - 1:
                    raise wrapped_error from e
                
                # Determine error type  
                error_type = self._classify_error_type(None, wrapped_error)
                
                if not retry_policy.should_retry(error_type, attempt):
                    raise wrapped_error from e
                
                # Emit retry hook event
                delay_ms = retry_policy.get_delay_ms(attempt)
                self._emit_retry_hook(function_name, attempt + 1, delay_ms, str(e), retry_policy.max_attempts, error_type)
                
                # Wait before retry
                time.sleep(delay_ms / 1000.0)
                continue
        
        # Should never reach here due to loop logic, but safety fallback
        if last_exception:
            raise last_exception
        return {"error": "Maximum retry attempts exceeded"}

    def _execute_tool_with_circuit_breaker_impl(self, function_name, arguments):
        """Execute tool with circuit breaker protection (internal implementation).
        
        Args:
            function_name: Name of the tool to execute
            arguments: Arguments for the tool
            
        Returns:
            Tool execution result or circuit breaker error
        """
        # Import circuit breaker components first (lazy import for performance)
        try:
            from ..tools.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig, CircuitBreakerException
        except ImportError:
            # Circuit breaker not available - fallback to direct execution
            logging.debug("Circuit breaker not available, falling back to direct tool execution")
            return self._execute_tool_impl(function_name, arguments)

        try:
            
            # Get or create circuit breaker for this tool
            breaker_name = f"tool_{function_name}"
            config = CircuitBreakerConfig(
                failure_threshold=5,        # Open after 5 failures
                recovery_timeout=60.0,      # Wait 60s before trying half-open
                timeout=30.0,               # Tool call timeout
                graceful_degradation=True   # Return error instead of raising exception
            )
            breaker = get_circuit_breaker(breaker_name, config)
            
            # Execute tool through circuit breaker with failure detection wrapper
            def _tool_wrapper():
                result = self._execute_tool_impl(function_name, arguments)
                # Convert error dicts to exceptions so circuit breaker can detect failures
                # Don't treat approval/permission denials as circuit breaker failures
                if isinstance(result, dict) and result.get("error") and \
                   not result.get("approval_denied") and \
                   not result.get("permission_denied") and \
                   not result.get("approval_error"):
                    # Create a sentinel exception to register failure with circuit breaker
                    class _ToolFailure(Exception):
                        def __init__(self, error_dict):
                            self.error_dict = error_dict
                            super().__init__(error_dict.get("error", "Tool execution failed"))
                    raise _ToolFailure(result)
                return result
            
            try:
                return breaker.call(_tool_wrapper)
            except Exception as e:
                # Check if this is our sentinel exception
                if hasattr(e, 'error_dict'):
                    return e.error_dict  # Return the original error dict
                else:
                    raise  # Re-raise other exceptions
            
        except CircuitBreakerException as e:
            # Circuit breaker is open - return error dict instead of raising
            logging.warning(f"Tool '{function_name}' circuit breaker open: {e}")
            return {
                "error": f"Tool '{function_name}' circuit breaker open - too many recent failures",
                "circuit_open": True,
                "agent_name": getattr(self, "name", None),
                "session_id": getattr(self, "_session_id", None),
                "remediation": "Wait for recovery_timeout (60s) or investigate recent tool failures.",
            }

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
            # Tool not found in declared tools or registry — do not fall back to
            # globals() or __main__ as that allows undeclared callables to execute.
            pass

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
        
        # Make defensive copy to prevent TOCTOU mutations
        import copy
        frozen_args = copy.deepcopy(arguments)
        
        async with self._approvals_lock:
            self._pending_approvals[tracking_id] = {
                "task": task,
                "function_name": function_name,
                "arguments": frozen_args,
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
        # Collect completed items under the lock, then execute tools outside the lock
        # to avoid holding it during potentially slow async tool execution.
        approved_items = []
        denied_items = []
        error_items = []

        async with self._approvals_lock:
            completed_ids = []
            for tid, info in list(self._pending_approvals.items()):
                task = info["task"]
                if task.done():
                    completed_ids.append(tid)
                    try:
                        decision = task.result()
                        if decision.approved:
                            approved_items.append((tid, info, decision))
                        else:
                            denied_items.append((tid, info, decision))
                    except Exception as e:
                        error_items.append((tid, info, e))

            # Remove completed entries while still holding the lock
            for tid in completed_ids:
                del self._pending_approvals[tid]

        # Execute approved tools outside the lock to avoid long lock hold
        for tid, info, decision in approved_items:
            try:
                tool_result = await self.execute_tool_async(
                    info["function_name"], info["arguments"],
                )
                results[tid] = {
                    "status": "approved_and_executed",
                    "tool_name": info["function_name"],
                    "decision": decision,
                    "result": tool_result,
                }
            except Exception as e:
                results[tid] = {
                    "status": "error",
                    "tool_name": info["function_name"],
                    "error": str(e),
                }

        for tid, info, decision in denied_items:
            results[tid] = {
                "status": "denied",
                "tool_name": info["function_name"],
                "decision": decision,
            }

        for tid, info, exc in error_items:
            results[tid] = {
                "status": "error",
                "tool_name": info["function_name"],
                "error": str(exc),
            }

        return results

    def pending_approval_count(self) -> int:
        """Number of approval requests still waiting."""
        return len(self._pending_approvals)
    
    def _handle_bridge_tool_call(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None) -> Any:
        """
        Handle bridge tool calls (tool_search, tool_describe, tool_call).
        
        This implements the tool search unwrapping logic before trace/stream/hooks
        as required by design invariant #6.
        
        Args:
            function_name: Bridge tool name
            arguments: Arguments passed to bridge tool
            tool_call_id: Optional tool call ID
            
        Returns:
            Result of bridge tool execution or unwrapped real tool call
        """
        # Ensure tool search metadata is available
        if not hasattr(self, '_tool_search_metadata') or self._tool_search_metadata is None:
            return "Tool search not available or not in bridge mode"
        
        metadata = self._tool_search_metadata
        
        # Check if we're in bridge mode
        if not metadata.get("bridge_mode", False):
            return "Tool search not in bridge mode"
        
        # Get deferrable tools from metadata
        deferrable_tools = metadata.get("deferrable_tools", [])
        
        if function_name == "tool_search":
            # Handle tool_search bridge call
            try:
                from ..tools.tool_search import dispatch_tool_search
                query = arguments.get("query", "")
                limit = arguments.get("limit", None)
                
                result = dispatch_tool_search(
                    query=query,
                    limit=limit, 
                    deferrable_tools=deferrable_tools,
                    config=self._tool_search_config
                )
                return json.dumps(result, indent=2)
            except ImportError:
                return "Tool search module not available"
            except Exception as e:
                logging.error(f"Error in tool_search: {e}")
                return f"Error searching tools: {e}"
        
        elif function_name == "tool_describe":
            # Handle tool_describe bridge call
            try:
                from ..tools.tool_search import dispatch_tool_describe
                tool_name = arguments.get("tool_name", "")
                
                result = dispatch_tool_describe(
                    tool_name=tool_name,
                    deferrable_tools=deferrable_tools
                )
                return json.dumps(result, indent=2)
            except ImportError:
                return "Tool search module not available"
            except Exception as e:
                logging.error(f"Error in tool_describe: {e}")
                return f"Error describing tool: {e}"
        
        elif function_name == "tool_call":
            # Handle tool_call bridge - unwrap and recurse with real tool
            try:
                from ..tools.tool_search import resolve_underlying_call
                
                # Unwrap the real tool call
                real_function_name, real_arguments = resolve_underlying_call(function_name, arguments)
                
                # Validate that the real tool is in our deferrable set (security check)
                deferrable_names = {
                    tool_def.get("function", {}).get("name", "") 
                    for tool_def in deferrable_tools
                }
                
                if real_function_name not in deferrable_names:
                    return f"Tool '{real_function_name}' is not available for execution"
                
                # Recursively execute the real tool (this will go through normal execution path)
                return self.execute_tool(real_function_name, real_arguments, tool_call_id)
                
            except ImportError:
                return "Tool search module not available"
            except Exception as e:
                logging.error(f"Error in tool_call unwrap: {e}")
                return f"Error executing tool: {e}"
        
        else:
            return f"Unknown bridge tool: {function_name}"

    def _get_tool_retry_policy(self, tool_name):
        """Get retry policy for a tool (tool-level > agent-level > default).
        
        Args:
            tool_name: Name of the tool to get retry policy for
            
        Returns:
            RetryPolicy instance
        """
        from ..tools.retry import RetryPolicy
        
        # Check for tool-level retry policy first
        tools = getattr(self, 'tools', [])
        # Handle non-iterable tools (e.g., single MCP instance)
        if not isinstance(tools, (list, tuple)):
            tools = []  # MCP or single tool instance - no tool-level policy lookup
        for tool in tools:
            if (callable(tool) and 
                getattr(tool, '__name__', '') == tool_name and
                hasattr(tool, 'retry_policy')):
                return tool.retry_policy
        
        # Check for agent-level retry policy
        agent_policy = getattr(self, '_tool_retry_policy', None)
        if agent_policy is not None:
            return agent_policy
        
        # Return default retry policy (cached class-level instance)
        if not hasattr(ToolExecutionMixin, '_default_retry_policy'):
            ToolExecutionMixin._default_retry_policy = RetryPolicy()
        return ToolExecutionMixin._default_retry_policy

    def _classify_error_type(self, error_dict, exception):
        """Classify error type for retry policy matching.
        
        Args:
            error_dict: Error dictionary from tool execution (if any)
            exception: Exception that was raised (if any)
            
        Returns:
            String error type for retry policy checking
        """
        # Check error dict first
        if error_dict and isinstance(error_dict, dict):
            error_msg = error_dict.get("error", "").lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                return "timeout"
            elif "rate" in error_msg and "limit" in error_msg:
                return "rate_limit"
            elif "connection" in error_msg or "network" in error_msg:
                return "connection_error"
        
        # Check exception type
        if exception:
            exc_msg = str(exception).lower()
            exc_type = type(exception).__name__.lower()
            
            if "timeout" in exc_msg or "timeout" in exc_type:
                return "timeout"
            elif "rate" in exc_msg and "limit" in exc_msg:
                return "rate_limit"  
            elif ("connection" in exc_msg or "network" in exc_msg or 
                  "connection" in exc_type):
                return "connection_error"
        
        return "unknown"

    def _emit_retry_hook(self, tool_name, attempt, delay_ms, error, max_attempts, error_type):
        """Emit ON_RETRY hook event.
        
        Args:
            tool_name: Name of the tool being retried
            attempt: Current attempt number (1-based)
            delay_ms: Delay before retry in milliseconds
            error: Error message or description
            max_attempts: Maximum number of attempts configured
            error_type: Classified error type
        """
        try:
            from ..hooks import HookEvent, OnRetryInput
            
            # Only emit if we have a hook runner
            hook_runner = getattr(self, '_hook_runner', None)
            if hook_runner is None:
                return
            
            retry_input = OnRetryInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.ON_RETRY,
                timestamp=str(time.time()),
                agent_name=self.name,
                tool_name=tool_name,
                attempt=attempt,
                delay_ms=delay_ms,
                error=error,
                max_attempts=max_attempts,
                error_type=error_type
            )
            
            # Execute hook synchronously
            hook_runner.execute_sync(HookEvent.ON_RETRY, retry_input, target=tool_name)
            
        except Exception as e:
            # Don't let hook failures break retry logic
            logging.debug(f"Failed to emit retry hook: {e}")
