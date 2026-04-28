"""
Chat and LLM interaction mixin for the Agent class.

Contains all methods for chat completion, streaming, message building,
and response processing. Extracted from agent.py for maintainability.
"""

import os
import re
import time
import json
import logging
from praisonaiagents._logging import get_logger
import asyncio
import threading
from ..errors import BudgetExceededError

# Fallback helpers to avoid circular imports
def _get_console():
    from rich.console import Console
    return Console

def _get_live():
    from rich.live import Live
    return Live

def _get_display_functions():
    from ..main import (
        display_error, display_instruction, display_interaction,
        display_generating, display_self_reflection, ReflectionOutput,
        adisplay_instruction, execute_sync_callback
    )
    return {
        'display_error': display_error,
        'display_instruction': display_instruction,
        'display_interaction': display_interaction,
        'display_generating': display_generating,
        'display_self_reflection': display_self_reflection,
        'ReflectionOutput': ReflectionOutput,
        'adisplay_instruction': adisplay_instruction,
        'execute_sync_callback': execute_sync_callback,
    }

logger = logging.getLogger(__name__)



import traceback
from typing import List, Optional, Any, Dict, Union, Callable, Generator, TYPE_CHECKING
from collections import OrderedDict

if TYPE_CHECKING:
    pass


class ChatMixin:
    """Mixin providing chat methods for the Agent class."""

    def _build_system_prompt(self, tools=None):
        """Build the system prompt with tool information.
        
        Args:
            tools: Optional list of tools to use (defaults to self.tools)
            
        Returns:
            str: The system prompt or None if use_system_prompt is False
        """
        if not self.use_system_prompt:
            return None
        
        # Check cache first (skip cache if memory is enabled since context is dynamic)
        if not self._memory_instance:
            tools_key = self._get_tools_cache_key(tools)
            cache_key = f"{self.role}:{self.goal}:{tools_key}"
            
            cached_prompt = self._cache_get(self._system_prompt_cache, cache_key)
            if cached_prompt is not None:
                return cached_prompt
        else:
            cache_key = None  # Don't cache when memory is enabled
            
        system_prompt = f"""{self.backstory}\n
Your Role: {self.role}\n
Your Goal: {self.goal}"""
        
        # Add rules context if rules manager is enabled (lazy initialization)
        if self._rules_manager_initialized and self._rules_manager:
            rules_context = self.get_rules_context()
            if rules_context:
                system_prompt += f"\n\n## Rules (Guidelines you must follow)\n{rules_context}"
        
        # Add memory context if memory is enabled
        if self._memory_instance:
            memory_context = self.get_memory_context()
            if memory_context:
                system_prompt += f"\n\n## Memory (Information you remember about the user)\n{memory_context}"
                # Display memory info to user if verbose
                if self.verbose:
                    self._display_memory_info()
            
            # Add learn context if learn is enabled (auto-inject when memory="learn")
            learn_context = self.get_learn_context()
            if learn_context:
                system_prompt += f"\n\n## Learned Context (Patterns and insights from past interactions)\n{learn_context}"
        
        # Add skills prompt if skills are configured
        if self._skills or self._skills_dirs:
            skills_prompt = self.get_skills_prompt()
            if skills_prompt:
                system_prompt += f"\n\n## Available Skills\n{skills_prompt}"
                system_prompt += "\n\nWhen a skill is relevant to the task, read its SKILL.md file to get detailed instructions. If the skill has scripts in its scripts/ directory, you can execute them using the execute_code or run_script tool."
        
        # Add tool usage instructions if tools are available
        # Use provided tools or fall back to self.tools
        tools_to_use = tools if tools is not None else self.tools
        if tools_to_use:
            tool_names = []
            for tool in tools_to_use:
                try:
                    if callable(tool) and hasattr(tool, '__name__'):
                        tool_names.append(tool.__name__)
                    elif isinstance(tool, dict) and isinstance(tool.get('function'), dict) and 'name' in tool['function']:
                        tool_names.append(tool['function']['name'])
                    elif isinstance(tool, str):
                        tool_names.append(tool)
                    elif hasattr(tool, "to_openai_tool"):
                        # Handle MCP tools
                        openai_tools = tool.to_openai_tool()
                        if isinstance(openai_tools, list):
                            for t in openai_tools:
                                if isinstance(t, dict) and 'function' in t and 'name' in t['function']:
                                    tool_names.append(t['function']['name'])
                        elif isinstance(openai_tools, dict) and 'function' in openai_tools:
                            tool_names.append(openai_tools['function']['name'])
                except (AttributeError, KeyError, TypeError) as e:
                    logging.warning(f"Could not extract tool name from {tool}: {e}")
                    continue
            
            if tool_names:
                system_prompt += f"\n\nYou have access to the following tools: {', '.join(tool_names)}. Use these tools when appropriate to help complete your tasks. Always use tools when they can help provide accurate information or perform actions."
                system_prompt += "\n\nExplain Before Acting: Before calling a tool, provide a brief one-sentence explanation of what you are about to do and why. Skip explanations only for repetitive low-level operations where narration would be noisy. When performing a batch of similar operations (e.g. searching for multiple items), explain the group once rather than narrating each call individually."
        
        # Cache the generated system prompt (only if cache_key is set, i.e., memory not enabled)
        # Use LRU eviction to prevent unbounded growth
        if cache_key:
            self._cache_put(self._system_prompt_cache, cache_key, system_prompt)
        return system_prompt

    def _build_response_format(self, schema_model):
        """Build response_format dict for native structured output.
        
        Args:
            schema_model: Pydantic model or dict schema
            
        Returns:
            Dict suitable for response_format parameter, or None if not applicable
        """
        if not schema_model:
            return None
        
        def _add_additional_properties_false(schema):
            """Recursively add additionalProperties: false and required array to all object schemas."""
            if isinstance(schema, dict):
                if schema.get('type') == 'object':
                    schema['additionalProperties'] = False
                    # Add required array with all property keys (OpenAI strict mode requirement)
                    if 'properties' in schema:
                        schema['required'] = list(schema['properties'].keys())
                # Recurse into properties
                if 'properties' in schema:
                    for prop in schema['properties'].values():
                        _add_additional_properties_false(prop)
                # Recurse into items (for arrays)
                if 'items' in schema:
                    _add_additional_properties_false(schema['items'])
                # Recurse into $defs
                if '$defs' in schema:
                    for def_schema in schema['$defs'].values():
                        _add_additional_properties_false(def_schema)
            return schema
        
        def _wrap_array_in_object(schema):
            """Wrap array schema in object since OpenAI requires root type to be object."""
            if schema.get('type') == 'array':
                return {
                    'type': 'object',
                    'properties': {
                        'items': schema
                    },
                    'required': ['items'],
                    'additionalProperties': False
                }
            return schema
        
        # Handle Pydantic model
        if hasattr(schema_model, 'model_json_schema'):
            schema = schema_model.model_json_schema()
            schema = _add_additional_properties_false(schema)
            schema = _wrap_array_in_object(schema)
            name = getattr(schema_model, '__name__', 'response')
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": name,
                    "schema": schema,
                    "strict": True
                }
            }
        
        # Handle dict schema (inline JSON schema from YAML)
        if isinstance(schema_model, dict):
            schema = schema_model.copy()
            schema = _add_additional_properties_false(schema)
            schema = _wrap_array_in_object(schema)
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": schema,
                    "strict": True
                }
            }
        
        return None

    def _supports_native_structured_output(self):
        """Check if current model supports native structured output via response_format.
        
        Auto-detects based on model capabilities using LiteLLM.
        
        Returns:
            bool: True if model supports response_format with json_schema
        """
        try:
            from ..llm.model_capabilities import supports_structured_outputs
        except ImportError:
            return False  # Module genuinely not available — acceptable

        try:
            return supports_structured_outputs(self.llm)
        except Exception as e:
            logging.warning(
                "Structured output capability check failed for agent %s (model=%r); "
                "falling back to prompt-based schema formatting. Check model capability "
                "configuration and optional provider dependencies: %s",
                getattr(self, "name", "<unknown>"),
                self.llm,
                e,
                exc_info=True,
            )
            return False

    def _build_messages(self, prompt, temperature=1.0, output_json=None, output_pydantic=None, tools=None, use_native_format=False):
        """Build messages list for chat completion.
        
        Args:
            prompt: The user prompt (str or list)
            temperature: Temperature for the chat
            output_json: Optional Pydantic model for JSON output
            output_pydantic: Optional Pydantic model for JSON output (alias)
            tools: Optional list of tools to use (defaults to self.tools)
            use_native_format: If True, skip text injection (native response_format will be used)
            
        Returns:
            Tuple of (messages list, original prompt)
        """
        messages = []
        original_prompt = None
        
        # Use openai_client's build_messages method if available
        if self._openai_client is not None:
            messages, original_prompt = self._openai_client.build_messages(
                prompt=prompt,
                system_prompt=self._build_system_prompt(
                    tools=tools,
                ),
                chat_history=self.chat_history,
                output_json=None if use_native_format else output_json,
                output_pydantic=None if use_native_format else output_pydantic
            )
        else:
            # Build messages manually
            system_prompt = self._build_system_prompt(
                tools=tools,
            )
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Inject session history if enabled (from persistent storage)
            if self._history_enabled and self._session_store is not None:
                try:
                    session_history = self._session_store.get_chat_history(
                        self._history_session_id,
                        max_messages=self._history_limit
                    )
                    if session_history:
                        messages.extend(session_history)
                except Exception as e:
                    logging.debug(f"Failed to load session history: {e}")
            
            # Add in-memory chat history (current conversation)
            if self.chat_history:
                messages.extend(self.chat_history)
            
            # Add user prompt
            if isinstance(prompt, list):
                messages.extend(prompt)
                original_prompt = prompt
            else:
                messages.append({"role": "user", "content": str(prompt)})
                original_prompt = str(prompt)
            
            # Add JSON format instruction if needed (only when not using native format)
            if not use_native_format and (output_json or output_pydantic):
                schema_model = output_pydantic or output_json
                # Handle Pydantic model
                if hasattr(schema_model, 'model_json_schema'):
                    import json
                    json_instruction = f"\nPlease respond with valid JSON matching this schema: {json.dumps(schema_model.model_json_schema())}"
                    messages[-1]["content"] += json_instruction
                # Handle inline dict schema (Option A from YAML)
                elif isinstance(schema_model, dict):
                    import json
                    json_instruction = f"\nPlease respond with valid JSON matching this schema: {json.dumps(schema_model)}"
                    messages[-1]["content"] += json_instruction
        
        return messages, original_prompt

    def _format_tools_for_completion(self, tools=None):
        """Format tools for OpenAI completion API.
        
        Supports:
        - Pre-formatted OpenAI tools (dicts with type='function')
        - Lists of pre-formatted tools
        - Callable functions
        - String function names
        - Objects with to_openai_tool() method
        
        Args:
            tools: List of tools in various formats or None to use self.tools
            
        Returns:
            List of formatted tools or empty list
        """
        if tools is None:
            tools = self.tools
        
        if not tools:
            return []
        
        # Check cache first
        tools_key = self._get_tools_cache_key(tools)
        cached_tools = self._cache_get(self._formatted_tools_cache, tools_key)
        if cached_tools is not None:
            return cached_tools
            
        formatted_tools = []
        for tool in tools:
            # Handle pre-formatted OpenAI tools
            if isinstance(tool, dict) and tool.get('type') == 'function':
                # Validate nested dictionary structure before accessing
                if 'function' in tool and isinstance(tool['function'], dict) and 'name' in tool['function']:
                    formatted_tools.append(tool)
                else:
                    logging.warning(f"Skipping malformed OpenAI tool: missing function or name")
            # Handle lists of tools
            elif isinstance(tool, list):
                for subtool in tool:
                    if isinstance(subtool, dict) and subtool.get('type') == 'function':
                        # Validate nested dictionary structure before accessing
                        if 'function' in subtool and isinstance(subtool['function'], dict) and 'name' in subtool['function']:
                            formatted_tools.append(subtool)
                        else:
                            logging.warning(f"Skipping malformed OpenAI tool in list: missing function or name")
            # Handle string tool names
            elif isinstance(tool, str):
                tool_def = self._generate_tool_definition(tool)
                if tool_def:
                    formatted_tools.append(tool_def)
                else:
                    logging.warning(f"Could not generate definition for tool: {tool}")
            # Handle objects with to_openai_tool method (MCP tools)
            elif hasattr(tool, "to_openai_tool"):
                openai_tools = tool.to_openai_tool()
                # MCP tools can return either a single tool or a list of tools
                if isinstance(openai_tools, list):
                    formatted_tools.extend(openai_tools)
                elif openai_tools is not None:
                    formatted_tools.append(openai_tools)
            # Handle callable functions
            elif callable(tool):
                tool_def = self._generate_tool_definition(tool.__name__)
                if tool_def:
                    formatted_tools.append(tool_def)
            else:
                logging.warning(f"Tool {tool} not recognized")
        
        # Validate JSON serialization before returning
        if formatted_tools:
            try:
                json.dumps(formatted_tools)  # Validate serialization
            except (TypeError, ValueError) as e:
                logging.error(f"Tools are not JSON serializable: {e}")
                return []
        
        # Cache the formatted tools with LRU eviction
        self._cache_put(self._formatted_tools_cache, tools_key, formatted_tools)
        return formatted_tools

    def _build_multimodal_prompt(
        self, 
        prompt: str, 
        attachments: Optional[List[str]] = None
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Build a multimodal prompt from text and attachments.
        
        This is a DRY helper used by chat/achat/run/arun/start/astart.
        Attachments are ephemeral - only text is stored in history.
        
        Args:
            prompt: Text query (ALWAYS stored in chat_history)
            attachments: Image/file paths for THIS turn only (NEVER stored)
            
        Returns:
            Either a string (no attachments) or multimodal message list
        """
        if not attachments:
            return prompt
        
        # Build multimodal content list
        content = [{"type": "text", "text": prompt}]
        
        for attachment in attachments:
            # Handle image files
            if isinstance(attachment, str):
                import os
                import base64
                
                if os.path.isfile(attachment):
                    # File path - read and encode
                    ext = os.path.splitext(attachment)[1].lower()
                    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                        try:
                            with open(attachment, 'rb') as f:
                                data = base64.b64encode(f.read()).decode('utf-8')
                            media_type = {
                                '.jpg': 'image/jpeg',
                                '.jpeg': 'image/jpeg',
                                '.png': 'image/png',
                                '.gif': 'image/gif',
                                '.webp': 'image/webp',
                            }.get(ext, 'image/jpeg')
                            content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{data}"}
                            })
                            logging.debug(f"Successfully encoded image attachment: {attachment} ({len(data)} bytes base64)")
                        except Exception as e:
                            logging.warning(f"Failed to load attachment {attachment}: {e}")
                elif attachment.startswith(('http://', 'https://', 'data:')):
                    # URL or data URI
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": attachment}
                    })
            elif isinstance(attachment, dict):
                # Already structured content
                content.append(attachment)
        
        return content

    def _extract_llm_response_content(self, response) -> Optional[str]:
        """Return assistant message text, a tool-call summary, or str(response) as fallback."""
        if not response:
            return None
        try:
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                msg = getattr(choice, "message", None)
                if msg is not None:
                    content = getattr(msg, "content", None)
                    if content:
                        return content
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if tool_calls:
                        names = [getattr(tc.function, "name", "?") for tc in tool_calls]
                        return f"[tool_calls: {', '.join(names)}]"
        except (AttributeError, IndexError, TypeError) as e:
            logging.warning(
                f"Failed to extract LLM response content (falling back to str): {e}"
            )
            # Fallback to str(response) is still fine, but now it's visible
        return str(response)

    def _process_stream_response(self, messages, temperature, start_time, formatted_tools=None, reasoning_steps=False):
        """Internal helper for streaming response processing with real-time events."""
        if self._openai_client is None:
            return None
            
        return self._openai_client.process_stream_response(
            messages=messages,
            model=self.llm,
            temperature=temperature,
            tools=formatted_tools,
            start_time=start_time,
            console=self.console,
            display_fn=_get_display_functions()['display_generating'] if self.verbose else None,
            reasoning_steps=reasoning_steps,
            stream_callback=self.stream_emitter.emit,
            emit_events=True
        )

    def _chat_completion(self, messages, temperature=1.0, tools=None, stream=True, reasoning_steps=False, task_name=None, task_description=None, task_id=None, response_format=None, _retry_depth=0):
        start_time = time.time()

        # --- Context compaction (opt-in via ExecutionConfig.context_compaction) ---
        # Compacts message history before sending to LLM. Zero overhead when disabled.
        _execution_cfg = getattr(self, 'execution', None)
        if _execution_cfg and getattr(_execution_cfg, 'context_compaction', False):
            try:
                from ..compaction import ContextCompactor
                from ..hooks import HookEvent as _HookEvent
                _max_tok = getattr(_execution_cfg, 'max_context_tokens', None) or 8000
                _compactor = ContextCompactor(max_tokens=_max_tok)
                if _compactor.needs_compaction(messages):
                    try:
                        self._hook_runner.execute_sync(_HookEvent.BEFORE_COMPACTION, None)
                    except Exception as e:
                        logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
                        if getattr(self, '_strict_hooks', False):
                            raise
                    compacted_msgs, _cr = _compactor.compact(messages)
                    messages[:] = compacted_msgs  # in-place update so callers see the change
                    logging.info(
                        f"[compaction] {self.name}: {_cr.original_tokens}→{_cr.compacted_tokens} tokens "
                        f"({_cr.messages_removed} messages removed)"
                    )
                    try:
                        self._hook_runner.execute_sync(_HookEvent.AFTER_COMPACTION, None)
                    except Exception as e:
                        logging.warning(f"AFTER_COMPACTION hook failed: {e}")
                        if getattr(self, '_strict_hooks', False):
                            raise
            except Exception as _ce:
                if getattr(self, '_strict_hooks', False):
                    raise
                logging.debug(f"[compaction] skipped (non-fatal): {_ce}")

        # Trigger BEFORE_LLM hook
        from ..hooks import HookEvent, BeforeLLMInput
        before_llm_input = BeforeLLMInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_LLM,
            timestamp=str(time.time()),
            agent_name=self.name,
            messages=messages,
            model=self.llm if isinstance(self.llm, str) else str(self.llm),
            temperature=temperature
        )
        self._hook_runner.execute_sync(HookEvent.BEFORE_LLM, before_llm_input)
        
        logging.debug(f"{self.name} sending messages to LLM: {messages}")
        
        # Emit LLM request trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.llm_request(
            self.name,
            messages_count=len(messages),
            tokens_used=0,  # Estimated before call
            model=self.llm if isinstance(self.llm, str) else None,
            messages=messages,  # Include full messages for context replay
        )

        # Use the new _format_tools_for_completion helper method
        formatted_tools = self._format_tools_for_completion(tools)

        try:
            # NEW: Unified protocol dispatch path (Issue #1304, #1362)
            # UNIFIED: Single protocol-driven dispatch path (fixes DRY violation)
            # All LLM providers now go through unified dispatcher for consistency and maintainability
            stream_callback = self.stream_emitter.emit if hasattr(self, 'stream_emitter') else None
            final_response = self._execute_unified_chat_completion(
                messages=messages,
                temperature=temperature,
                tools=formatted_tools,
                stream=stream,
                reasoning_steps=reasoning_steps,
                task_name=task_name,
                task_description=task_description,
                task_id=task_id,
                response_format=response_format,
                stream_callback=stream_callback,
                emit_events=True,
            )

            # Emit LLM response trace event with token usage
            _duration_ms = (time.time() - start_time) * 1000
            _prompt_tokens = 0
            _completion_tokens = 0
            _cost_usd = 0.0
            
            # Extract token usage from response if available
            if final_response:
                _usage = getattr(final_response, 'usage', None)
                if _usage:
                    _prompt_tokens = getattr(_usage, 'prompt_tokens', 0) or 0
                    _completion_tokens = getattr(_usage, 'completion_tokens', 0) or 0
                    # Calculate cost using litellm (if available) or fallback pricing
                    _cost_usd = self._calculate_llm_cost(_prompt_tokens, _completion_tokens, response=final_response)
            
            _trace_emitter.llm_response(
                self.name,
                duration_ms=_duration_ms,
                response_content=self._extract_llm_response_content(final_response),
                prompt_tokens=_prompt_tokens,
                completion_tokens=_completion_tokens,
                cost_usd=_cost_usd,
            )

            # Budget tracking & enforcement (zero overhead when _max_budget is None)
            # Thread-safe cost tracking (Gap 1a fix)
            with self._cost_lock:
                self._total_cost += _cost_usd
                self._total_tokens_in += _prompt_tokens
                self._total_tokens_out += _completion_tokens
                self._llm_call_count += 1
                budget_exceeded = self._max_budget and self._total_cost >= self._max_budget
                current_cost = self._total_cost
            
            if budget_exceeded:
                if self._on_budget_exceeded == "stop":
                    raise BudgetExceededError(
                        f"Agent '{self.name}' exceeded budget: ${current_cost:.4f} >= ${self._max_budget:.4f}",
                        budget_type="cost",
                        limit=self._max_budget,
                        used=current_cost,
                        agent_id=self.name
                    )
                elif self._on_budget_exceeded == "warn":
                    logging.warning(
                        f"[budget] {self.name}: ${current_cost:.4f} exceeded "
                        f"${self._max_budget:.4f} budget"
                    )
                elif callable(self._on_budget_exceeded):
                    self._on_budget_exceeded(current_cost, self._max_budget)
            
            # Trigger AFTER_LLM hook
            from ..hooks import HookEvent, AfterLLMInput
            after_llm_input = AfterLLMInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.AFTER_LLM,
                timestamp=str(time.time()),
                agent_name=self.name,
                messages=messages,
                response=str(final_response),
                model=self.llm if isinstance(self.llm, str) else str(self.llm),
                latency_ms=(time.time() - start_time) * 1000
            )
            self._hook_runner.execute_sync(HookEvent.AFTER_LLM, after_llm_input)
            
            return final_response

        except BudgetExceededError:
            raise
        except Exception as e:
            from ..errors import LLMError
            error_str = str(e).lower()
            
            # Check if this is a context overflow error
            context_overflow_phrases = [
                "maximum context length",
                "context window is too long", 
                "context length exceeded",
                "context_length_exceeded",
                "token limit",
                "too many tokens"
            ]
            is_overflow = any(phrase in error_str for phrase in context_overflow_phrases)
            
            if is_overflow and self.context_manager:
                # Attempt overflow recovery with emergency truncation
                logging.warning(f"[{self.name}] Context overflow detected, attempting recovery...")
                try:
                    from ..context.budgeter import get_model_limit
                    from ..context.tokens import estimate_messages_tokens
                    
                    model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
                    model_limit = get_model_limit(model_name)
                    target = int(model_limit * 0.7)  # Target 70% of limit for safety
                    
                    # Apply emergency truncation
                    truncated_messages = self.context_manager.emergency_truncate(messages, target)
                    
                    logging.info(
                        f"[{self.name}] Emergency truncation: {estimate_messages_tokens(messages)} -> "
                        f"{estimate_messages_tokens(truncated_messages)} tokens"
                    )
                    
                    # Retry with truncated messages (recursive call with depth limit)
                    if _retry_depth < 2:
                        return self._chat_completion(
                            truncated_messages, temperature, tools, stream, 
                            reasoning_steps, task_name, task_description, task_id, response_format, 
                            _retry_depth=_retry_depth + 1
                        )
                    else:
                        logging.error(f"[{self.name}] Context overflow retry limit exceeded")
                        raise LLMError(
                            f"Context overflow could not be resolved after {_retry_depth} attempts", 
                            model_name=model_name, agent_id=self.name, is_retryable=False
                        ) from e
                except LLMError:
                    # Re-raise LLMError (including depth limit errors) without swallowing
                    raise
                except Exception as recovery_error:
                    logging.error(f"[{self.name}] Overflow recovery failed: {recovery_error}")
            
            # Emit LLM response trace event on error
            _duration_ms = (time.time() - start_time) * 1000
            _trace_emitter.llm_response(
                self.name,
                duration_ms=_duration_ms,
                finish_reason="error",
                response_content=str(e),  # Include error for context replay
            )
            
            # Classify and raise structured error with improved transient failure detection
            model_name = self.llm if isinstance(self.llm, str) else "unknown"
            session_id = getattr(self, '_session_id', 'unknown')
            
            # Check for retryable errors (rate limits, transient network issues, provider errors)
            retryable_indicators = [
                "rate limit", "429", "too many requests",
                "timeout", "connection reset", "connection error", "socket error",
                "500", "502", "503", "504", "service unavailable", "internal server error",
                "dns", "network", "connection refused"
            ]
            
            # Check for non-retryable errors (auth issues)
            auth_indicators = ["401", "403", "authentication", "unauthorized", "invalid_api_key"]
            
            if any(phrase in error_str.lower() for phrase in retryable_indicators):
                is_retryable = True
            elif any(phrase in error_str.lower() for phrase in auth_indicators):
                is_retryable = False
            else:
                # Default to retryable for unknown errors to be more resilient
                is_retryable = True
            
            # Create LLMError with contextual metadata
            error = LLMError(
                str(e), 
                model_name=model_name, 
                agent_id=self.name, 
                is_retryable=is_retryable,
                session_id=session_id
            )
            
            # Call error hook if available for error interception
            if hasattr(self, 'on_error') and self.on_error:
                try:
                    self.on_error(error)
                except Exception as hook_error:
                    logging.debug(f"Error in on_error hook: {hook_error}")
            
            raise error from e

    def _execute_unified_chat_completion(
        self, 
        messages, 
        temperature=1.0, 
        tools=None, 
        stream=True,
        reasoning_steps=False,
        task_name=None,
        task_description=None,
        task_id=None,
        response_format=None,
        stream_callback=None,
        emit_events=True,
    ):
        """
        Execute unified chat completion using composition instead of runtime class mutation.
        
        This method provides the same functionality as UnifiedChatMixin but uses
        composition for safety and maintainability.
        """
        from ..llm import create_llm_dispatcher
        
        # Get or create unified dispatcher
        if not hasattr(self, '_unified_dispatcher') or self._unified_dispatcher is None:
            # Provider selection based on existing agent configuration
            if self._using_custom_llm and hasattr(self, 'llm_instance'):
                dispatcher = create_llm_dispatcher(llm_instance=self.llm_instance)
            else:
                # Initialize OpenAI client if not present
                if not hasattr(self, '_openai_client') or self._openai_client is None:
                    from ..llm import get_openai_client
                    self._openai_client = get_openai_client(api_key=getattr(self, 'api_key', None))
                dispatcher = create_llm_dispatcher(openai_client=self._openai_client, model=self.llm)
            
            # Cache the dispatcher
            self._unified_dispatcher = dispatcher
        
        # Execute unified dispatch with all necessary parameters
        # Includes all parameters from both legacy paths to ensure full compatibility
        try:
            if stream_callback is None and hasattr(self, 'stream_emitter'):
                stream_callback = getattr(self.stream_emitter, 'emit', None)
            final_response = self._unified_dispatcher.chat_completion(
                messages=messages,
                tools=tools,
                tool_choice=getattr(self, 'tool_choice', None),
                temperature=temperature,
                max_tokens=getattr(self, 'max_tokens', None),
                stream=stream,
                response_format=response_format,
                execute_tool_fn=getattr(self, 'execute_tool', None),
                console=self.console if (self.verbose or stream) else None,
                display_fn=self._display_generating if self.verbose else None,
                stream_callback=stream_callback,
                emit_events=emit_events,
                verbose=self.verbose,
                max_iterations=10,
                reasoning_steps=reasoning_steps,
                task_name=task_name,
                task_description=task_description,
                task_id=task_id,
                # Additional parameters from legacy custom LLM path
                markdown=self.markdown,
                agent_name=self.name,
                agent_role=self.role,
                agent_tools=(
                    [
                        t["function"]["name"]
                        if isinstance(t, dict)
                        and isinstance(t.get("function"), dict)
                        and "name" in t["function"]
                        else getattr(t, "__name__", str(t))
                        for t in (tools if tools is not None else self.tools or [])
                    ]
                    or None
                ),
            )
            return final_response
            
        except Exception as e:
            logging.error(f"Unified chat completion failed: {e}")
            raise

    async def _execute_unified_achat_completion(
        self, 
        messages, 
        temperature=1.0, 
        tools=None, 
        stream=True,
        reasoning_steps=False,
        task_name=None,
        task_description=None,
        task_id=None,
        response_format=None,
        stream_callback=None,
        emit_events=True,
    ):
        """
        Execute unified async chat completion using composition instead of runtime class mutation.
        
        This method provides the same functionality as UnifiedChatMixin but uses
        composition for safety and maintainability.
        """
        from ..llm import create_llm_dispatcher
        
        # Get or create unified dispatcher
        if not hasattr(self, '_unified_dispatcher') or self._unified_dispatcher is None:
            # Provider selection based on existing agent configuration
            if self._using_custom_llm and hasattr(self, 'llm_instance'):
                dispatcher = create_llm_dispatcher(llm_instance=self.llm_instance)
            else:
                # Initialize OpenAI client if not present
                if not hasattr(self, '_openai_client') or self._openai_client is None:
                    from ..llm import get_openai_client
                    self._openai_client = get_openai_client(api_key=getattr(self, 'api_key', None))
                dispatcher = create_llm_dispatcher(openai_client=self._openai_client, model=self.llm)
            
            # Cache the dispatcher
            self._unified_dispatcher = dispatcher
        
        # Execute unified async dispatch with all necessary parameters
        # Includes all parameters from both legacy paths to ensure full compatibility
        try:
            if stream_callback is None and hasattr(self, 'stream_emitter'):
                stream_callback = getattr(self.stream_emitter, 'emit', None)
            final_response = await self._unified_dispatcher.achat_completion(
                messages=messages,
                tools=tools,
                tool_choice=getattr(self, 'tool_choice', None),
                temperature=temperature,
                max_tokens=getattr(self, 'max_tokens', None),
                stream=stream,
                response_format=response_format,
                execute_tool_fn=getattr(self, 'execute_tool', None),
                console=self.console if (self.verbose or stream) else None,
                display_fn=self._display_generating if self.verbose else None,
                stream_callback=stream_callback,
                emit_events=emit_events,
                verbose=self.verbose,
                max_iterations=10,
                reasoning_steps=reasoning_steps,
                task_name=task_name,
                task_description=task_description,
                task_id=task_id,
                # Additional parameters from legacy custom LLM path
                markdown=self.markdown,
                agent_name=self.name,
                agent_role=self.role,
                agent_tools=(
                    [
                        t["function"]["name"]
                        if isinstance(t, dict)
                        and isinstance(t.get("function"), dict)
                        and "name" in t["function"]
                        else getattr(t, "__name__", str(t))
                        for t in (tools if tools is not None else self.tools or [])
                    ]
                    or None
                ),
            )
            return final_response
            
        except Exception as e:
            logging.error(f"Unified async chat completion failed: {e}")
            raise

    def _execute_callback_and_display(self, prompt: str, response: str, generation_time: float, task_name=None, task_description=None, task_id=None):
        """Helper method to execute callbacks and display interaction.
        
        This centralizes the logic for callback execution and display to avoid duplication.
        """
        # Always execute callbacks for status/trace output (regardless of LLM backend)
        _get_display_functions()['execute_sync_callback'](
            'interaction',
            message=prompt,
            response=response,
            markdown=self.markdown,
            generation_time=generation_time,
            agent_name=self.name,
            agent_role=self.role,
            agent_tools=[getattr(t, '__name__', str(t)) for t in self.tools] if self.tools else None,
            task_name=task_name,
            task_description=task_description, 
            task_id=task_id
        )
        # Always display final interaction when verbose is True to ensure consistent formatting
        # This ensures both OpenAI and custom LLM providers (like Gemini) show formatted output
        if self.verbose and not self._final_display_shown:
            _get_display_functions()['display_interaction'](prompt, response, markdown=self.markdown, 
                              generation_time=generation_time, console=self.console,
                              agent_name=self.name,
                              agent_role=self.role,
                              agent_tools=(
                    [
                        t["function"]["name"]
                        if isinstance(t, dict)
                        and isinstance(t.get("function"), dict)
                        and "name" in t["function"]
                        else getattr(t, "__name__", str(t))
                        for t in (tools if tools is not None else self.tools or [])
                    ]
                    or None
                ),
                              task_name=None,  # Not available in this context
                              task_description=None,  # Not available in this context
                              task_id=None)  # Not available in this context
            self._final_display_shown = True

    def _display_generating(self, content: str, start_time: float):
        """Display function for generating animation with agent info."""
        from rich.panel import Panel
        from rich.markdown import Markdown
        elapsed = time.time() - start_time
        
        # Show content if provided (for both streaming and progressive display)
        if content:
            display_content = Markdown(content) if self.markdown else content
            return Panel(
                display_content,
                title=f"[bold]{self.name}[/bold] - Generating... {elapsed:.1f}s",
                border_style="green",
                expand=False
            )

    def _apply_context_management(
        self,
        messages: list,
        system_prompt: str = "",
        tools: list = None,
    ) -> tuple:
        """
        Apply context management before LLM call.
        
        Handles auto-compaction when context exceeds threshold.
        Zero overhead when context=False.
        
        Args:
            messages: Current chat history
            system_prompt: System prompt content
            tools: Tool schemas
            
        Returns:
            Tuple of (processed_messages, context_result_dict)
            context_result_dict contains optimization metadata if applied
        """
        # Fast path: no context management
        if not self.context_manager:
            return messages, None
        
        try:
            # Process through context manager
            result = self.context_manager.process(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools or [],
                trigger="turn",
            )
            
            optimized = result.get("messages", messages)
            
            # Log if optimization occurred
            if result.get("optimized"):
                logging.debug(
                    f"[{self.name}] Context optimized: "
                    f"{result.get('tokens_before', 0)} -> {result.get('tokens_after', 0)} tokens "
                    f"(saved {result.get('tokens_saved', 0)})"
                )
            
            # HARD LIMIT CHECK: If still over model limit, apply emergency truncation
            try:
                from ..context.budgeter import get_model_limit
                from ..context.tokens import estimate_messages_tokens
                
                model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
                model_limit = get_model_limit(model_name)
                current_tokens = estimate_messages_tokens(optimized)
                
                # If over 95% of limit, apply emergency truncation
                if current_tokens > model_limit * 0.95:
                    logging.warning(
                        f"[{self.name}] Context at {current_tokens} tokens (limit: {model_limit}), "
                        f"applying emergency truncation"
                    )
                    target = int(model_limit * 0.8)  # Target 80% of limit
                    optimized = self.context_manager.emergency_truncate(optimized, target)
                    result["emergency_truncated"] = True
                    result["tokens_after"] = estimate_messages_tokens(optimized)
            except Exception as e:
                logging.debug(f"Hard limit check skipped: {e}")
            
            return optimized, result
            
        except Exception as e:
            # Context management should never break the chat flow
            logging.warning(f"Context management error (continuing without): {e}")
            return messages, None

    def _truncate_tool_output(self, tool_name: str, output: str) -> str:
        """
        Truncate tool output according to configured budget.
        
        Zero overhead when context=False.
        
        Args:
            tool_name: Name of the tool
            output: Raw tool output
            
        Returns:
            Truncated output if over budget, otherwise original
        """
        if not self.context_manager:
            return output
        
        try:
            return self.context_manager.truncate_tool_output(tool_name, output)
        except Exception as e:
            logging.warning(f"Tool output truncation error: {e}")
            return output

    def _resolve_skill_invocation(self, prompt):
        """If ``prompt`` is ``/skill-name [args]``, render the skill body.

        Returns:
            The rendered prompt when a user-invocable skill matches, else
            the original ``prompt`` unchanged. Non-string prompts (e.g.
            multimodal lists) are returned as-is.
        """
        if not isinstance(prompt, str):
            return prompt
        text = prompt.lstrip()
        if not text.startswith("/"):
            return prompt
        # Avoid path-like "/usr/..." inputs
        head = text[1:].split(None, 1)
        if not head:
            return prompt
        name = head[0]
        args = head[1] if len(head) > 1 else ""
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            return prompt
        mgr = getattr(self, "skill_manager", None)
        if mgr is None:
            return prompt
        rendered = mgr.invoke(name, raw_args=args)
        if rendered is None:
            return prompt
        # G-A fix: Best-effort pre-approve any tools declared under
        # `allowed-tools` in the skill frontmatter. Non-fatal on error.
        try:
            tool_names = mgr.get_allowed_tools(name)
            if tool_names:
                from ..approval import get_approval_registry

                registry = get_approval_registry()
                agent_name = getattr(self, "display_name", getattr(self, "name", None))
                if agent_name:  # Only approve if we have a stable agent identifier
                    for _tn in tool_names:
                        try:
                            registry.auto_approve_tool(_tn, agent_name=agent_name)
                        except Exception as exc:  # pragma: no cover - approval is optional
                            logging.debug(
                                "Failed to auto-approve skill tool '%s' for skill '%s' on agent '%s': %s. "
                                "The skill will continue, but this tool may still require explicit approval.",
                                _tn,
                                name,
                                agent_name,
                                exc,
                                exc_info=True,
                            )
        except Exception as exc:  # pragma: no cover - approval is optional
            logging.debug(
                "Failed to resolve allowed tools for skill '%s' on agent '%s': %s. "
                "The skill will continue without pre-approving tools.",
                name,
                getattr(self, "name", None),
                exc,
                exc_info=True,
            )
        return rendered

    def chat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None, output_json: Optional[Any] = None, output_pydantic: Optional[Any] = None, reasoning_steps: bool = False, stream: Optional[bool] = None, task_name: Optional[str] = None, task_description: Optional[str] = None, task_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None, force_retrieval: bool = False, skip_retrieval: bool = False, attachments: Optional[List[str]] = None, tool_choice: Optional[str] = None) -> Optional[str]:
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
        # Slash-command invocation: /skill-name [args] renders the skill
        # body before any backend/LLM call.
        prompt = self._resolve_skill_invocation(prompt)

        # Check if external managed backend is configured
        if hasattr(self, 'backend') and self.backend is not None:
            # Extract kwargs for delegation, excluding 'self' and function locals
            delegation_kwargs = {
                'temperature': temperature,
                'tools': tools,
                'output_json': output_json,
                'output_pydantic': output_pydantic,
                'reasoning_steps': reasoning_steps,
                'stream': stream,
                'task_name': task_name,
                'task_description': task_description,
                'task_id': task_id,
                'config': config,
                'force_retrieval': force_retrieval,
                'skip_retrieval': skip_retrieval,
                'attachments': attachments,
                'tool_choice': tool_choice
            }
            return self._delegate_to_backend(prompt, **delegation_kwargs)
        
        # Emit context trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.agent_start(self.name, {"role": self.role, "goal": self.goal})
        
        try:
            return self._chat_impl(prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice)
        finally:
            _trace_emitter.agent_end(self.name)

    def _chat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None):
        """Internal chat implementation (extracted for trace wrapping)."""
        # Apply rate limiter if configured (before any LLM call)
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        
        # Process ephemeral attachments (DRY - builds multimodal prompt)
        # IMPORTANT: Original text 'prompt' is stored in history, attachments are NOT
        llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt
        
        # Apply response template if configured (DRY: TemplateConfig.response is canonical,
        # OutputConfig.template is fallback for backward compatibility)
        effective_template = self.response_template or self._output_template
        if effective_template:
            template_instruction = f"\n\nIMPORTANT: Format your response according to this template:\n{effective_template}"
            if isinstance(llm_prompt, str):
                llm_prompt = llm_prompt + template_instruction
            elif isinstance(llm_prompt, list):
                # For multimodal prompts, append to the last text content
                for i in range(len(llm_prompt) - 1, -1, -1):
                    if isinstance(llm_prompt[i], dict) and llm_prompt[i].get('type') == 'text':
                        llm_prompt[i]['text'] = llm_prompt[i]['text'] + template_instruction
                        break
        
        # Initialize DB session on first chat (lazy)
        self._init_db_session()
        
        # Initialize session store for JSON-based persistence (lazy)
        # This enables automatic session persistence when session_id is provided
        self._init_session_store()
        
        # Start a new run for this chat turn
        prompt_str = prompt if isinstance(prompt, str) else str(prompt)
        self._start_run(prompt_str)

        # Trigger BEFORE_AGENT hook
        from ..hooks import HookEvent, BeforeAgentInput
        before_agent_input = BeforeAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt_str,
            conversation_history=self.chat_history,
            tools_available=[t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
        )
        hook_results = self._hook_runner.execute_sync(HookEvent.BEFORE_AGENT, before_agent_input)
        if self._hook_runner.is_blocked(hook_results):
            logging.warning(f"Agent {self.name} execution blocked by BEFORE_AGENT hook")
            return None
        
        # Update prompt if modified by hooks
        for res in hook_results:
            if res.output and res.output.modified_data and "prompt" in res.output.modified_data:
                prompt = res.output.modified_data["prompt"]
                llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt

        # Reset the final display flag for each new conversation
        self._final_display_shown = False
        
        # Log all parameter values when in debug mode
        if get_logger().getEffectiveLevel() == logging.DEBUG:
            param_info = {
                "prompt": str(prompt)[:100] + "..." if isinstance(prompt, str) and len(str(prompt)) > 100 else str(prompt),
                "temperature": temperature,
                "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools] if tools else None,
                "output_json": str(output_json.__class__.__name__) if output_json else None,
                "output_pydantic": str(output_pydantic.__class__.__name__) if output_pydantic else None,
                "reasoning_steps": reasoning_steps,
                "agent_name": self.name,
                "agent_role": self.role,
                "agent_goal": self.goal
            }
            logging.debug(f"Agent.chat parameters: {json.dumps(param_info, indent=2, default=str)}")
        
        start_time = time.time()
        reasoning_steps = reasoning_steps or self.reasoning_steps
        # Use agent's stream setting if not explicitly provided
        if stream is None:
            stream = self.stream
        
        # Unified retrieval handling with policy-based decision
        # Uses token-aware context building (DRY - same path as RAG pipeline)
        if self._knowledge_sources or self.knowledge is not None:
            if not self._knowledge_processed:
                self._ensure_knowledge_processed()
            
            # Determine if we should retrieve based on policy
            should_retrieve = False
            if self._retrieval_config is not None:
                should_retrieve = self._retrieval_config.should_retrieve(
                    prompt if isinstance(prompt, str) else str(prompt),
                    force=force_retrieval,
                    skip=skip_retrieval
                )
            elif not skip_retrieval:
                # No config but knowledge exists - retrieve by default unless skipped
                should_retrieve = True if force_retrieval else (self.knowledge is not None)
            
            if should_retrieve and self.knowledge:
                # Use unified retrieval path with token-aware context building
                knowledge_context, _ = self._get_knowledge_context(
                    prompt if isinstance(prompt, str) else str(prompt),
                    use_rag=True  # Use RAG pipeline for token-aware context
                )
                if knowledge_context:
                    # Format with safety boundaries
                    if self._retrieval_config and self._retrieval_config.context_template:
                        formatted_context = self._retrieval_config.context_template.format(
                            context=knowledge_context
                        )
                    else:
                        formatted_context = f"<retrieved_context>\n{knowledge_context}\n</retrieved_context>"
                    
                    # Append formatted knowledge to the prompt
                    prompt = f"{prompt}\n\n{formatted_context}"

        if self._using_custom_llm:
            try:
                # Special handling for MCP tools when using provider/model format
                # Fix: Handle empty tools list properly - use self.tools if tools is None or empty
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Convert MCP tool objects to OpenAI format if needed
                if tool_param is not None:
                    MCP = None
                    try:
                        from ..mcp.mcp import MCP
                    except ImportError:
                        pass
                    if MCP is not None and isinstance(tool_param, MCP) and hasattr(tool_param, 'to_openai_tool'):
                        # Single MCP instance
                        logging.debug("Converting single MCP tool to OpenAI format")
                        openai_tool = tool_param.to_openai_tool()
                        if openai_tool:
                            # Handle both single tool and list of tools
                            if isinstance(openai_tool, list):
                                tool_param = openai_tool
                            else:
                                tool_param = [openai_tool]
                            logging.debug(f"Converted MCP tool: {tool_param}")
                    elif isinstance(tool_param, (list, tuple)):
                        # List that may contain MCP instances - convert each MCP to OpenAI format
                        converted_tools = []
                        for t in tool_param:
                            if MCP is not None and isinstance(t, MCP) and hasattr(t, 'to_openai_tool'):
                                logging.debug("Converting MCP instance in list to OpenAI format")
                                openai_tools = t.to_openai_tool()
                                if isinstance(openai_tools, list):
                                    converted_tools.extend(openai_tools)
                                elif openai_tools:
                                    converted_tools.append(openai_tools)
                            else:
                                # Keep non-MCP tools as-is
                                converted_tools.append(t)
                        tool_param = converted_tools
                        logging.debug(f"Converted {len(converted_tools)} tools from list")
                
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize prompt content for consistent chat history storage
                normalized_content = prompt
                if isinstance(prompt, list):
                    # Extract text from multimodal prompts
                    normalized_content = next((item["text"] for item in prompt if item.get("type") == "text"), "")
                
                # Add user message to chat history BEFORE LLM call so handoffs can access it
                # Use atomic check-then-act to prevent TOCTOU race conditions
                if self._add_to_chat_history_if_not_duplicate("user", normalized_content):
                    # Persist user message to DB
                    self._persist_message("user", normalized_content)
                
                try:
                    # Apply context management before LLM call (auto-compaction)
                    # Zero overhead when context=False
                    system_prompt_for_llm = self._build_system_prompt(tools)
                    processed_history, context_result = self._apply_context_management(
                        messages=self.chat_history,
                        system_prompt=system_prompt_for_llm,
                        tools=tool_param,
                    )
                    
                    # Pass everything to LLM class
                    # Use llm_prompt (which includes multimodal content if attachments present)
                    # Build LLM call kwargs
                    llm_kwargs = dict(
                        prompt=llm_prompt,
                        system_prompt=system_prompt_for_llm,
                        chat_history=processed_history,
                        temperature=temperature,
                        tools=tool_param,
                        output_json=output_json,
                        output_pydantic=output_pydantic,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        reflection=self.self_reflect,
                        max_reflect=self.max_reflect,
                        min_reflect=self.min_reflect,
                        console=self.console,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools if tools is not None else self.tools)],
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id,
                        execute_tool_fn=self.execute_tool,
                        parallel_tool_calls=getattr(getattr(self, "execution", None), "parallel_tool_calls", False),
                        reasoning_steps=reasoning_steps,
                        stream=stream
                    )
                    
                    # Pass tool_choice if specified (auto, required, none)
                    # Also check for YAML-configured tool_choice on the agent
                    effective_tool_choice = tool_choice or getattr(self, '_yaml_tool_choice', None)
                    if effective_tool_choice:
                        llm_kwargs['tool_choice'] = effective_tool_choice
                    
                    response_text = self.llm_instance.get_response(**llm_kwargs)

                    self._add_to_chat_history("assistant", response_text)
                    # Persist assistant message to DB
                    self._persist_message("assistant", response_text)

                    # Log completion time if in debug mode
                    if get_logger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.chat completed in {total_time:.2f} seconds")

                    # Apply guardrail validation for custom LLM response
                    try:
                        validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools, task_name, task_description, task_id)
                        # Execute callback and display after validation
                        self._execute_callback_and_display(prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                        return self._trigger_after_agent_hook(prompt, validated_response, start_time)
                    except Exception as e:
                        logging.error(f"Agent {self.name}: Guardrail validation failed for custom LLM: {e}")
                        # Rollback chat history on guardrail failure
                        self._truncate_chat_history(chat_history_length)
                        return None
                except Exception as e:
                    # Rollback chat history if LLM call fails
                    self._truncate_chat_history(chat_history_length)
                    _get_display_functions()['display_error'](f"Error in LLM chat: {e}")
                    return None
            except Exception as e:
                _get_display_functions()['display_error'](f"Error in LLM chat: {e}")
                return None
        else:
            # Determine if we should use native structured output
            schema_model = output_pydantic or output_json
            use_native_format = False
            response_format = None
            
            if schema_model and self._supports_native_structured_output():
                # Model supports native structured output - build response_format
                response_format = self._build_response_format(schema_model)
                if response_format:
                    use_native_format = True
                    logging.debug(f"Agent {self.name} using native structured output with response_format")
            
            # Use the new _build_messages helper method
            # Pass llm_prompt (which includes multimodal content if attachments present)
            messages, original_prompt = self._build_messages(
                llm_prompt, temperature, output_json, output_pydantic,
                use_native_format=use_native_format
            )
            

            # Store chat history length for potential rollback
            chat_history_length = len(self.chat_history)
            
            # Normalize original_prompt for consistent chat history storage
            normalized_content = original_prompt
            if isinstance(original_prompt, list):
                # Extract text from multimodal prompts
                normalized_content = next((item["text"] for item in original_prompt if item.get("type") == "text"), "")
            
            # Prevent duplicate messages
            if not (self.chat_history and 
                    self.chat_history[-1].get("role") == "user" and 
                    self.chat_history[-1].get("content") == normalized_content):
                # Add user message to chat history BEFORE LLM call so handoffs can access it
                self._append_to_chat_history({"role": "user", "content": normalized_content})
                # Persist user message to DB (OpenAI path)
                self._persist_message("user", normalized_content)

            reflection_count = 0
            start_time = time.time()
            
            # Apply context management before LLM call (auto-compaction)
            # Zero overhead when context=False
            system_prompt_content = messages[0].get("content", "") if messages and messages[0].get("role") == "system" else ""
            processed_messages, context_result = self._apply_context_management(
                messages=messages,
                system_prompt=system_prompt_content,
                tools=tools,
            )
            # Use processed messages for the LLM call
            messages = processed_messages
            
            
            # Wrap entire while loop in try-except for rollback on any failure
            try:
                while True:
                    try:
                        if self.verbose:
                            # Handle both string and list prompts for instruction display
                            display_text = prompt
                            if isinstance(prompt, list):
                                # Extract text content from multimodal prompt
                                display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                            
                            if display_text and str(display_text).strip():
                                # Pass agent information to display_instruction
                                agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                                _get_display_functions()['display_instruction'](
                                    f"Agent {self.name} is processing prompt: {display_text}", 
                                    console=self.console,
                                    agent_name=self.name,
                                    agent_role=self.role,
                                    agent_tools=agent_tools
                                )

                        response = self._chat_completion(messages, temperature=temperature, tools=tools if tools else None, reasoning_steps=reasoning_steps, stream=stream, task_name=task_name, task_description=task_description, task_id=task_id, response_format=response_format)
                        if not response:
                            # Rollback chat history on response failure
                            self._truncate_chat_history(chat_history_length)
                            return None

                        # Handle None content (can happen with tool calls or empty responses)
                        content = response.choices[0].message.content
                        response_text = content.strip() if content else ""

                        # Handle output_json or output_pydantic if specified
                        if output_json or output_pydantic:
                            # Add to chat history and return raw response
                            # User message already added before LLM call via _build_messages
                            self._append_to_chat_history({"role": "assistant", "content": response_text})
                            # Persist assistant message to DB
                            self._persist_message("assistant", response_text)
                            # Apply guardrail validation even for JSON output
                            try:
                                validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                # Execute callback after validation
                                self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                return self._trigger_after_agent_hook(original_prompt, validated_response, start_time)
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed for JSON output: {e}")
                                # Rollback chat history on guardrail failure
                                self._truncate_chat_history(chat_history_length)
                                return None

                        if not self.self_reflect:
                            # User message already added before LLM call via _build_messages
                            self._append_to_chat_history({"role": "assistant", "content": response_text})
                            # Persist assistant message to DB (non-reflect path)
                            self._persist_message("assistant", response_text)
                            if self.verbose:
                                logging.debug(f"Agent {self.name} final response: {response_text}")
                            # Return only reasoning content if reasoning_steps is True
                            if reasoning_steps and hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
                                # Apply guardrail to reasoning content
                                try:
                                    validated_reasoning = self._apply_guardrail_with_retry(response.choices[0].message.reasoning_content, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_reasoning, time.time() - start_time, task_name, task_description, task_id)
                                    return self._trigger_after_agent_hook(original_prompt, validated_reasoning, start_time)
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed for reasoning content: {e}")
                                    # Rollback chat history on guardrail failure
                                    self._truncate_chat_history(chat_history_length)
                                    return None
                            # Apply guardrail to regular response
                            try:
                                validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                # Execute callback after validation
                                self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                return self._trigger_after_agent_hook(original_prompt, validated_response, start_time)
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed: {e}")
                                # Rollback chat history on guardrail failure
                                self._truncate_chat_history(chat_history_length)
                                return None

                        reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
{self.reflect_prompt if self.reflect_prompt else "Identify any flaws, improvements, or actions."}
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                        """
                        logging.debug(f"{self.name} reflection attempt {reflection_count+1}, sending prompt: {reflection_prompt}")
                        messages.append({"role": "user", "content": reflection_prompt})

                        try:
                            # Check if we're using a custom LLM (like Gemini)
                            if self._using_custom_llm or self._openai_client is None:
                                # For custom LLMs, we need to handle reflection differently
                                # Use non-streaming to get complete JSON response
                                reflection_response = self._chat_completion(messages, temperature=temperature, tools=None, stream=False, reasoning_steps=False, task_name=task_name, task_description=task_description, task_id=task_id)
                                
                                if not reflection_response or not reflection_response.choices:
                                    raise Exception("No response from reflection request")
                                
                                reflection_content = reflection_response.choices[0].message.content
                                reflection_text = reflection_content.strip() if reflection_content else ""
                                
                                # Clean the JSON output
                                cleaned_json = self.clean_json_output(reflection_text)
                                
                                # Parse the JSON manually
                                reflection_data = json.loads(cleaned_json)
                                
                                # Create a reflection output object manually
                                class CustomReflectionOutput:
                                    def __init__(self, data):
                                        self.reflection = data.get('reflection', '')
                                        self.satisfactory = data.get('satisfactory', 'no').lower()
                                
                                reflection_output = _get_display_functions()['ReflectionOutput'](reflection_data)
                            else:
                                # Use OpenAI's structured output for OpenAI models
                                reflection_response = self._openai_client.sync_client.beta.chat.completions.parse(
                                    model=self.reflect_llm if self.reflect_llm else self.llm,
                                    messages=messages,
                                    temperature=temperature,
                                    response_format=_get_display_functions()['ReflectionOutput']
                                )

                                reflection_output = reflection_response.choices[0].message.parsed

                            if self.verbose:
                                _get_display_functions()['display_self_reflection'](f"Agent {self.name} self reflection (using {self.reflect_llm if self.reflect_llm else self.llm}): reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'", console=self.console)

                            messages.append({"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"})

                            # Only consider satisfactory after minimum reflections
                            if reflection_output.satisfactory == "yes" and reflection_count >= self.min_reflect - 1:
                                if self.verbose:
                                    _get_display_functions()['display_self_reflection']("Agent marked the response as satisfactory after meeting minimum reflections", console=self.console)
                                # User message already added before LLM call via _build_messages
                                self._append_to_chat_history({"role": "assistant", "content": response_text})
                                # Apply guardrail validation after satisfactory reflection
                                try:
                                    validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                    self._end_run(validated_response, "completed", {"duration_ms": (time.time() - start_time) * 1000})
                                    return self._trigger_after_agent_hook(original_prompt, validated_response, start_time)
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed after reflection: {e}")
                                    # Rollback chat history on guardrail failure
                                    self._truncate_chat_history(chat_history_length)
                                    self._end_run(None, "error", {"error": str(e)})
                                    return None

                            # Check if we've hit max reflections
                            if reflection_count >= self.max_reflect - 1:
                                if self.verbose:
                                    _get_display_functions()['display_self_reflection']("Maximum reflection count reached, returning current response", console=self.console)
                                # User message already added before LLM call via _build_messages
                                self._append_to_chat_history({"role": "assistant", "content": response_text})
                                # Apply guardrail validation after max reflections
                                try:
                                    validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                    return self._trigger_after_agent_hook(original_prompt, validated_response, start_time)
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed after max reflections: {e}")
                                    # Rollback chat history on guardrail failure
                                    self._truncate_chat_history(chat_history_length)
                                    return None
                            
                            # If not satisfactory and not at max reflections, continue with regeneration
                            logging.debug(f"{self.name} reflection count {reflection_count + 1}, continuing reflection process")
                            messages.append({"role": "user", "content": "Now regenerate your response using the reflection you made"})
                            # For custom LLMs during reflection, always use non-streaming to ensure complete responses
                            use_stream = self.stream if not self._using_custom_llm else False
                            response = self._chat_completion(messages, temperature=temperature, tools=None, stream=use_stream, task_name=task_name, task_description=task_description, task_id=task_id)
                            content = response.choices[0].message.content
                            response_text = content.strip() if content else ""
                            reflection_count += 1
                            continue  # Continue the loop for more reflections

                        except Exception as e:
                                _get_display_functions()['display_error'](f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                                logging.error("Reflection parsing failed.", exc_info=True)
                                messages.append({"role": "assistant", "content": "Self Reflection failed."})
                                reflection_count += 1
                                continue  # Continue even after error to try again
                    except Exception:
                        # Catch any exception from the inner try block and re-raise to outer handler
                        raise
            except Exception as e:
                # Catch any exceptions that escape the while loop
                _get_display_functions()['display_error'](f"Unexpected error in chat: {e}", console=self.console)
                # Rollback chat history
                self._truncate_chat_history(chat_history_length)
                return None

    def clean_json_output(self, output: str) -> str:
        """Clean and extract JSON from response text."""
        cleaned = output.strip()
        # Remove markdown code blocks if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned  

    async def achat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None, output_json: Optional[Any] = None, output_pydantic: Optional[Any] = None, reasoning_steps: bool = False, stream: Optional[bool] = None, task_name: Optional[str] = None, task_description: Optional[str] = None, task_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None, force_retrieval: bool = False, skip_retrieval: bool = False, attachments: Optional[List[str]] = None, tool_choice: Optional[str] = None):
        """Async version of chat method with self-reflection support.
        
        Args:
            prompt: Text query that WILL be stored in chat_history
            attachments: Optional list of image/file paths that are ephemeral
                        (used for THIS turn only, NEVER stored in history).
        """
        # Slash-command invocation: /skill-name [args] renders the skill body.
        prompt = self._resolve_skill_invocation(prompt)

        # Emit context trace event (zero overhead when not set)
        from ..trace.context_events import get_context_emitter
        _trace_emitter = get_context_emitter()
        _trace_emitter.agent_start(self.name, {"role": self.role, "goal": self.goal})
        
        try:
            return await self._achat_impl(
                prompt=prompt, temperature=temperature, tools=tools,
                output_json=output_json, output_pydantic=output_pydantic,
                reasoning_steps=reasoning_steps, stream=stream,
                task_name=task_name, task_description=task_description, task_id=task_id,
                config=config, force_retrieval=force_retrieval, skip_retrieval=skip_retrieval,
                attachments=attachments, _trace_emitter=_trace_emitter, tool_choice=tool_choice
            )
        finally:
            _trace_emitter.agent_end(self.name)

    async def _achat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None):
        """Internal async chat implementation (extracted for trace wrapping)."""
        # Use agent's stream setting if not explicitly provided
        if stream is None:
            stream = self.stream
        # Process ephemeral attachments (DRY - builds multimodal prompt)
        # IMPORTANT: Original text 'prompt' is stored in history, attachments are NOT
        llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt
        
        # Trigger BEFORE_AGENT hook
        from ..hooks import HookEvent, BeforeAgentInput
        before_agent_input = BeforeAgentInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_AGENT,
            timestamp=str(time.time()),
            agent_name=self.name,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            conversation_history=self.chat_history,
            tools_available=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools or self.tools)]
        )
        hook_results = await self._hook_runner.execute(HookEvent.BEFORE_AGENT, before_agent_input)
        if self._hook_runner.is_blocked(hook_results):
            logging.warning(f"Agent {self.name} execution blocked by BEFORE_AGENT hook")
            return None
            
        # Update prompt if modified by hooks
        for res in hook_results:
            if res.output and res.output.modified_data and "prompt" in res.output.modified_data:
                prompt = res.output.modified_data["prompt"]
                llm_prompt = self._build_multimodal_prompt(prompt, attachments) if attachments else prompt
        
        # Track execution via telemetry
        if hasattr(self, '_telemetry') and self._telemetry:
            self._telemetry.track_agent_execution(self.name, success=True)
            
        # Reset the final display flag for each new conversation
        self._final_display_shown = False
        
        # Log all parameter values when in debug mode
        if get_logger().getEffectiveLevel() == logging.DEBUG:
            param_info = {
                "prompt": str(prompt)[:100] + "..." if isinstance(prompt, str) and len(str(prompt)) > 100 else str(prompt),
                "temperature": temperature,
                "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in tools] if tools else None,
                "output_json": str(output_json.__class__.__name__) if output_json else None,
                "output_pydantic": str(output_pydantic.__class__.__name__) if output_pydantic else None,
                "reasoning_steps": reasoning_steps,
                "agent_name": self.name,
                "agent_role": self.role,
                "agent_goal": self.goal
            }
            logging.debug(f"Agent.achat parameters: {json.dumps(param_info, indent=2, default=str)}")
        
        start_time = time.time()
        reasoning_steps = reasoning_steps or self.reasoning_steps
        try:
            # Default to self.tools if tools argument is None
            if tools is None:
                tools = self.tools

            # Search for existing knowledge if any knowledge is provided
            if self._knowledge_sources and not self._knowledge_processed:
                self._ensure_knowledge_processed()
            
            if not skip_retrieval and self.knowledge:
                search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                if search_results:
                    if isinstance(search_results, dict) and 'results' in search_results:
                        knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                    else:
                        knowledge_content = "\n".join(search_results)
                    prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"

            if self._using_custom_llm:
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize prompt content for consistent chat history storage
                normalized_content = prompt
                if isinstance(prompt, list):
                    # Extract text from multimodal prompts
                    normalized_content = next((item["text"] for item in prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    # Add user message to chat history BEFORE LLM call so handoffs can access it
                    self._append_to_chat_history({"role": "user", "content": normalized_content})

                # --- Context compaction (async custom LLM path) ---
                _exec_cfg = getattr(self, 'execution', None)
                if _exec_cfg and getattr(_exec_cfg, 'context_compaction', False):
                    try:
                        from ..compaction import ContextCompactor
                        from ..hooks import HookEvent as _HE
                        _mtok = getattr(_exec_cfg, 'max_context_tokens', None) or 8000
                        _cw = ContextCompactor(max_tokens=_mtok)
                        if _cw.needs_compaction(self.chat_history):
                            try:
                                await self._hook_runner.execute(_HE.BEFORE_COMPACTION, None)
                            except Exception as e:
                                logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
                                if getattr(self, '_strict_hooks', False):
                                    raise
                            _ch, _cr = _cw.compact(self.chat_history)
                            self._replace_chat_history(_ch)
                            logging.info(
                                f"[compaction] {self.name}: {_cr.original_tokens}→{_cr.compacted_tokens} tokens "
                                f"({_cr.messages_removed} messages removed)"
                            )
                            try:
                                await self._hook_runner.execute(_HE.AFTER_COMPACTION, None)
                            except Exception as e:
                                logging.warning(f"AFTER_COMPACTION hook failed: {e}")
                                if getattr(self, '_strict_hooks', False):
                                    raise
                    except Exception as _ce:
                        if getattr(self, '_strict_hooks', False):
                            raise
                        logging.debug(f"[compaction] skipped (non-fatal): {_ce}")

                try:
                    response_text = await self.llm_instance.get_response_async(
                        prompt=prompt,
                        system_prompt=self._build_system_prompt(tools),
                        chat_history=self.chat_history,
                        temperature=temperature,
                        tools=tools,
                        output_json=output_json,
                        output_pydantic=output_pydantic,
                        verbose=self.verbose,
                        markdown=self.markdown,
                        reflection=self.self_reflect,
                        max_reflect=self.max_reflect,
                        min_reflect=self.min_reflect,
                        console=self.console,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools if tools is not None else self.tools)],
                        task_name=task_name,
                        task_description=task_description,
                        task_id=task_id,
                        execute_tool_fn=self.execute_tool_async,
                        parallel_tool_calls=getattr(getattr(self, "execution", None), "parallel_tool_calls", False),
                        reasoning_steps=reasoning_steps,
                        stream=stream
                    )

                    self._append_to_chat_history({"role": "assistant", "content": response_text})

                    if get_logger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                    
                    # Apply guardrail validation for custom LLM response
                    try:
                        validated_response = self._apply_guardrail_with_retry(response_text, prompt, temperature, tools, task_name, task_description, task_id)
                        # Execute callback after validation
                        self._execute_callback_and_display(normalized_content, validated_response, time.time() - start_time, task_name, task_description, task_id)
                        return await self._atrigger_after_agent_hook(prompt, validated_response, start_time)
                    except Exception as e:
                        logging.error(f"Agent {self.name}: Guardrail validation failed for custom LLM: {e}")
                        # Rollback chat history on guardrail failure
                        self._truncate_chat_history(chat_history_length)
                        return None
                except Exception as e:
                    # Rollback chat history if LLM call fails
                    self._truncate_chat_history(chat_history_length)
                    _get_display_functions()['display_error'](f"Error in LLM chat: {e}")
                    if get_logger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
                    return None

            # For OpenAI client
            # Use the new _build_messages helper method
            messages, original_prompt = self._build_messages(prompt, temperature, output_json, output_pydantic)
            
            # Store chat history length for potential rollback
            chat_history_length = len(self.chat_history)
            
            # Normalize original_prompt for consistent chat history storage
            normalized_content = original_prompt
            if isinstance(original_prompt, list):
                # Extract text from multimodal prompts
                normalized_content = next((item["text"] for item in original_prompt if item.get("type") == "text"), "")
            
            # Prevent duplicate messages
            if not (self.chat_history and 
                    self.chat_history[-1].get("role") == "user" and 
                    self.chat_history[-1].get("content") == normalized_content):
                # Add user message to chat history BEFORE LLM call so handoffs can access it
                self._append_to_chat_history({"role": "user", "content": normalized_content})

            # --- Context compaction (async standard OpenAI path) ---
            _exec_cfg2 = getattr(self, 'execution', None)
            if _exec_cfg2 and getattr(_exec_cfg2, 'context_compaction', False):
                try:
                    from ..compaction import ContextCompactor
                    from ..hooks import HookEvent as _HE2
                    _mtok2 = getattr(_exec_cfg2, 'max_context_tokens', None) or 8000
                    _cw2 = ContextCompactor(max_tokens=_mtok2)
                    if _cw2.needs_compaction(messages):
                        try:
                            await self._hook_runner.execute(_HE2.BEFORE_COMPACTION, None)
                        except Exception:
                            pass
                        _cm2, _cr2 = _cw2.compact(messages)
                        messages[:] = _cm2
                        logging.info(
                            f"[compaction] {self.name}: {_cr2.original_tokens}→{_cr2.compacted_tokens} tokens "
                            f"({_cr2.messages_removed} messages removed)"
                        )
                        try:
                            await self._hook_runner.execute(_HE2.AFTER_COMPACTION, None)
                        except Exception:
                            pass
                except Exception as _ce2:
                    logging.debug(f"[compaction] skipped (non-fatal): {_ce2}")

            reflection_count = 0
            start_time = time.time()

            while True:
                try:
                    if self.verbose:
                        display_text = prompt
                        if isinstance(prompt, list):
                            display_text = next((item["text"] for item in prompt if item["type"] == "text"), "")
                        
                        if display_text and str(display_text).strip():
                            agent_tools = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools]
                            await _get_display_functions()['adisplay_instruction'](
                                f"Agent {self.name} is processing prompt: {display_text}",
                                console=self.console,
                                agent_name=self.name,
                                agent_role=self.role,
                                agent_tools=agent_tools
                            )

                    # Use the new _format_tools_for_completion helper method
                    formatted_tools = self._format_tools_for_completion(tools)
                    
                    # NEW: Unified protocol dispatch path (Issue #1304) - Async version
                    # Enable unified dispatch by default for DRY and feature parity (sync/async consistent)
                    if getattr(self, '_use_unified_llm_dispatch', True):
                        # Build response_format for native structured output (parity with sync path)
                        schema_model = output_pydantic or output_json
                        response_format = None
                        if schema_model and self._supports_native_structured_output():
                            response_format = self._build_response_format(schema_model)
                        
                        # Use composition instead of runtime class mutation for safety
                        response = await self._execute_unified_achat_completion(
                            messages=messages,
                            temperature=temperature,
                            tools=formatted_tools,
                            stream=stream,
                            reasoning_steps=reasoning_steps,
                            task_name=task_name,
                            task_description=task_description,
                            task_id=task_id,
                            response_format=response_format
                        )
                        # Continue to handle structured outputs and other processing
                        # Don't return immediately - fall through to existing logic
                    else:
                        # LEGACY: Check if OpenAI client is available
                        if self._openai_client is None:
                            error_msg = "OpenAI client is not initialized. Please provide OPENAI_API_KEY or use a custom LLM provider."
                            _get_display_functions()['display_error'](error_msg)
                            return None

                        # Make the API call based on the type of request
                        if tools:
                            effective_tool_choice = tool_choice or getattr(self, '_yaml_tool_choice', None)
                            tool_call_kwargs = dict(
                                model=self.llm,
                                messages=messages,
                                temperature=temperature,
                                tools=formatted_tools,
                            )
                            if effective_tool_choice:
                                tool_call_kwargs['tool_choice'] = effective_tool_choice
                            response = await self._openai_client.async_client.chat.completions.create(
                                **tool_call_kwargs
                            )
                            result = await self._achat_completion(response, tools)
                            if get_logger().getEffectiveLevel() == logging.DEBUG:
                                total_time = time.time() - start_time
                                logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                            # Execute callback after tool completion
                            self._execute_callback_and_display(original_prompt, result, time.time() - start_time, task_name, task_description, task_id)
                            return await self._atrigger_after_agent_hook(original_prompt, result, start_time)
                        elif output_json or output_pydantic:
                            response = await self._openai_client.async_client.chat.completions.create(
                                model=self.llm,
                                messages=messages,
                                temperature=temperature,
                                response_format={"type": "json_object"}
                            )
                            response_text = response.choices[0].message.content
                            if get_logger().getEffectiveLevel() == logging.DEBUG:
                                total_time = time.time() - start_time
                                logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                            # Execute callback after JSON/Pydantic completion
                            self._execute_callback_and_display(original_prompt, response_text, time.time() - start_time, task_name, task_description, task_id)
                            return await self._atrigger_after_agent_hook(original_prompt, response_text, start_time)
                        else:
                            response = await self._openai_client.async_client.chat.completions.create(
                                model=self.llm,
                                messages=messages,
                                temperature=temperature
                            )
                        
                        response_text = response.choices[0].message.content
                        
                        # Handle self-reflection if enabled
                        if self.self_reflect:
                            reflection_count = 0
                            
                            while True:
                                reflection_prompt = f"""
Reflect on your previous response: '{response_text}'.
{self.reflect_prompt if self.reflect_prompt else "Identify any flaws, improvements, or actions."}
Provide a "satisfactory" status ('yes' or 'no').
Output MUST be JSON with 'reflection' and 'satisfactory'.
                                """
                                
                                # Add reflection prompt to messages
                                reflection_messages = messages + [
                                    {"role": "assistant", "content": response_text},
                                    {"role": "user", "content": reflection_prompt}
                                ]
                                
                                try:
                                    # Check if OpenAI client is available for self-reflection
                                    if self._openai_client is None:
                                        # For custom LLMs, self-reflection with structured output is not supported
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection'](f"Agent {self.name}: Self-reflection with structured output is not supported for custom LLM providers. Skipping reflection.", console=self.console)
                                        # Return the original response without reflection
                                        self._append_to_chat_history({"role": "user", "content": original_prompt})
                                        self._append_to_chat_history({"role": "assistant", "content": response_text})
                                        if get_logger().getEffectiveLevel() == logging.DEBUG:
                                            total_time = time.time() - start_time
                                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                                        return await self._atrigger_after_agent_hook(original_prompt, response_text, start_time)
                                    
                                    reflection_response = await self._openai_client.async_client.beta.chat.completions.parse(
                                        model=self.reflect_llm if self.reflect_llm else self.llm,
                                        messages=reflection_messages,
                                        temperature=temperature,
                                        response_format=_get_display_functions()['ReflectionOutput']
                                    )
                                    
                                    reflection_output = reflection_response.choices[0].message.parsed
                                    
                                    if self.verbose:
                                        _get_display_functions()['display_self_reflection'](f"Agent {self.name} self reflection (using {self.reflect_llm if self.reflect_llm else self.llm}): reflection='{reflection_output.reflection}' satisfactory='{reflection_output.satisfactory}'", console=self.console)
                                    
                                    # Only consider satisfactory after minimum reflections
                                    if reflection_output.satisfactory == "yes" and reflection_count >= self.min_reflect - 1:
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection']("Agent marked the response as satisfactory after meeting minimum reflections", console=self.console)
                                        break
                                    
                                    # Check if we've hit max reflections
                                    if reflection_count >= self.max_reflect - 1:
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection']("Maximum reflection count reached, returning current response", console=self.console)
                                        break
                                    
                                    # Regenerate response based on reflection
                                    regenerate_messages = reflection_messages + [
                                        {"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"},
                                        {"role": "user", "content": "Now regenerate your response using the reflection you made"}
                                    ]
                                    
                                    new_response = await self._openai_client.async_client.chat.completions.create(
                                        model=self.llm,
                                        messages=regenerate_messages,
                                        temperature=temperature
                                    )
                                    response_text = new_response.choices[0].message.content
                                    reflection_count += 1
                                    
                                except Exception as e:
                                    if self.verbose:
                                        _get_display_functions()['display_error'](f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                                    logging.error("Reflection parsing failed.", exc_info=True)
                                    reflection_count += 1
                                    if reflection_count >= self.max_reflect:
                                        break
                                    continue
                        
                        if get_logger().getEffectiveLevel() == logging.DEBUG:
                            total_time = time.time() - start_time
                            logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                        
                        # Apply guardrail validation for OpenAI client response
                        try:
                            validated_response = self._apply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                            # Execute callback after validation
                            self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                            return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                        except Exception as e:
                            logging.error(f"Agent {self.name}: Guardrail validation failed for OpenAI client: {e}")
                            # Rollback chat history on guardrail failure
                            self._truncate_chat_history(chat_history_length)
                            return None
                except Exception as e:
                    _get_display_functions()['display_error'](f"Error in chat completion: {e}")
                    if get_logger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
                    return None
        except Exception as e:
            _get_display_functions()['display_error'](f"Error in achat: {e}")
            if get_logger().getEffectiveLevel() == logging.DEBUG:
                total_time = time.time() - start_time
                logging.debug(f"Agent.achat failed in {total_time:.2f} seconds: {str(e)}")
            return None

    async def _achat_completion(self, response, tools, reasoning_steps=False):
        """Async version of _chat_completion method"""
        try:
            message = response.choices[0].message
            if not hasattr(message, 'tool_calls') or not message.tool_calls:
                return message.content

            results = []
            for tool_call in message.tool_calls:
                try:
                    function_name = tool_call.function.name
                    # Parse JSON arguments safely 
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as json_error:
                        logging.error(f"Failed to parse tool arguments as JSON: {json_error}")
                        arguments = {}
                    
                    # Find the matching tool
                    tool = next((t for t in tools if t.__name__ == function_name), None)
                    if not tool:
                        _get_display_functions()['display_error'](f"Tool {function_name} not found")
                        continue

                    # --- BEFORE_TOOL hook ---
                    try:
                        from ..hooks import HookEvent, BeforeToolInput
                        _before_tool_input = BeforeToolInput(
                            session_id=getattr(self, '_session_id', 'default'),
                            cwd=os.getcwd(),
                            event_name=HookEvent.BEFORE_TOOL,
                            timestamp=str(time.time()),
                            agent_name=self.name,
                            tool_name=function_name,
                            tool_input=arguments,
                        )
                        _before_results = await self._hook_runner.execute(HookEvent.BEFORE_TOOL, _before_tool_input)
                        if self._hook_runner.is_blocked(_before_results):
                            _block_reason = next(
                                (r.output.get_reason() for r in _before_results if r.output and r.output.is_blocking()),
                                "Blocked by hook"
                            )
                            results.append(f"[Tool blocked by hook: {_block_reason}]")
                            continue
                    except Exception as _hook_err:
                        logging.debug(f"BEFORE_TOOL hook error (non-fatal): {_hook_err}")

                    # Route through safety pipeline instead of direct execution
                    # Pass the tools list to honor task-scoped tools
                    result = await self.execute_tool_async(function_name, arguments, tools_override=tools)

                    # --- AFTER_TOOL hook ---
                    try:
                        from ..hooks import AfterToolInput
                        _after_tool_input = AfterToolInput(
                            session_id=getattr(self, '_session_id', 'default'),
                            cwd=os.getcwd(),
                            event_name=HookEvent.AFTER_TOOL,
                            timestamp=str(time.time()),
                            agent_name=self.name,
                            tool_name=function_name,
                            tool_input=arguments,
                            tool_output=result,
                        )
                        await self._hook_runner.execute(HookEvent.AFTER_TOOL, _after_tool_input)
                    except Exception as _hook_err:
                        logging.debug(f"AFTER_TOOL hook error (non-fatal): {_hook_err}")
                    
                    results.append(result)
                except Exception as e:
                    _get_display_functions()['display_error'](f"Error executing tool {function_name}: {e}")
                    results.append(None)

            # If we have results, format them into a response
            if results:
                formatted_results = "\n".join([str(r) for r in results if r is not None])
                if formatted_results:
                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "assistant", "content": "Here are the tool results:"},
                        {"role": "user", "content": formatted_results + "\nPlease process these results and provide a final response."}
                    ]
                    try:
                        final_response = await self._openai_client.async_client.chat.completions.create(
                            model=self.llm,
                            messages=messages,
                            temperature=1.0,
                            stream=stream
                        )
                        full_response_text = ""
                        reasoning_content = ""
                        chunks = []
                        start_time = time.time()
                        
                        # Process stream without display_generating since streaming is active
                        async for chunk in final_response:
                            chunks.append(chunk)
                            if chunk.choices[0].delta.content:
                                full_response_text += chunk.choices[0].delta.content
                            
                            if reasoning_steps and hasattr(chunk.choices[0].delta, "reasoning_content"):
                                rc = chunk.choices[0].delta.reasoning_content
                                if rc:
                                    reasoning_content += rc
                        
                        self.console.print()
                        
                        final_response = _get_llm_functions()['process_stream_chunks'](chunks)
                        # Return only reasoning content if reasoning_steps is True
                        if reasoning_steps and hasattr(final_response.choices[0].message, 'reasoning_content') and final_response.choices[0].message.reasoning_content:
                            return final_response.choices[0].message.reasoning_content
                        return final_response.choices[0].message.content if final_response else full_response_text

                    except Exception as e:
                        _get_display_functions()['display_error'](f"Error in final chat completion: {e}")
                        return formatted_results
                return formatted_results
            return None
        except Exception as e:
            _get_display_functions()['display_error'](f"Error in _achat_completion: {e}")
            return None

    def iter_stream(self, prompt: str, **kwargs):
        """Stream agent response as an iterator of chunks.
        
        App-friendly streaming. Yields response chunks without terminal display.
        Use this for building custom UIs or processing streams programmatically.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments:
                - display (bool): Show terminal output. Default: False
                - output (str): Output preset override
                
        Yields:
            str: Response chunks as they are generated
            
        Example:
            ```python
            agent = Agent(instructions="You are helpful")
            
            # Process stream programmatically
            full_response = ""
            for chunk in agent.iter_stream("Tell me a story"):
                full_response += chunk
                # Custom processing here
            
            # Or collect all at once
            response = "".join(agent.iter_stream("Hello"))
            ```
        """
        # Load history context
        self._load_history_context()
        
        # Force streaming, no display by default (app-friendly)
        kwargs['stream'] = True
        
        # Use the internal streaming generator
        for chunk in self._start_stream(prompt, **kwargs):
            yield chunk
        
        # Auto-save session if enabled
        self._auto_save_session()

    def _start_stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Stream generator for real-time response chunks."""
        try:
            # Reset the final display flag for each new conversation
            self._final_display_shown = False
            
            # Temporarily disable verbose mode to prevent console output conflicts during streaming
            original_verbose = self.verbose
            self.verbose = False
            
            # For custom LLM path, use the new get_response_stream generator
            if self._using_custom_llm:
                # Handle knowledge search
                actual_prompt = prompt
                if self._knowledge_sources and not self._knowledge_processed:
                    self._ensure_knowledge_processed()
                
                if self.knowledge:
                    search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                    if search_results:
                        if isinstance(search_results, dict) and 'results' in search_results:
                            knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                        else:
                            knowledge_content = "\n".join(search_results)
                        actual_prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"
                
                # Handle tools properly
                tools = kwargs.get('tools', self.tools)
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Convert MCP tools if needed
                if tool_param is not None:
                    MCP = None
                    try:
                        from ..mcp.mcp import MCP
                    except ImportError:
                        pass
                    if MCP is not None and isinstance(tool_param, MCP) and hasattr(tool_param, 'to_openai_tool'):
                        openai_tool = tool_param.to_openai_tool()
                        if openai_tool:
                            if isinstance(openai_tool, list):
                                tool_param = openai_tool
                            else:
                                tool_param = [openai_tool]
                
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize prompt content for chat history
                normalized_content = actual_prompt
                if isinstance(actual_prompt, list):
                    normalized_content = next((item["text"] for item in actual_prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages in chat history
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    self._append_to_chat_history({"role": "user", "content": normalized_content})
                
                try:
                    # Use the new streaming generator from LLM class
                    response_content = ""
                    for chunk in self.llm_instance.get_response_stream(
                        prompt=actual_prompt,
                        system_prompt=self._build_system_prompt(tool_param),
                        chat_history=self.chat_history,
                        temperature=kwargs.get('temperature', 1.0),
                        tools=tool_param,
                        output_json=kwargs.get('output_json'),
                        output_pydantic=kwargs.get('output_pydantic'),
                        verbose=False,  # Keep verbose false for streaming
                        markdown=self.markdown,
                        agent_name=self.name,
                        agent_role=self.role,
                        agent_tools=[t.__name__ if hasattr(t, '__name__') else str(t) for t in (tool_param or [])],
                        task_name=kwargs.get('task_name'),
                        task_description=kwargs.get('task_description'),
                        task_id=kwargs.get('task_id'),
                        execute_tool_fn=self.execute_tool,
                        parallel_tool_calls=getattr(getattr(self, "execution", None), "parallel_tool_calls", False)
                    ):
                        response_content += chunk
                        yield chunk
                    
                    # Add complete response to chat history
                    if response_content:
                        self._append_to_chat_history({"role": "assistant", "content": response_content})
                        
                except Exception as e:
                    # Rollback chat history on error
                    self._truncate_chat_history(chat_history_length)
                    logging.error(f"Custom LLM streaming error: {e}")
                    raise
                    
            else:
                # For OpenAI-style models, implement proper streaming without display
                # Handle knowledge search
                actual_prompt = prompt
                if self._knowledge_sources and not self._knowledge_processed:
                    self._ensure_knowledge_processed()
                
                if self.knowledge:
                    search_results = self.knowledge.search(prompt, agent_id=self.agent_id)
                    if search_results:
                        if isinstance(search_results, dict) and 'results' in search_results:
                            knowledge_content = "\n".join([result['memory'] for result in search_results['results']])
                        else:
                            knowledge_content = "\n".join(search_results)
                        actual_prompt = f"{prompt}\n\nKnowledge: {knowledge_content}"
                
                # Handle tools properly
                tools = kwargs.get('tools', self.tools)
                if tools is None or (isinstance(tools, list) and len(tools) == 0):
                    tool_param = self.tools
                else:
                    tool_param = tools
                
                # Build messages using the helper method
                messages, original_prompt = self._build_messages(actual_prompt, kwargs.get('temperature', 1.0), 
                                                               kwargs.get('output_json'), kwargs.get('output_pydantic'))
                
                # Store chat history length for potential rollback
                chat_history_length = len(self.chat_history)
                
                # Normalize original_prompt for consistent chat history storage
                normalized_content = original_prompt
                if isinstance(original_prompt, list):
                    normalized_content = next((item["text"] for item in original_prompt if item.get("type") == "text"), "")
                
                # Prevent duplicate messages in chat history
                if not (self.chat_history and 
                        self.chat_history[-1].get("role") == "user" and 
                        self.chat_history[-1].get("content") == normalized_content):
                    self._append_to_chat_history({"role": "user", "content": normalized_content})
                
                try:
                    # Check if OpenAI client is available
                    if self._openai_client is None:
                        raise ValueError("OpenAI client is not initialized. Please provide OPENAI_API_KEY or use a custom LLM provider.")
                    
                    # Format tools for OpenAI
                    formatted_tools = self._format_tools_for_completion(tool_param)
                    
                    # Create streaming completion directly without display function
                    completion_args = {
                        "model": self.llm,
                        "messages": messages,
                        "temperature": kwargs.get('temperature', 1.0),
                        "stream": True
                    }
                    if formatted_tools:
                        completion_args["tools"] = formatted_tools
                    
                    # Import StreamEvent types for event emission
                    from ..streaming.events import StreamEvent, StreamEventType
                    import time as time_module
                    
                    # Emit REQUEST_START event
                    request_start_perf = time_module.perf_counter()
                    self.stream_emitter.emit(StreamEvent(
                        type=StreamEventType.REQUEST_START,
                        timestamp=request_start_perf,
                        metadata={"model": self.llm, "message_count": len(messages)}
                    ))
                    
                    completion = self._openai_client.sync_client.chat.completions.create(**completion_args)
                    
                    # Emit HEADERS_RECEIVED event
                    self.stream_emitter.emit(StreamEvent(
                        type=StreamEventType.HEADERS_RECEIVED,
                        timestamp=time_module.perf_counter()
                    ))
                    
                    # Stream the response chunks without display
                    response_text = ""
                    tool_calls_data = []
                    first_token_emitted = False
                    last_content_time = None
                    
                    for chunk in completion:
                        delta = chunk.choices[0].delta
                        
                        # Handle text content
                        if delta.content is not None:
                            chunk_content = delta.content
                            response_text += chunk_content
                            last_content_time = time_module.perf_counter()
                            
                            # Emit FIRST_TOKEN on first content
                            if not first_token_emitted:
                                self.stream_emitter.emit(StreamEvent(
                                    type=StreamEventType.FIRST_TOKEN,
                                    timestamp=last_content_time,
                                    content=chunk_content
                                ))
                                first_token_emitted = True
                            else:
                                # Emit DELTA_TEXT for subsequent tokens
                                self.stream_emitter.emit(StreamEvent(
                                    type=StreamEventType.DELTA_TEXT,
                                    timestamp=last_content_time,
                                    content=chunk_content
                                ))
                            
                            yield chunk_content
                        
                        # Handle tool calls (accumulate but don't yield as chunks)
                        if hasattr(delta, 'tool_calls') and delta.tool_calls:
                            for tool_call_delta in delta.tool_calls:
                                # Extend tool_calls_data list to accommodate the tool call index
                                while len(tool_calls_data) <= tool_call_delta.index:
                                    tool_calls_data.append({'id': '', 'function': {'name': '', 'arguments': ''}})
                                
                                # Accumulate tool call data
                                if tool_call_delta.id:
                                    tool_calls_data[tool_call_delta.index]['id'] = tool_call_delta.id
                                if tool_call_delta.function.name:
                                    tool_calls_data[tool_call_delta.index]['function']['name'] = tool_call_delta.function.name
                                if tool_call_delta.function.arguments:
                                    tool_calls_data[tool_call_delta.index]['function']['arguments'] += tool_call_delta.function.arguments
                    
                    # Emit LAST_TOKEN and STREAM_END events after streaming loop
                    if last_content_time:
                        self.stream_emitter.emit(StreamEvent(
                            type=StreamEventType.LAST_TOKEN,
                            timestamp=last_content_time
                        ))
                    self.stream_emitter.emit(StreamEvent(
                        type=StreamEventType.STREAM_END,
                        timestamp=time_module.perf_counter(),
                        metadata={"response_length": len(response_text)}
                    ))
                    
                    # Handle any tool calls that were accumulated
                    if tool_calls_data:
                        # Add assistant message with tool calls to chat history
                        assistant_message = {"role": "assistant", "content": response_text}
                        if tool_calls_data:
                            assistant_message["tool_calls"] = [
                                {
                                    "id": tc['id'],
                                    "type": "function", 
                                    "function": tc['function']
                                } for tc in tool_calls_data if tc['id']
                            ]
                        self._append_to_chat_history(assistant_message)
                        
                        # Execute tool calls and add results to chat history
                        for tool_call in tool_calls_data:
                            if tool_call['id'] and tool_call['function']['name']:
                                try:
                                    # Parse JSON arguments safely 
                                    try:
                                        parsed_args = json.loads(tool_call['function']['arguments']) if tool_call['function']['arguments'] else {}
                                    except json.JSONDecodeError as json_error:
                                        logging.error(f"Failed to parse tool arguments as JSON: {json_error}")
                                        parsed_args = {}
                                    
                                    tool_result = self.execute_tool(
                                        tool_call['function']['name'], 
                                        parsed_args,
                                        tool_call_id=tool_call.get('id')
                                    )
                                    # Add tool result to chat history
                                    self._append_to_chat_history({
                                        "role": "tool",
                                        "tool_call_id": tool_call['id'],
                                        "content": str(tool_result)
                                    })
                                except Exception as tool_error:
                                    logging.error(f"Tool execution error in streaming: {tool_error}")
                                    # Add error result to chat history
                                    self._append_to_chat_history({
                                        "role": "tool", 
                                        "tool_call_id": tool_call['id'],
                                        "content": f"Error: {str(tool_error)}"
                                    })
                    else:
                        # Add complete response to chat history (text-only response)
                        if response_text:
                            self._append_to_chat_history({"role": "assistant", "content": response_text})
                        
                except Exception as e:
                    # Rollback chat history on error
                    self._truncate_chat_history(chat_history_length)
                    logging.error(f"OpenAI streaming error: {e}")
                    # Fall back to simulated streaming
                    response = self.chat(prompt, **kwargs)
                    if response:
                        words = str(response).split()
                        chunk_size = max(1, len(words) // 20)
                        for i in range(0, len(words), chunk_size):
                            chunk_words = words[i:i + chunk_size]
                            chunk = ' '.join(chunk_words)
                            if i + chunk_size < len(words):
                                chunk += ' '
                            yield chunk
            
            # Restore original verbose mode
            self.verbose = original_verbose
                    
        except Exception as e:
            # Restore verbose mode on any error
            self.verbose = original_verbose
            # Graceful fallback to non-streaming if streaming fails
            logging.warning(f"Streaming failed, falling back to regular response: {e}")
            response = self.chat(prompt, **kwargs)
            if response:
                yield response
