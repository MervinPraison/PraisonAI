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
import threading
import random
from typing import List, Optional, Any, Dict, Union, TYPE_CHECKING
from ..errors import ToolExecutionError
from ..config.feature_configs import DEFAULT_TOOL_OUTPUT_LIMIT

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class BackoffPolicy:
    """Exponential backoff policy for tool retries."""
    
    @staticmethod
    def delay(attempt: int, initial_delay: float, backoff_factor: float, jitter: float, max_delay: float = 60.0) -> float:
        """Calculate delay for a retry attempt.
        
        Args:
            attempt: Attempt number (1-based)
            initial_delay: Initial delay in seconds
            backoff_factor: Exponential backoff multiplier
            jitter: Fraction of base delay to add as random jitter
            max_delay: Maximum delay to cap exponential growth
            
        Returns:
            Delay in seconds
        """
        base = initial_delay * (backoff_factor ** (attempt - 1))
        # Cap the base delay to prevent excessively long waits
        base = min(base, max_delay)
        jitter_amount = random.uniform(0, jitter * base)
        return base + jitter_amount


# Cap on encoded image bytes injected back into the conversation to avoid
# blowing up the context window. ~5MB of base64 (~3.75MB raw) by default.
MULTIMODAL_IMAGE_BYTE_LIMIT = 5_000_000


def _content_part_to_data_uri(part: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a structured content part into an OpenAI-style message part.

    Returns a ``{"type": "image_url", "image_url": {...}}`` part for images, a
    ``{"type": "text", ...}`` part for text, or ``None`` if it cannot be
    represented as a model-visible part (callers should fall back to text).
    """
    import base64

    if not isinstance(part, dict):
        return None

    ptype = part.get("type")

    if ptype == "text":
        text = part.get("text")
        if text is None:
            return None
        return {"type": "text", "text": str(text)}

    if ptype in ("image", "image_url"):
        # Already-formed OpenAI image_url part
        if ptype == "image_url" and isinstance(part.get("image_url"), dict):
            return {"type": "image_url", "image_url": part["image_url"]}

        url = part.get("url")
        if url:
            return {"type": "image_url", "image_url": {"url": url}}

        data = part.get("data")
        if data is None:
            return None

        mime = part.get("mime") or "image/png"
        if isinstance(data, (bytes, bytearray)):
            if len(data) > MULTIMODAL_IMAGE_BYTE_LIMIT:
                logging.warning(
                    "Multimodal image part (%d bytes) exceeds limit %d; skipping",
                    len(data), MULTIMODAL_IMAGE_BYTE_LIMIT,
                )
                return None
            encoded = base64.b64encode(bytes(data)).decode("utf-8")
        else:
            # Assume already base64-encoded string (strip any data URI prefix)
            encoded = str(data)
            if encoded.startswith("data:"):
                return {"type": "image_url", "image_url": {"url": encoded}}
            if len(encoded) > MULTIMODAL_IMAGE_BYTE_LIMIT * 2:
                logging.warning(
                    "Multimodal image part (encoded %d chars) exceeds limit; skipping",
                    len(encoded),
                )
                return None
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}"},
        }

    # Files / other media are referenced as text (most providers cannot ingest
    # arbitrary binaries inline). Surface name/mime so the model is aware.
    if ptype == "file":
        name = part.get("name") or "file"
        mime = part.get("mime") or "application/octet-stream"
        return {"type": "text", "text": f"[file: {name} ({mime})]"}

    return None


def _normalize_multimodal_result(result: Any) -> Optional[List[Dict[str, Any]]]:
    """Detect a multimodal tool result and return its content parts.

    Recognises:
    - ``ToolResult`` with ``content`` parts
    - a bare list of content-part dicts (``[{"type": "image"|"text"|...}]``)
    - a single content-part dict
    - MCP-style content blocks (``{"type": "image", "data": ..., "mimeType": ...}``)

    Returns ``None`` for plain text/JSON results so the existing path is used.
    """
    # ToolResult carrying structured content
    content = getattr(result, "content", None)
    if content and isinstance(content, list):
        return _coerce_parts(content)

    if isinstance(result, dict):
        parts = _coerce_parts([result])
        if parts and any(p.get("type") in ("image", "file") for p in parts):
            return parts
        return None

    if isinstance(result, list) and result:
        if all(isinstance(p, dict) and p.get("type") for p in result):
            parts = _coerce_parts(result)
            if parts and any(p.get("type") in ("image", "file") for p in parts):
                return parts
    return None


def _coerce_parts(raw_parts: List[Any]) -> List[Dict[str, Any]]:
    """Normalize assorted part shapes (incl. MCP) into the canonical schema."""
    parts: List[Dict[str, Any]] = []
    for p in raw_parts:
        if not isinstance(p, dict):
            continue
        ptype = p.get("type")
        if ptype == "text":
            parts.append({"type": "text", "text": p.get("text", "")})
        elif ptype in ("image", "image_url"):
            norm = dict(p)
            norm["type"] = "image" if ptype == "image" else "image_url"
            # MCP uses 'mimeType'; normalize to 'mime'
            if "mimeType" in norm and "mime" not in norm:
                norm["mime"] = norm.pop("mimeType")
            parts.append(norm)
        elif ptype in ("file", "blob", "resource"):
            norm = dict(p)
            norm["type"] = "file"
            if "mimeType" in norm and "mime" not in norm:
                norm["mime"] = norm.pop("mimeType")
            parts.append(norm)
    return parts


def format_tool_result_messages(
    result: Any,
    tool_call_id: str,
    text_fallback: Optional[str] = None,
    function_name: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Build LLM messages from a (possibly multimodal) tool result.

    For a plain text/JSON result this returns ``None`` so callers keep their
    existing single ``tool`` message behaviour (no regression). For a multimodal
    result it returns a list of messages: a ``tool`` message (satisfying the
    tool_call_id contract) followed by a ``user`` message carrying the
    model-visible image/text parts.

    Most providers do not accept ``image_url`` parts inside a ``tool`` role
    message, so images are delivered via a follow-up ``user`` message.

    When ``function_name`` belongs to an external/untrusted tool, any text
    parts are wrapped in the same prompt-injection fence used by the text path
    (``wrap_if_external``) so external instructions cannot reach the model as
    unfenced content.
    """
    pair = build_tool_result_message_pair(
        result, tool_call_id, text_fallback=text_fallback, function_name=function_name
    )
    if pair is None:
        return None
    tool_message, followup_message = pair
    return [tool_message, followup_message]


def build_tool_result_message_pair(
    result: Any,
    tool_call_id: str,
    text_fallback: Optional[str] = None,
    function_name: Optional[str] = None,
) -> Optional[tuple]:
    """Return ``(tool_message, followup_user_message)`` for a multimodal result.

    Separating the ``tool`` reply from the ``user`` media follow-up lets callers
    that process multiple tool calls in one assistant turn keep all ``tool``
    replies consecutive (the provider contract) and append the media
    ``user`` message(s) only after the whole batch is handled.

    Returns ``None`` for plain text/JSON results (existing path, no regression).
    """
    parts = _normalize_multimodal_result(result)
    if not parts:
        return None

    is_external = False
    if function_name:
        try:
            from ..tools.trust import is_external_tool
            is_external = is_external_tool(function_name)
        except Exception:
            is_external = False

    visible_parts: List[Dict[str, Any]] = []
    text_summary_chunks: List[str] = []
    has_media = False
    for part in parts:
        formatted = _content_part_to_data_uri(part)
        if formatted is None:
            continue
        if formatted.get("type") == "image_url":
            has_media = True
            visible_parts.append(formatted)
        else:
            text_value = formatted.get("text", "")
            if is_external and text_value:
                text_value = _fence_external_text(function_name, text_value)
                formatted = {"type": "text", "text": text_value}
            text_summary_chunks.append(text_value)
            visible_parts.append(formatted)

    if not visible_parts or not has_media:
        # Nothing model-visible beyond text -> let the text path handle it
        return None

    text_summary = "\n".join(c for c in text_summary_chunks if c).strip()
    tool_text = text_fallback or text_summary or "[tool returned media; see attached content]"

    tool_message = {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": tool_text,
    }
    followup_message = {
        "role": "user",
        "content": visible_parts,
    }
    return tool_message, followup_message


def _fence_external_text(function_name: str, text: str) -> str:
    """Apply the external-content prompt-injection fence to a text string."""
    try:
        from ..tools.trust import wrap_if_external
        wrapped = wrap_if_external(function_name, text)
        return wrapped if isinstance(wrapped, str) else text
    except Exception:
        return text


class ToolExecutionMixin:
    """Mixin providing toolexecution methods for the Agent class."""
    
    def _register_artifact_tools(self):
        """Register artifact retrieval tools when artifacts are first created."""
        try:
            from ..tools import artifact_tools
            
            # Set the store reference for the tools
            artifact_tools.set_artifact_store(self._artifact_store)
            
            # Add the retrieval tools
            tools_to_add = [
                artifact_tools.artifact_head,
                artifact_tools.artifact_tail,
                artifact_tools.artifact_grep,
                artifact_tools.artifact_chunk,
                artifact_tools.artifact_load,
                artifact_tools.artifact_list,
            ]
            
            # Only add if not already present
            existing_tool_names = {getattr(t, '__name__', str(t)) for t in self.tools}
            for tool in tools_to_add:
                tool_name = getattr(tool, '__name__', str(tool))
                if tool_name not in existing_tool_names:
                    self.tools.append(tool)
            
            logging.debug("Registered artifact retrieval tools")
        except Exception as e:
            logging.warning(f"Failed to register artifact tools: {e}")

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
        """Resolve tool names via the canonical resolver chain."""
        from ..tools.resolver import resolve_tool_names

        return resolve_tool_names(tool_names)

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
        
        # Route through user-supplied tool middleware (Agent(hooks=[...])) when
        # present. Zero overhead when no hooks: the fast path calls straight
        # into _execute_tool_with_context.
        manager = self._get_tool_middleware_manager()
        if manager is None:
            return self._execute_tool_with_context(function_name, arguments, state, tool_call_id)

        from ..hooks import ToolRequest, ToolResponse, InvocationContext
        request = ToolRequest(
            tool_name=function_name,
            arguments=arguments,
            context=InvocationContext(
                agent_id=self.name,
                run_id=getattr(self, '_current_run_id', 'unknown'),
                session_id=getattr(self, '_session_id', None) or 'default',
                tool_name=function_name,
            ),
        )

        def _final_handler(req: ToolRequest) -> ToolResponse:
            result = self._execute_tool_with_context(
                req.tool_name, req.arguments, state, tool_call_id
            )
            return ToolResponse(tool_name=req.tool_name, result=result)

        response = manager.execute_tool_call(request, _final_handler)
        return response.result if isinstance(response, ToolResponse) else response

    def _get_tool_middleware_manager(self):
        """Return a MiddlewareManager if user tool hooks are registered, else None.

        Lazily constructs the manager from ``self._hooks`` (the list passed via
        ``Agent(hooks=[...])``) on first use. Returns ``None`` when there are no
        hooks or no tool-level hooks, preserving the zero-overhead fast path.
        """
        hooks = getattr(self, '_hooks', None)
        if not hooks:
            return None
        manager = getattr(self, '_middleware_manager', None)
        if manager is None:
            from ..hooks import MiddlewareManager
            manager = MiddlewareManager(hooks)
            self._middleware_manager = manager
        return manager if manager.has_tool_hooks else None

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
        from ..streaming.events import StreamEvent, StreamEventType, tool_progress_channel
        import time as _time
        
        # Record the tool name for this turn so the self-improve review policy
        # can see what ran (issue #3037). Skipped during a guarded review turn
        # to avoid tracking the review's own tool calls or recursing.
        if not getattr(self, "_in_skill_review", False):
            turn_tools = getattr(self, "_turn_tools_used", None)
            if turn_tools is None:
                self._turn_tools_used = []
                turn_tools = self._turn_tools_used
            turn_tools.append(function_name)

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

        # Build a progress sink so tools can stream incremental output while they
        # run (e.g. line-buffered stdout from a long shell command). The sink
        # forwards TOOL_PROGRESS events to the stream emitter; it is only active
        # when callbacks are registered, so there is zero overhead otherwise.
        _progress_sink = None
        if _stream_emitter is not None and _stream_emitter.has_callbacks:
            def _progress_sink(_event):  # noqa: ANN001 — StreamEvent forwarder
                _event.tool_call = {"name": function_name, "id": tool_call_id}
                _event.agent_id = self.name
                _stream_emitter.emit(_event)
        
        blocked_result = None
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
            
            # Trigger BEFORE_TOOL hook (only build the input if a hook is actually registered)
            from ..hooks import HookEvent, BeforeToolInput
            if self._hook_runner.registry.has_hooks(HookEvent.BEFORE_TOOL):
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
                    if res.output and res.output.modified_input:
                        arguments.update(res.output.modified_input)

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

            # Result-aware tool-loop detection (name + args + result-hash).
            # Record this call, then run the detector on the pre-execution
            # history. On a CRITICAL verdict, block before executing (a genuine
            # stuck stall or A->B->A->B oscillation). A WARNING queues a
            # one-shot self-correction nudge for the next autonomous turn.
            # Zero overhead when disabled; polling with changing output is NOT
            # flagged (streaks break on result-hash change).
            if hasattr(self, '_ensure_loop_detector'):
                from . import loop_detection as _loop_detection
                _ld_history, _ld_config = self._ensure_loop_detector()
                if _ld_config.enabled:
                    _loop_detection.record_tool_call(
                        _ld_history, function_name, arguments, _ld_config
                    )
                    _verdict = _loop_detection.detect_tool_loop(
                        _ld_history, function_name, arguments, _ld_config
                    )
                    if _verdict.get("stuck"):
                        if _verdict.get("level") == "critical":
                            # Block via the shared blocked_result path so trace
                            # spans, stream events, AFTER_TOOL hooks, doom-loop
                            # and loop-guard teardown still run (matches the
                            # loop_guard BLOCK behaviour at line ~524).
                            blocked_result = {
                                "error": _verdict.get("message", "loop detected"),
                                "loop_blocked": True,
                            }
                        elif not getattr(self, '_loop_warned_this_turn', False):
                            self._loop_warned_this_turn = True
                            self._pending_self_correction = (
                                f"[System: repeated {_verdict.get('detector')} detected. "
                                f"Try a different approach. {_verdict.get('message', '')}]"
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
                
                # max_retry_limit is the number of retries (not total attempts)
                # So total attempts = 1 (initial) + max_retry_limit (retries)
                for attempt in range(1, max_retry_limit + 2):
                    try:
                        # P8/G11: Apply tool timeout if configured
                        tool_timeout = getattr(self, '_tool_timeout', None)
                        if tool_timeout and tool_timeout > 0:
                            # Guard the sink so a tool that keeps running after a
                            # timeout (future.cancel() cannot stop a started thread)
                            # can no longer emit progress once the result is decided.
                            _attempt_sink = _progress_sink
                            _progress_active = None
                            if _progress_sink is not None:
                                _progress_active = threading.Event()
                                _progress_active.set()

                                def _attempt_sink(_event, _src=_progress_sink, _flag=_progress_active):  # noqa: ANN001
                                    if _flag.is_set():
                                        _src(_event)

                            # Activate the progress channel BEFORE copy_context so the
                            # sink propagates into the executor thread via contextvars.
                            with tool_progress_channel(_attempt_sink):
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
                                    if _progress_active is not None:
                                        _progress_active.clear()
                                    future.cancel()
                                    logging.warning(f"Tool {function_name} timed out after {tool_timeout}s")
                                    result = {"error": f"Tool timed out after {tool_timeout}s", "timeout": True}
                        else:
                            with tool_progress_channel(_progress_sink), with_injection_context(state):
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
                            # For other error dicts: approval/permission denials are legitimate
                            # non-retryable outcomes; everything else represents a tool failure
                            # that should engage the outer retry/backoff loop.
                            elif result.get("approval_denied") or result.get("permission_denied") or result.get("approval_error") or result.get("policy_denied") or result.get("guardrail_denied"):
                                break
                            else:
                                # Avoid compounding with the inner retry loop in
                                # _execute_tool_with_circuit_breaker: error types it already
                                # retries (e.g. timeout/rate_limit/connection_error) are
                                # exhausted by the time they reach here, so escalating them as
                                # retryable would re-run the entire inner loop from scratch on
                                # every outer attempt. Only escalate error types the inner loop
                                # does NOT retry (e.g. "unknown") so they get one outer pass.
                                error_type = self._classify_error_type(result, None)
                                inner_policy = self._get_tool_retry_policy(function_name)
                                is_retryable = error_type not in inner_policy.retry_on
                                raise ToolExecutionError(
                                    result.get("error", f"Tool '{function_name}' failed"),
                                    tool_name=function_name,
                                    agent_id=self.name,
                                    is_retryable=is_retryable,
                                )
                        else:
                            # Success path - return the result
                            break
                            
                    except ToolExecutionError as e:
                        last_exception = e
                        # Only retry if the error is marked as retryable and we have retries left
                        # attempt starts at 1, so (attempt - 1) gives us the retry count
                        if not e.is_retryable or (attempt - 1) >= max_retry_limit:
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
                        
                        # attempt starts at 1, so (attempt - 1) gives us the retry count
                        if not is_retryable or (attempt - 1) >= max_retry_limit:
                            raise tool_error from e
                        
                        # Calculate delay for exponential backoff
                        delay = BackoffPolicy.delay(attempt, retry_initial_delay, retry_backoff_factor, retry_jitter)
                        logging.warning(
                            f"Tool {function_name} failed (attempt {attempt}/{max_retry_limit + 1}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
            
            # Apply runtime-scoped middleware normalization BEFORE hooks fire
            # Plugin harnesses can register middleware to normalize vendor-specific results
            runtime_id = getattr(self, '_runtime_id', 'praisonai')  # Default to native runtime
            normalized_result = None  # Track normalized result for hooks
            if runtime_id != 'praisonai':  # Skip for native runtime to avoid allocation
                try:
                    from ..runtime import get_middleware, MiddlewareContext
                    middleware = get_middleware(runtime_id)
                    
                    # Only allocate context and normalize if not using default pass-through
                    if middleware.runtime_id != 'praisonai':
                        mw_ctx = MiddlewareContext(
                            tool_name=function_name,
                            runtime_id=runtime_id,
                            agent_id=self.name,
                            session_id=getattr(self, '_session_id', None),
                            execution_time_ms=(_time.time() - _tool_start_time) * 1000,
                            metadata={'original_result_type': type(result).__name__}
                        )
                        
                        normalized_result = middleware.normalize(result, function_name, mw_ctx)
                        
                        # Handle error cases by propagating error message as result
                        if not normalized_result.success and normalized_result.error_message:
                            # For failed tools, include error context in the result
                            result = f"Tool Error: {normalized_result.error_message}"
                        else:
                            # For successful tools, use the normalized content
                            result = normalized_result.content
                        
                        # Store normalized result for hooks to access full context
                        self._last_normalized_result = normalized_result
                        
                        logger.debug(f"Applied runtime middleware for {runtime_id}: {function_name}")
                except ImportError:
                    # Runtime middleware not available - continue without normalization
                    logger.debug("Runtime middleware not available, skipping normalization")
                except Exception as e:
                    # Don't let middleware failures break tool execution
                    logger.warning(f"Runtime middleware failed for {runtime_id}: {e}")
            
            # Detect multimodal tool results (images/files) BEFORE any trust
            # wrapping or truncation mutates/stringifies them. Multimodal results
            # are returned as-is so the message-building layer can emit
            # model-visible image parts via format_tool_result_messages().
            _is_multimodal_result = _normalize_multimodal_result(result) is not None

            # Apply prompt injection protection for external tools
            # Zero-cost for trusted tools, wraps external content in security markers
            if not _is_multimodal_result:
                try:
                    from ..tools.trust import wrap_if_external
                    result = wrap_if_external(function_name, result)
                except Exception:
                    # Trust module unavailable (partial/broken install) must not
                    # abort tool execution; fall through with the raw result.
                    pass
            
            # Apply tool output truncation to prevent context overflow
            # Uses context manager budget if enabled, otherwise applies default limit
            if result and not _is_multimodal_result:
                try:
                    result_str = str(result)
                    
                    # Get configured limit
                    limit = getattr(self, 'tool_output_limit', DEFAULT_TOOL_OUTPUT_LIMIT)
                    
                    # Initialize artifact reference before limit check so downstream
                    # `if artifact_ref:` guards remain valid on short-result paths.
                    artifact_ref = None

                    # Check if we need to spill to artifact store
                    if len(result_str) > limit:
                        # Try to use artifact store if available
                        if hasattr(self, '_artifact_store') and self._artifact_store is not None:
                            try:
                                from ..context.artifacts import ArtifactMetadata
                                
                                # Create metadata for this artifact
                                metadata = ArtifactMetadata(
                                    agent_id=self.name,
                                    run_id=getattr(self, '_current_run_id', 'unknown'),
                                    tool_name=function_name,
                                    turn_id=getattr(self, '_turn_counter', 0),
                                )
                                
                                # Store the full output
                                artifact_ref = self._artifact_store.store(result_str, metadata)
                                logging.debug(f"Stored {function_name} output ({len(result_str)} bytes) as artifact {artifact_ref.artifact_id}")
                                
                                # Register artifact retrieval tools if not already registered
                                if not hasattr(self, '_artifact_tools_registered'):
                                    self._register_artifact_tools()
                                    self._artifact_tools_registered = True
                            except Exception as e:
                                logging.debug(f"Failed to store artifact: {e}")
                        
                        # Generate truncated preview
                        tail_size = min(limit // 5, 2000)
                        head = result_str[:limit - tail_size]
                        tail = result_str[-tail_size:] if tail_size > 0 else ""
                        
                        # If we stored an artifact, include reference in the output
                        if artifact_ref:
                            truncated = (
                                f"{head}\n"
                                f"...[{len(result_str):,} chars total, showing first/last portions]...\n"
                                f"{tail}\n\n"
                                f"{artifact_ref.to_inline()}"
                            )
                        else:
                            # Fallback to simple truncation
                            truncated = f"{head}\n...[{len(result_str):,} chars, showing first/last portions]...\n{tail}"
                    else:
                        truncated = result_str
                    
                    if self.context_manager and hasattr(self, '_truncate_tool_output'):
                        # Use context-aware truncation if available, but preserve artifact reference
                        if artifact_ref:
                            # Extract the artifact reference from the truncated string
                            artifact_inline = artifact_ref.to_inline()
                            # Remove the artifact reference before context truncation
                            truncated_without_ref = truncated.replace(artifact_inline, "").rstrip()
                            # Apply context truncation
                            truncated_without_ref = self._truncate_tool_output(function_name, truncated_without_ref, tool_call_id)
                            # Re-append the artifact reference
                            truncated = f"{truncated_without_ref}\n\n{artifact_inline}"
                        else:
                            truncated = self._truncate_tool_output(function_name, truncated, tool_call_id)
                    
                    if len(truncated) < len(result_str):
                        logging.debug(f"Truncated {function_name} output from {len(result_str)} to {len(truncated)} chars")
                        # For dicts, truncate large string fields (e.g., raw_content from search)
                        if isinstance(result, dict):
                            max_field_chars = getattr(self, 'tool_output_limit', DEFAULT_TOOL_OUTPUT_LIMIT) if not self.context_manager else None
                            result = self._truncate_dict_fields(result, function_name, max_field_chars, tool_call_id)
                            # Add artifact reference to dict result if available
                            if artifact_ref:
                                result["_artifact_ref"] = artifact_ref.to_dict()
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
            
            # Extract error information from normalized result if available
            tool_error = None
            if hasattr(self, '_last_normalized_result') and self._last_normalized_result:
                if not self._last_normalized_result.success and self._last_normalized_result.error_message:
                    tool_error = self._last_normalized_result.error_message
                # Clean up temporary attribute
                delattr(self, '_last_normalized_result')
            
            # Only build the input if an AFTER_TOOL hook is actually registered
            if self._hook_runner.registry.has_hooks(HookEvent.AFTER_TOOL):
                after_tool_input = AfterToolInput(
                    session_id=getattr(self, '_session_id', 'default'),
                    cwd=os.getcwd(),
                    event_name=HookEvent.AFTER_TOOL,
                    timestamp=str(_time.time()),
                    agent_name=self.name,
                    tool_name=function_name,
                    tool_input=arguments,
                    tool_output=result,
                    tool_error=tool_error,
                    execution_time_ms=(_time.time() - _tool_start_time) * 1000
                )
                after_tool_results = self._hook_runner.execute_sync(HookEvent.AFTER_TOOL, after_tool_input, target=function_name)

                # Surface any additional_context returned by AFTER_TOOL hooks
                # back to the model by appending it to the tool result (mirrors
                # the loop-guard injection pattern below). Without this the
                # neutral additional_context channel would be silently dropped.
                extra_context = self._hook_runner.aggregate_context(after_tool_results)
                if extra_context:
                    if isinstance(result, str):
                        result = f"{result}\n\n{extra_context}"
                    elif isinstance(result, dict):
                        result.setdefault("_additional_context", extra_context)
                    else:
                        result = {"value": result, "_additional_context": extra_context}
            
            # Back-fill the result hash so the result-aware detector can tell a
            # genuine stall (identical output) from legitimate polling (changing
            # output). This is the key data-fix: fingerprints now include output.
            if hasattr(self, '_ensure_loop_detector'):
                from . import loop_detection as _loop_detection
                _ld_history, _ld_config = self._ensure_loop_detector()
                if _ld_config.enabled:
                    _loop_detection.record_tool_outcome(
                        _ld_history, function_name, arguments, result, _ld_config
                    )

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
                loop_guard.record(function_name, arguments, is_success, result=result)
                # Surface the loop-guard decision back to the model on this same
                # iteration. Previously only WARN was injected, so a post-exec
                # BLOCK/HALT (e.g. the call that first reaches a threshold) was
                # silently discarded and only took effect on the next
                # pre-execution check. Injecting block/halt here ensures the stop
                # signal reaches the model immediately without raising mid-turn.
                decision = loop_guard.check(function_name, arguments, is_pre_execution=False)
                if decision.action.value in ("warn", "block", "halt"):
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
            
            # Wrap the exception if it's not already a ToolExecutionError
            if not isinstance(e, ToolExecutionError):
                is_retryable = not isinstance(e, (ValueError, TypeError, AttributeError))
                raise ToolExecutionError(
                    f"Tool '{function_name}' failed: {e}",
                    tool_name=function_name,
                    agent_id=self.name,
                    is_retryable=is_retryable,
                ) from e
            raise  # Re-raise if already wrapped

    def _build_after_agent_input(self, prompt, response, start_time, tools_used=None):
        """Build the AfterAgentInput payload shared by sync/async hook dispatch.

        Loop-agnostic (no ``await``, no event-loop interaction) so it can be
        reused by both ``_trigger_after_agent_hook`` and
        ``_atrigger_after_agent_hook`` without any async-safety change.
        """
        from ..hooks import HookEvent, AfterAgentInput
        return AfterAgentInput(
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

    def _after_agent_side_effects(self, prompt, response):
        """Run loop-agnostic after-agent side effects (no ``await`` inside).

        Covers auto-memory extraction, auto-learning extraction, and the
        periodic learning nudge. Skill-review and hook dispatch remain in the
        respective sync/async public methods because they differ on the async
        boundary.
        """
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

    def _trigger_after_agent_hook(self, prompt, response, start_time, tools_used=None):
        """Trigger AFTER_AGENT hook and return response."""
        # During a guarded skill-review turn, skip the entire after-agent
        # side-effect pipeline (hooks, auto-memory, auto-learning, nudge,
        # skill-review). The review turn is internal and must not re-fire
        # these effects or recurse into another review.
        if getattr(self, "_in_skill_review", False):
            return response
        # Default tools_used from the per-turn buffer when the caller did not
        # pass it explicitly (issue #3037). Chat paths return without wiring
        # tools_used, so without this the review policy always sees an empty
        # list and never runs. Consume the buffer so the next turn starts clean.
        if tools_used is None:
            tools_used = list(getattr(self, "_turn_tools_used", []) or [])
        self._turn_tools_used = []
        # Trigger AFTER_AGENT hook (only build the input if a hook is actually registered)
        from ..hooks import HookEvent
        if self._hook_runner.registry.has_hooks(HookEvent.AFTER_AGENT):
            after_agent_input = self._build_after_agent_input(prompt, response, start_time, tools_used)
            self._hook_runner.execute_sync(HookEvent.AFTER_AGENT, after_agent_input)

        self._after_agent_side_effects(prompt, response)

        # Autonomous skill self-improvement loop (opt-in via self_improve=True).
        # Runs a guarded review pass restricted to skill_manage. No-op when
        # disabled or already inside a review (re-entrancy guarded). In
        # "background" mode (self_improve="background") the extra LLM review
        # turn is deferred to the core background runner so the reply is not
        # gated on it (issue #2985).
        try:
            run_review = getattr(self, "_run_skill_review", None)
            if run_review is not None:
                self._dispatch_skill_review(run_review, prompt, response, tools_used)
        except Exception as e:
            logger.warning(
                "Skill self-improvement review failed for agent=%s session_id=%s; "
                "set self_improve=False to disable this best-effort pass. error=%s",
                getattr(self, "name", None),
                getattr(self, "_session_id", None),
                e,
                exc_info=True,
            )

        return response

    def _dispatch_skill_review(self, run_review, prompt, response, tools_used):
        """Run the guarded skill review inline or in the background per mode.

        Central routing so the sync and async after-agent paths stay in
        lock-step. When ``self._self_improve_mode == "background"`` the review
        (a full extra LLM turn) is enqueued on the core background runner via
        the mixin's :meth:`_schedule_self_improvement`; otherwise it runs
        inline exactly as before (default, backward compatible).
        """
        if getattr(self, "_self_improve_mode", "inline") == "background":
            schedule = getattr(self, "_schedule_self_improvement", None)
            if schedule is not None:
                schedule(lambda: run_review(prompt, response, tools_used))
                return
        run_review(prompt, response, tools_used)

    async def _atrigger_after_agent_hook(self, prompt, response, start_time, tools_used=None):
        """Async version: Trigger AFTER_AGENT hook and return response."""
        # During a guarded skill-review turn, skip the entire after-agent
        # side-effect pipeline (see sync variant for rationale).
        if getattr(self, "_in_skill_review", False):
            return response
        # Default tools_used from the per-turn buffer when the caller did not
        # pass it explicitly (issue #3037); mirrors the sync path.
        if tools_used is None:
            tools_used = list(getattr(self, "_turn_tools_used", []) or [])
        self._turn_tools_used = []
        # Trigger AFTER_AGENT hook (only build the input if a hook is actually registered)
        from ..hooks import HookEvent
        if self._hook_runner.registry.has_hooks(HookEvent.AFTER_AGENT):
            after_agent_input = self._build_after_agent_input(prompt, response, start_time, tools_used)
            await self._hook_runner.execute(HookEvent.AFTER_AGENT, after_agent_input)

        self._after_agent_side_effects(prompt, response)

        # Autonomous skill self-improvement loop (opt-in via self_improve=True).
        # In "background" mode the review runs off the hot path on the core
        # background runner (issue #2985); otherwise it is awaited inline.
        try:
            if getattr(self, "_self_improve_mode", "inline") == "background":
                run_review = getattr(self, "_run_skill_review", None)
                schedule = getattr(self, "_schedule_self_improvement", None)
                if run_review is not None and schedule is not None:
                    schedule(lambda: run_review(prompt, response, tools_used))
                elif run_review is not None:
                    run_review(prompt, response, tools_used)
            else:
                arun_review = getattr(self, "_arun_skill_review", None)
                if arun_review is not None:
                    await arun_review(prompt, response, tools_used)
        except Exception as e:
            logger.warning(
                "Skill self-improvement review failed for agent=%s session_id=%s; "
                "set self_improve=False to disable this best-effort pass. error=%s",
                getattr(self, "name", None),
                getattr(self, "_session_id", None),
                e,
                exc_info=True,
            )

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

    DEFAULT_OUTPUT_RESERVATION_TOKENS = 1024

    def _estimate_min_call_cost(self, messages, max_tokens=None) -> float:
        """Estimate the minimum cost of an upcoming LLM call before dispatch.

        Uses the known input size (messages) plus an output-token reservation
        so the budget can be enforced as a hard pre-call ceiling. When the agent
        has no ``max_tokens`` configured, a conservative default reservation
        (``DEFAULT_OUTPUT_RESERVATION_TOKENS``) is used so a small prompt with a
        large provider-default response cannot trivially bypass the guard and
        then overshoot the cap. Input tokens are approximated as ~4 characters
        per token, matching the rest of the codebase.

        Note: This is intentionally a *minimum* estimate. It counts message
        content only and does not include tool-schema tokens, so a tool-heavy
        request may still cost more than estimated; the reactive post-call
        accounting remains the backstop for that case.

        Args:
            messages: The messages that will be sent to the LLM.
            max_tokens: Optional output-token reservation. Falls back to
                ``DEFAULT_OUTPUT_RESERVATION_TOKENS`` when not provided.

        Returns:
            Estimated minimum cost in USD for the call.
        """
        prompt_chars = 0
        if messages:
            for _msg in messages:
                _content = _msg.get("content") if isinstance(_msg, dict) else None
                if isinstance(_content, str):
                    prompt_chars += len(_content)
                elif isinstance(_content, list):
                    for _part in _content:
                        if isinstance(_part, dict):
                            _text = _part.get("text")
                            if isinstance(_text, str):
                                prompt_chars += len(_text)
                elif _content is not None:
                    prompt_chars += len(str(_content))

        prompt_tokens = prompt_chars // 4
        if max_tokens:
            completion_tokens = int(max_tokens)
        elif prompt_chars > 0:
            completion_tokens = self.DEFAULT_OUTPUT_RESERVATION_TOKENS
        else:
            completion_tokens = 0
        return self._calculate_llm_cost(prompt_tokens, completion_tokens)

    def _truncate_dict_fields(self, data: dict, tool_name: str, max_field_chars: int = None, tool_call_id: str = None) -> dict:
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
                truncated = f"{head}\n...[{len(value):,} chars, showing first/last portions]...\n{tail}"
                
                # Store full field value for later retrieval
                try:
                    from ..runtime.tool_output_store import get_tool_output_store
                    from uuid import uuid4
                    store = get_tool_output_store(getattr(self, '_run_id', None))
                    # Add unique suffix to prevent collisions with repeated keys
                    unique_suffix = uuid4().hex[:8]
                    field_call_id = f"{tool_call_id}_{key}_{unique_suffix}" if tool_call_id else f"{tool_name}_{key}_{unique_suffix}"
                    metadata = store.store(f"{tool_name}.{key}", value, call_id=field_call_id)
                    if metadata:
                        truncated = store.format_reference(metadata, truncated)
                        logging.debug(f"Stored full {tool_name}.{key} field ({len(value)} bytes) at {metadata.get('path')}")
                except Exception as e:
                    logging.debug(f"Failed to store dict field: {e}")
                
                result[key] = truncated
                logging.debug(f"Smart truncated field '{key}' from {len(value)} to ~{max_field_chars} chars")
            elif isinstance(value, dict):
                result[key] = self._truncate_dict_fields(value, tool_name, max_field_chars, tool_call_id)
            elif isinstance(value, list):
                result[key] = [
                    self._truncate_dict_fields(item, tool_name, max_field_chars, tool_call_id) if isinstance(item, dict)
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

        # PermissionMode / PermissionManager gate. This must run *before* the
        # backend/registry approval logic so an explicit ``ask`` rule actually
        # prompts, a ``deny`` rejects, ``PermissionMode.BYPASS`` short-circuits
        # to always-allow, and ``PLAN``/``DONT_ASK`` deny as documented.
        mode_decision = self._resolve_permission_mode_decision(
            tool_name, is_async=is_async
        )
        if mode_decision is not None:
            return mode_decision
        manager_forces_approval = self._permission_manager_requires_approval(tool_name)

        backend = getattr(self, '_approval_backend', None)
        approve_all = getattr(self, '_approve_all_tools', False)
        
        # Check tool trust level if available
        tool_registry = get_tool_registry()
        trust_level = tool_registry.get_trust_level(tool_name)
        
        if backend is not None:
            # Also honour approval requirements registered through the public
            # registry (e.g. a plugin/startup hook marking a custom destructive
            # tool as requiring approval). Without this, the backend path would
            # only gate the built-in DEFAULT_DANGEROUS_TOOLS and silently skip
            # registry-required tools.
            approval_registry = get_approval_registry()
            registry_required = approval_registry.is_required(tool_name)
            # Check if tool needs approval based on multiple criteria
            needs_approval = (
                approve_all 
                or tool_name in DEFAULT_DANGEROUS_TOOLS
                or registry_required
                or manager_forces_approval  # explicit PermissionManager ``ask`` rule
                or (trust_level == "external")  # External tools need approval
            )
            if needs_approval:
                request = ApprovalRequest(
                    tool_name=tool_name,
                    arguments=tool_args,
                    risk_level=(
                        approval_registry.get_risk_level(tool_name)
                        or DEFAULT_DANGEROUS_TOOLS.get(tool_name, "medium")
                    ),
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
            # No approval backend configured. An explicit PermissionManager
            # ``ask`` rule must still gate the call, so mark it required in the
            # approval registry (idempotent) before delegating so the registry
            # prompts instead of silently allowing.
            if manager_forces_approval:
                try:
                    get_approval_registry().add_requirement(tool_name)
                except Exception:  # noqa: BLE001
                    pass
            if is_async:
                return get_approval_registry().approve_async(
                    getattr(self, 'name', None), tool_name, tool_args,
                )
            else:
                return get_approval_registry().approve_sync(
                    getattr(self, 'name', None), tool_name, tool_args,
                )

    def _permission_manager_requires_approval(self, function_name) -> bool:
        """Return ``True`` when an explicit ``ask`` rule gates *function_name*.

        Consults the attached ``PermissionManager`` so a rule with
        ``action="ask"`` actually drives the approval prompt at execution time
        (previously only a hard ``deny`` had any effect). ``allow``/``deny`` and
        the "no matching rule" default are not treated as approval-forcing here
        (``deny`` is already handled by ``_check_permission_manager_deny``).
        """
        manager = getattr(self, "_permission_manager", None)
        if manager is None:
            return False
        try:
            from ..permissions import PermissionAction
            action = manager.resolve_tool_action(
                function_name, getattr(self, "name", None)
            )
            return action == PermissionAction.ASK
        except Exception as e:  # noqa: BLE001
            logging.debug(
                "permission manager resolve_tool_action failed for %s: %s",
                function_name, e,
            )
            return False

    def _resolve_permission_mode_decision(self, function_name, is_async=False):
        """Apply ``PermissionMode`` to *function_name*, if a mode is set.

        Returns an ``ApprovalDecision`` (or its awaitable in async context) when
        the mode determines the outcome, else ``None`` to defer to the normal
        approval flow.

        - ``BYPASS``: skip all permission checks → always allow.
        - ``PLAN``: read-only exploration → deny any tool not tagged read-only.
        - ``DONT_ASK``: auto-deny anything that would otherwise prompt for input
          (an explicit ``ask`` rule or a known dangerous tool).
        - ``DEFAULT``/``ACCEPT_EDITS``/unset: defer (return ``None``).
        """
        mode = getattr(self, "_permission_mode", None)
        if mode is None:
            return None
        try:
            from ..permissions import PermissionMode
        except Exception:  # noqa: BLE001
            return None

        # Normalise string values to the enum for robustness.
        if isinstance(mode, str):
            try:
                mode = PermissionMode(mode)
            except ValueError:
                return None

        from ..approval.protocols import ApprovalDecision

        def _wrap(decision):
            if is_async:
                async def _coro():
                    return decision
                return _coro()
            return decision

        if mode == PermissionMode.BYPASS:
            return _wrap(ApprovalDecision(
                approved=True, reason="PermissionMode.BYPASS: permission checks skipped"
            ))

        if mode == PermissionMode.PLAN:
            # PLAN allows only side-effect-free exploration. A tool is treated as
            # read-only only when its name has no mutation marker *and* it is not
            # flagged as approval-worthy elsewhere (dangerous / external /
            # registry-required / explicit ``ask`` rule). This closes the gap
            # where a write-capable tool (e.g. ``send_email``) whose name misses
            # the marker list would otherwise be allowed in plan mode.
            if self._is_read_only_tool(function_name) and not self._tool_would_prompt(function_name):
                return _wrap(ApprovalDecision(
                    approved=True, reason="PermissionMode.PLAN: read-only tool allowed"
                ))
            return _wrap(ApprovalDecision(
                approved=False,
                reason=f"PermissionMode.PLAN: '{function_name}' is not read-only; write operations are not allowed",
            ))

        if mode == PermissionMode.DONT_ASK:
            # Auto-deny anything that would otherwise prompt so a non-interactive
            # run never hangs — including tools that prompt only because of their
            # ``external`` trust level or a registry approval requirement.
            if self._tool_would_prompt(function_name):
                return _wrap(ApprovalDecision(
                    approved=False,
                    reason=f"PermissionMode.DONT_ASK: auto-denied prompt for '{function_name}'",
                ))
            return None

        return None

    def _tool_would_prompt(self, function_name) -> bool:
        """Return ``True`` when *function_name* would trigger an approval prompt.

        Mirrors the ``needs_approval`` criteria in ``_resolve_approval_decision``
        so ``DONT_ASK`` and ``PLAN`` see the same set of prompt-worthy tools:
        an explicit ``ask`` rule, a built-in dangerous tool, a registry-required
        tool, or an ``external`` trust level.
        """
        try:
            from ..approval.registry import DEFAULT_DANGEROUS_TOOLS
            if function_name in DEFAULT_DANGEROUS_TOOLS:
                return True
            if self._permission_manager_requires_approval(function_name):
                return True
            from ..approval import get_approval_registry
            if get_approval_registry().is_required(function_name):
                return True
            from ..tools import get_registry as get_tool_registry
            if get_tool_registry().get_trust_level(function_name) == "external":
                return True
        except Exception as e:  # noqa: BLE001
            logging.debug("_tool_would_prompt failed for %s: %s", function_name, e)
        return False

    @staticmethod
    def _is_read_only_tool(function_name) -> bool:
        """Best-effort heuristic for whether a tool only reads (no writes).

        Used by ``PermissionMode.PLAN``. Tools whose names imply mutation
        (write/edit/delete/create/run/exec/…) are treated as non-read-only.
        """
        if not function_name:
            return True
        name = str(function_name).lower()
        write_markers = (
            "write", "edit", "append", "delete", "remove", "create", "mkdir",
            "rm", "put", "post", "patch", "update", "insert", "save", "move",
            "rename", "chmod", "chown", "exec", "run", "shell", "bash", "command",
            "kill", "apply_patch", "install", "deploy",
        )
        return not any(marker in name for marker in write_markers)

    def _check_permission_manager_deny(self, function_name):
        """Return an error dict if the PermissionManager hard-denies the tool.

        Ensures the pattern-based ``PermissionManager`` (rules from
        ``.praisonai/permissions/``, YAML or Python) gates every tool-call path
        uniformly — native functions **and** MCP tools — since both flow through
        ``_execute_tool_impl``. Returns ``None`` when no manager is attached or
        the tool is not denied, preserving backward compatibility.
        """
        manager = getattr(self, "_permission_manager", None)
        if manager is None:
            return None
        try:
            if manager.is_denied(function_name, getattr(self, "name", None)):
                return {
                    "error": f"Tool '{function_name}' blocked by permission policy",
                    "permission_denied": True,
                }
        except Exception as e:
            logging.debug("permission manager is_denied failed for %s: %s", function_name, e)
        return None

    def _is_bypass_mode(self) -> bool:
        """Return ``True`` when ``PermissionMode.BYPASS`` is active.

        BYPASS means *skip all permission checks*, so it must short-circuit
        even the pattern-based ``PermissionManager`` deny gate (which otherwise
        runs before the approval decision and would block the tool first).
        """
        mode = getattr(self, "_permission_mode", None)
        if mode is None:
            return False
        try:
            from ..permissions import PermissionMode
            if isinstance(mode, str):
                try:
                    mode = PermissionMode(mode)
                except ValueError:
                    return False
            return mode == PermissionMode.BYPASS
        except Exception:  # noqa: BLE001
            return False

    def _check_tool_approval_sync(self, function_name, arguments):
        """Check tool approval synchronously. Returns (decision, arguments) or error dict."""
        # Permission tier fast-path (O(1) frozenset lookup, resolved at __init__)
        if self._perm_deny and function_name in self._perm_deny:
            return {"error": f"Tool '{function_name}' blocked by permission policy", "permission_denied": True}
        if self._perm_allow is not None and function_name not in self._perm_allow:
            return {"error": f"Tool '{function_name}' not in allowed tools list", "permission_denied": True}

        # Pattern-based PermissionManager deny gate (native + MCP, uniform).
        # BYPASS mode skips this gate as its contract requires.
        if not self._is_bypass_mode():
            manager_denial = self._check_permission_manager_deny(function_name)
            if manager_denial is not None:
                return manager_denial

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

        # Pattern-based PermissionManager deny gate (native + MCP, uniform).
        # BYPASS mode skips this gate as its contract requires.
        if not self._is_bypass_mode():
            manager_denial = self._check_permission_manager_deny(function_name)
            if manager_denial is not None:
                return manager_denial

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
                        result.get("policy_denied") or
                        result.get("guardrail_denied") or
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
            
            # Get or create circuit breaker for this tool.
            # Scope the key to this Agent instance so one agent's failing tool
            # cannot trip the breaker for another agent's same-named tool.
            breaker_name = f"tool_{id(self)}_{function_name}"
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
                   not result.get("approval_error") and \
                   not result.get("policy_denied") and \
                   not result.get("guardrail_denied"):
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

    def _check_tool_policy_and_guardrails(self, function_name, arguments):
        """Gate a tool call through the attached PolicyEngine and tool guardrails.

        Consults ``self._policy`` (a ``PolicyEngine``) via ``check_tool`` and any
        tool-call guardrails exposing ``validate_tool_call``. Returns an error
        dict when the call is denied, or ``(None, arguments)`` (arguments possibly
        rewritten by a guardrail) when allowed. Zero overhead when neither is set.
        """
        policy = getattr(self, "_policy", None)
        if policy is not None and hasattr(policy, "check_tool"):
            try:
                result = policy.check_tool(function_name, arguments)
            except Exception as e:  # noqa: BLE001
                # Fail closed: an operator opted into policy enforcement, so a
                # broken/misconfigured PolicyEngine must deny rather than let a
                # protected tool run without a decision.
                logging.warning(
                    f"Tool '{function_name}' denied: policy check_tool raised: {e}"
                )
                return {
                    "error": f"Tool '{function_name}' denied: policy check failed ({e})",
                    "policy_denied": True,
                }
            if not getattr(result, "allowed", True):
                reason = getattr(result, "reason", "denied by policy")
                logging.warning(
                    f"Tool '{function_name}' denied by policy: {reason}"
                )
                return {
                    "error": f"Tool '{function_name}' denied by policy: {reason}",
                    "policy_denied": True,
                }

        for guardrail in getattr(self, "_tool_call_guardrails", None) or []:
            validate = getattr(guardrail, "validate_tool_call", None)
            if validate is None:
                continue
            try:
                is_valid, processed = validate(function_name, arguments)
            except Exception as e:  # noqa: BLE001
                # Fail closed: mirror the guardrail-chain default. A guardrail
                # dependency/implementation error must block, not permit, the
                # unchecked call.
                logging.warning(
                    f"Tool '{function_name}' denied: guardrail validate_tool_call raised: {e}"
                )
                return {
                    "error": f"Tool '{function_name}' denied: guardrail check failed ({e})",
                    "guardrail_denied": True,
                }
            if not is_valid:
                logging.warning(
                    f"Tool '{function_name}' rejected by tool-call guardrail"
                )
                return {
                    "error": f"Tool '{function_name}' rejected by guardrail",
                    "guardrail_denied": True,
                }
            if isinstance(processed, dict):
                arguments = processed
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

        # Policy/guardrail gate (protocol-driven). Runs after approval so an
        # explicit PolicyEngine deny or a tool-call guardrail can block a tool
        # before dispatch (native + MCP, uniform). Zero overhead when unset.
        policy_result = self._check_tool_policy_and_guardrails(function_name, arguments)
        if isinstance(policy_result, dict):
            return policy_result  # Error dict
        _, arguments = policy_result

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
            # Cheap, deterministic self-repair: the model often emits a name that
            # only differs by case/separator (e.g. 'WebSearch' -> 'web_search').
            # Build a normalised index of the agent's active tools and re-match.
            def _norm(n):
                return str(n).lower().replace('_', '').replace('-', '').replace(' ', '')

            normalised = {}
            for name, tool in self._iter_active_named_tools():
                normalised.setdefault(_norm(name), []).append((name, tool))
            match = normalised.get(_norm(function_name))
            if match and len(match) == 1:
                matched_name, func = match[0]
                logging.debug(
                    f"Self-repaired tool name {function_name!r} -> {matched_name!r}"
                )

        if func:
            bind_target = func
            bind_arguments = arguments
            try:
                # BaseTool instances (plugin system) - call run() method
                from ..tools.base import BaseTool
                if isinstance(func, BaseTool):
                    bind_target = func.run
                    casted_arguments = self._cast_arguments(func.run, arguments)
                    bind_arguments = casted_arguments
                    return func.run(**casted_arguments)
                
                # Langchain: If it's a class with run but not _run, instantiate and call run
                if inspect.isclass(func) and hasattr(func, 'run') and not hasattr(func, '_run'):
                    instance = func()
                    bind_target = instance.run
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance.run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance.run, run_params)
                    bind_arguments = casted_params
                    return instance.run(**casted_params)

                # CrewAI: If it's a class with an _run method, instantiate and call _run
                elif inspect.isclass(func) and hasattr(func, '_run'):
                    instance = func()
                    bind_target = instance._run
                    run_params = {k: v for k, v in arguments.items() 
                                  if k in inspect.signature(instance._run).parameters 
                                  and k != 'self'}
                    casted_params = self._cast_arguments(instance._run, run_params)
                    bind_arguments = casted_params
                    return instance._run(**casted_params)

                # Otherwise treat as regular function
                elif callable(func):
                    bind_target = func
                    casted_arguments = self._cast_arguments(func, arguments)
                    bind_arguments = casted_arguments
                    return func(**casted_arguments)
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Error executing tool {function_name}: {error_msg}")
                # Only echo the parameter schema when the failure is a genuine
                # argument-binding error (wrong/missing/extra kwargs). A
                # TypeError/ValueError raised *inside* a successfully-bound tool
                # (domain validation) must not be mislabelled as a parameter
                # problem, or the model would alter valid call arguments instead
                # of fixing the offending value.
                if self._is_argument_binding_error(bind_target, bind_arguments):
                    schema = self._tool_parameter_hint(func)
                    if schema:
                        # Fold the parameter names into the error string itself so
                        # the hint survives conversion to ToolExecutionError (which
                        # keeps only the message) and actually reaches the model.
                        error_msg = (
                            f"{error_msg} Expected parameters for '{function_name}' — "
                            f"required: {schema['required']}, optional: {schema['optional']}."
                        )
                        return {"error": error_msg, "expected_parameters": schema}
                return {"error": error_msg}

        # Unresolved: return a corrective, model-readable message so the model can
        # retry with a valid name instead of repeating the same mistake.
        available = self._available_active_tool_names()
        suggestion = None
        try:
            import difflib
            near = difflib.get_close_matches(function_name, available, n=1, cutoff=0.5)
            suggestion = near[0] if near else None
        except Exception:
            pass
        hint = f" Did you mean '{suggestion}'?" if suggestion else ""
        error_msg = (
            f"Tool '{function_name}' not found.{hint} "
            f"Available tools: {available}"
        )
        logging.error(error_msg)
        return {"error": error_msg, "available_tools": available}

    def _get_tool_display_name(self, tool):
        """Best-effort display name for an agent tool of any supported kind."""
        try:
            from ..tools.base import BaseTool
            if isinstance(tool, BaseTool):
                return getattr(tool, 'name', None)
        except ImportError:
            pass
        name = getattr(tool, 'name', None)
        if isinstance(name, str) and name:
            return name
        if callable(tool) or inspect.isclass(tool):
            return getattr(tool, '__name__', None)
        return None

    def _iter_active_named_tools(self):
        """Yield ``(name, tool)`` for every active tool.

        MCP instances are expanded into their contained tools (each MCP tool is
        an iterable callable with a ``__name__``/``name``) so they participate
        in name repair and appear in the corrective inventory, rather than only
        exposing the opaque container.
        """
        MCP = None
        try:
            from ..mcp.mcp import MCP
        except ImportError:
            pass

        def _expand(tool):
            if MCP is not None and isinstance(tool, MCP):
                try:
                    for sub in tool:
                        sub_name = self._get_tool_display_name(sub)
                        if sub_name:
                            yield sub_name, sub
                except Exception:
                    pass
                return
            name = self._get_tool_display_name(tool)
            if name:
                yield name, tool

        tools = self.tools
        if MCP is not None and isinstance(tools, MCP):
            yield from _expand(tools)
            return
        for tool in tools if isinstance(tools, (list, tuple)) else []:
            yield from _expand(tool)

    def _available_active_tool_names(self):
        """Names of the agent's currently active tools, for corrective feedback."""
        names = [name for name, _tool in self._iter_active_named_tools()]
        return sorted(set(names))

    def _resolve_callable_signature_target(self, func):
        """Return the callable whose signature describes ``func``'s arguments."""
        target = func
        try:
            from ..tools.base import BaseTool
            if isinstance(func, BaseTool):
                return func.run
        except ImportError:
            pass
        if inspect.isclass(func):
            run = getattr(func, 'run', None) or getattr(func, '_run', None)
            if run is not None:
                target = run
        return target

    def _is_argument_binding_error(self, func, arguments) -> bool:
        """True only when ``arguments`` cannot bind to ``func``'s signature.

        Distinguishes a genuine call-boundary failure (wrong/missing/extra
        kwargs) from a ``TypeError``/``ValueError`` raised *inside* a
        successfully-bound tool during its own domain logic. Only the former
        should receive a parameter-schema hint; the latter is a runtime error
        the model must fix by changing the value, not the parameter names.
        """
        target = self._resolve_callable_signature_target(func)
        try:
            sig = inspect.signature(target)
        except (TypeError, ValueError):
            return False
        try:
            sig.bind(**(arguments or {}))
        except TypeError:
            return True
        return False

    def _tool_parameter_hint(self, func):
        """Return {'required': [...], 'optional': [...]} for a callable tool."""
        target = func
        try:
            from ..tools.base import BaseTool
            if isinstance(func, BaseTool):
                target = func.run
            elif inspect.isclass(func):
                target = getattr(func, 'run', None) or getattr(func, '_run', None)
            if target is None or not callable(target):
                return None
            sig = inspect.signature(target)
            required, optional = [], []
            for pname, param in sig.parameters.items():
                if pname == 'self' or param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
                else:
                    optional.append(pname)
            if not required and not optional:
                return None
            return {"required": required, "optional": optional}
        except (ValueError, TypeError):
            return None

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
            tool_name_attr = getattr(tool, '__name__', None) or getattr(tool, 'name', None)
            tool_policy = getattr(tool, 'retry_policy', None) if hasattr(tool, 'retry_policy') else None
            if tool_name_attr == tool_name and tool_policy is not None:
                return tool_policy
        
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
            elif ("rate" in error_msg and "limit" in error_msg) or "too many requests" in error_msg:
                return "rate_limit"
            elif "connection" in error_msg or "network" in error_msg:
                return "connection_error"
        
        # Check exception type
        if exception:
            exc_msg = str(exception).lower()
            exc_type = type(exception).__name__.lower()
            
            if "timeout" in exc_msg or "timeout" in exc_type:
                return "timeout"
            elif ("rate" in exc_msg and "limit" in exc_msg) or "too many requests" in exc_msg:
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
