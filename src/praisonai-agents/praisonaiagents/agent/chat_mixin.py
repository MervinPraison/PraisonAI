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
from ..errors import BudgetExceededError

# Shared lazy display helpers (cached, thread-safe; avoid circular imports)
from ._lazy_display import _get_console, _get_live, _get_display_functions

logger = logging.getLogger(__name__)



from typing import List, Optional, Any, Dict, Union, Generator, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ChatMixin:
    """Mixin providing chat methods for the Agent class."""

    def _resolve_max_steps(self, default: int = 10) -> int:
        """Resolve the unified multi-step tool budget shared by both loops.

        Reads ``ExecutionConfig.max_steps`` when set (single knob honoured by the
        OpenAI-native and LiteLLM tool-execution loops); otherwise falls back to
        ``max_iter`` and finally ``default`` for backward compatibility.
        """
        execution = getattr(self, "execution", None)
        if execution is not None:
            resolver = getattr(execution, "resolved_max_steps", None)
            if callable(resolver):
                try:
                    return int(resolver())
                except Exception:
                    pass
            max_steps = getattr(execution, "max_steps", None)
            if max_steps is not None:
                return int(max_steps)
            max_iter = getattr(execution, "max_iter", None)
            if max_iter is not None:
                return int(max_iter)
        return default

    def _resolve_max_tool_calls(self, default: int = 10) -> int:
        """Resolve the per-turn tool-call guardrail (independent of ``max_steps``)."""
        execution = getattr(self, "execution", None)
        if execution is not None:
            resolver = getattr(execution, "resolved_max_tool_calls", None)
            if callable(resolver):
                try:
                    return int(resolver())
                except Exception:
                    pass
            return int(getattr(execution, "max_tool_calls_per_turn", default))
        return default

    def _resolve_harness_base_prompt(self):
        """Resolve the model-family harness base-prompt fragment, if any.

        Honours an explicit ``harness_base_prompt`` override on the agent when
        set; otherwise resolves lazily from the active model id. Returns an
        empty string when no fragment applies (behaviour-preserving default).
        Never raises: any resolution error collapses to no fragment.
        """
        override = getattr(self, "harness_base_prompt", None)
        if override is not None:
            return override
        try:
            from ..model_harness import resolve_harness
            # self.llm may be a string model id or an LLM object; resolve the
            # string form only (unknown/object models keep the default profile).
            model = getattr(self, "llm", None)
            model_id = model if isinstance(model, str) else None
            profile = resolve_harness(model_id)
            return profile.base_prompt or ""
        except Exception:
            return ""

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

        # Prepend the model-family harness base prompt when one applies.
        # Resolution is lazy and falls back to a behaviour-preserving default
        # (no fragment) for unknown models, so output is unchanged by default.
        harness_prompt = self._resolve_harness_base_prompt()
        if harness_prompt:
            system_prompt = f"{harness_prompt}\n\n{system_prompt}"
        
        # Add rules context when rules are enabled (default). Discovery is
        # lazy and gated: accessing self.rules_manager triggers a cheap
        # filesystem scan the first time; if no instruction file/dir is found
        # the manager is dropped, so zero-config runs incur no ongoing cost.
        if getattr(self, "_rules_enabled", True) and self.rules_manager:
            rules_context = self.get_rules_context()
            if rules_context:
                system_prompt += f"\n\n## Rules (Guidelines you must follow)\n{rules_context}"
        
        # Add memory context if memory is enabled
        if self._memory_instance:
            # Use cache-optimized context if model supports prompt caching and cache boundary is requested
            use_cache_boundaries = hasattr(self, '_model_supports_prompt_caching') and self._model_supports_prompt_caching()
            if use_cache_boundaries and hasattr(self._memory_instance, 'build_cache_optimized_context'):
                try:
                    # Get the goal/task description for context building
                    task_desc = getattr(self, 'goal', '') or 'general assistance'
                    cache_result = self._memory_instance.build_cache_optimized_context(
                        task_descr=task_desc,
                        include_cache_boundary=True
                    )
                    memory_context = cache_result.get('stable_prefix', '')
                    if memory_context:
                        system_prompt += f"\n\n## Memory (Information you remember about the user)\n{memory_context}"
                        # Note: the cache boundary marker is intentionally NOT
                        # appended to the prompt text. No provider currently
                        # consumes it as structured cache metadata, so injecting
                        # the raw sentinel would only pollute the system prompt.
                        # Display memory info to user if verbose
                        if self.verbose:
                            self._display_memory_info()
                except (AttributeError, KeyError, TypeError) as e:
                    # Fall back to standard memory context if cache optimization fails
                    memory_context = self.get_memory_context()
                    if memory_context:
                        system_prompt += f"\n\n## Memory (Information you remember about the user)\n{memory_context}"
                        # Display memory info to user if verbose
                        if self.verbose:
                            self._display_memory_info()
            else:
                # Standard memory context without cache boundaries
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
        
        # Cache the base system prompt BEFORE adding session context
        # Session context is per-turn and should not be cached
        if cache_key:
            self._cache_put(self._system_prompt_cache, cache_key, system_prompt)
        
        # Add session context (platform awareness) if available - AFTER caching
        try:
            from ..session.context import get_session_context
            session_ctx = get_session_context()
            
            # Format session context into prompt if origin or targets are present
            if session_ctx.origin or session_ctx.reachable_targets:
                context_parts = []
                
                # Add origin information
                if session_ctx.origin:
                    origin = session_ctx.origin
                    origin_str = f"You are replying on {origin.platform}"
                    if origin.chat_type and origin.chat_type != "unknown":
                        origin_str += f" ({origin.chat_type}"
                        if origin.display_name:
                            origin_str += f' "{origin.display_name}"'
                        origin_str += ")"
                    if origin.thread_id:
                        origin_str += f" in thread {origin.thread_id}"
                    context_parts.append(origin_str + ".")
                
                # Add reachable targets
                if session_ctx.reachable_targets:
                    target_descriptions = []
                    for target in session_ctx.reachable_targets:
                        desc = f"{target.name}"
                        if target.kind == "home":
                            desc += f" ({target.platform}, home channel)"
                        elif target.kind == "alias":
                            desc += f" ({target.platform}:{target.channel_id})"
                        target_descriptions.append(desc)
                    
                    if target_descriptions:
                        context_parts.append(
                            f"Reachable delivery targets: {', '.join(target_descriptions)}."
                        )
                
                if context_parts:
                    system_prompt += "\n\n## Session Context\n" + "\n".join(context_parts)
        except ImportError:
            # Session context module not available, continue without it
            pass
        except Exception as e:
            # Log unexpected errors but continue
            import logging
            logging.debug(f"Session context injection failed: {e}", exc_info=True)
            pass
        
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
            
            # Prune permission-denied tool names so the advertised surface in the
            # system prompt matches the function schema (and execution-time rules).
            tool_names = [n for n in tool_names if self._tool_name_allowed(n)]

            if tool_names:
                system_prompt += f"\n\nYou have access to the following tools: {', '.join(tool_names)}. Use these tools when appropriate to help complete your tasks. Always use tools when they can help provide accurate information or perform actions."
                system_prompt += "\n\nExplain Before Acting: Before calling a tool, provide a brief one-sentence explanation of what you are about to do and why. Skip explanations only for repetitive low-level operations where narration would be noisy. When performing a batch of similar operations (e.g. searching for multiple items), explain the group once rather than narrating each call individually."
        
        # Add prompt injection protection instructions for external tool results
        try:
            from ..tools.trust import get_system_prompt_addition
            trust_instructions = get_system_prompt_addition()
            if trust_instructions:
                system_prompt += f"\n\n## Security: {trust_instructions}"
        except ImportError:
            pass  # Trust module not available, skip security instructions
        
        # Apply model-aware runtime profile overrides (opt-in). When no profile
        # is configured for the active model family, the resolved profile is the
        # behaviour-neutral "default" whose apply_system_prompt is a no-op, so
        # the generated prompt is byte-for-byte identical to before.
        try:
            profile = self._resolve_runtime_profile()
            if profile is not None:
                # apply_system_prompt is a pure no-op unless the profile declares
                # prompt overrides, so the default/family profiles leave the
                # generated prompt byte-for-byte identical.
                system_prompt = profile.apply_system_prompt(system_prompt)
        except Exception as e:
            import logging
            logging.debug(f"Runtime profile application failed: {e}", exc_info=True)

        # Note: Caching is done BEFORE session context injection to avoid cross-user leakage
        return system_prompt

    def _resolve_runtime_profile(self):
        """Resolve the model-aware runtime profile for this agent.

        Honours an explicit ``runtime_profile`` set on the agent (bool/str/dict/
        RuntimeProfile); otherwise resolves by model family. Returns the
        behaviour-neutral ``default`` profile when nothing matches or the feature
        is disabled, keeping output identical to today.
        """
        from ..runtime.profiles import RuntimeProfile, resolve_profile

        configured = getattr(self, "runtime_profile", None)

        if configured is False:
            return None
        if isinstance(configured, RuntimeProfile):
            return configured
        if isinstance(configured, dict):
            return RuntimeProfile(**configured)

        model = self.llm if isinstance(self.llm, str) else str(self.llm) if self.llm else None
        if isinstance(configured, str):
            return resolve_profile(model=model, name=configured)
        return resolve_profile(model=model)

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
            return False  # Module genuinely not available - acceptable

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
                    # Prefer compacted working history (summary + tail) on
                    # resume when a compaction checkpoint exists (Issue #2741);
                    # falls back to raw chat history for backward compatibility.
                    if hasattr(self._session_store, "get_working_history"):
                        session_history = self._session_store.get_working_history(
                            self._history_session_id,
                            max_messages=self._history_limit
                        )
                    else:
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
        - Tool Search progressive disclosure (if enabled)
        
        Args:
            tools: List of tools in various formats or None to use self.tools.
                  Note: [] (empty list) means explicitly no tools (security boundary),
                        None means inherit from self.tools
            
        Returns:
            List of formatted tools or empty list
        """
        # Security fix: Distinguish None (inherit) vs [] (explicit deny)
        if tools is None:
            tools = self.tools
        elif isinstance(tools, list) and len(tools) == 0:
            # Explicit empty list - return immediately to enforce boundary
            return []
        
        if not tools:
            return []
        
        # Check cache first - include tool_search config in cache key for safety
        tools_key = self._get_tools_cache_key(tools)
        tool_search_enabled = getattr(self, '_tool_search_config', None) is not None
        cache_key = f"{tools_key}:tool_search={tool_search_enabled}"
        cached_entry = self._cache_get(self._formatted_tools_cache, cache_key)
        if cached_entry is not None:
            cached_tools, cached_metadata = cached_entry
            self._tool_search_metadata = cached_metadata
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
        
        # Apply tool search assembly if enabled (after formatting, before caching)
        if hasattr(self, '_tool_search_config') and self._tool_search_config is not None:
            try:
                from ..tools.tool_search import assemble_tool_defs
                # Get context length from LLM config if available
                context_length = getattr(self, '_context_window_size', None)
                
                # Assemble tools with bridge mode check
                assembled_tools, metadata = assemble_tool_defs(
                    tool_defs=formatted_tools,
                    config=self._tool_search_config,
                    context_length=context_length
                )
                
                # Store metadata for bridge tool dispatch
                self._tool_search_metadata = metadata
                formatted_tools = assembled_tools
                
            except ImportError:
                # Tool search module not available, continue with original tools
                logging.warning("Tool search requested but tool_search module not available")
        
        # Strip __praisonai_deferrable__ from provider-facing tool payloads
        # Keep the marker only for internal tool classification
        cleaned_tools = []
        for tool in formatted_tools:
            if isinstance(tool, dict) and "__praisonai_deferrable__" in tool:
                tool_copy = tool.copy()
                tool_copy.pop("__praisonai_deferrable__", None)
                cleaned_tools.append(tool_copy)
            else:
                cleaned_tools.append(tool)
        
        # Sort tools deterministically for cache stability
        def sort_formatted_tools(tools_list):
            """Sort already-formatted tool schemas by function name."""
            def sort_key(tool):
                if isinstance(tool, dict) and tool.get('type') == 'function':
                    return str(tool.get('function', {}).get('name') or '')
                return ''
            return sorted(tools_list, key=sort_key)
        
        cleaned_tools = sort_formatted_tools(cleaned_tools)
        
        # Prune permission-denied tools from the advertised set so the model is
        # only ever offered tools it can actually call. Mirrors the execution-time
        # enforcement in tool_execution.py (_perm_deny / _perm_allow). No-op when
        # no deny set and no allow set are configured (backward compatible).
        cleaned_tools = self._prune_denied_tools(cleaned_tools)
        
        # Cache the formatted tools with LRU eviction, including tool search metadata
        self._cache_put(
            self._formatted_tools_cache,
            cache_key,
            (cleaned_tools, getattr(self, "_tool_search_metadata", None)),
        )
        return cleaned_tools

    def _build_before_tool_definitions_input(self, formatted_tools):
        """Build the BEFORE_TOOL_DEFINITIONS hook input.

        A deep copy of ``formatted_tools`` is used so that in-place hook
        mutations never leak back into ``_format_tools_for_completion``'s cache
        and corrupt subsequent requests.
        """
        import copy
        from ..hooks import HookEvent, BeforeToolDefinitionsInput
        return BeforeToolDefinitionsInput(
            session_id=getattr(self, '_session_id', 'default'),
            cwd=os.getcwd(),
            event_name=HookEvent.BEFORE_TOOL_DEFINITIONS,
            timestamp=str(time.time()),
            agent_name=self.name,
            model=self.llm if isinstance(self.llm, str) else str(self.llm),
            tool_definitions=copy.deepcopy(formatted_tools),
        )

    def _apply_before_tool_definitions_hook(self, formatted_tools):
        """Fire the BEFORE_TOOL_DEFINITIONS hook so hooks/plugins can inspect or
        rewrite the advertised tool definitions before they reach the LLM.

        Mirrors how BEFORE_LLM lets a hook mutate its payload in place. No-op
        (returns the input unchanged) when no hook runner or no tools exist.
        Returns the possibly-mutated list of tool definitions. Synchronous
        path; use ``_aapply_before_tool_definitions_hook`` in async contexts.
        """
        if not formatted_tools or not getattr(self, '_hook_runner', None):
            return formatted_tools
        try:
            from ..hooks import HookEvent
            _inp = self._build_before_tool_definitions_input(formatted_tools)
            _results = self._hook_runner.execute_sync(HookEvent.BEFORE_TOOL_DEFINITIONS, _inp)
            # Fail closed on a blocking hook/plugin: a POLICY/GUARDRAIL that
            # denies the advertised tool surface must actually withhold it,
            # not just rewrite it. Dropping every definition keeps the model
            # from being offered a tool a guardrail refused.
            if self._hook_runner.is_blocked(_results):
                _reason = next(
                    (getattr(r.output, "reason", None) for r in _results
                     if r.output and getattr(r.output, "is_denied", lambda: False)()),
                    None,
                ) or "Blocked by hook"
                logging.warning(
                    f"[before-tool-definitions] tool definitions blocked by hook: {_reason}"
                )
                return []
            # Adopt mutations, mirroring how BEFORE_LLM adopts its payload.
            return _inp.tool_definitions
        except Exception as _e:
            logging.debug(f"[before-tool-definitions] hook skipped: {_e}")
            return formatted_tools

    async def _aapply_before_tool_definitions_hook(self, formatted_tools):
        """Async variant of ``_apply_before_tool_definitions_hook``.

        ``execute_sync`` raises inside a running event loop, so the async chat
        path must await the hook runner directly to actually run the hook.
        """
        if not formatted_tools or not getattr(self, '_hook_runner', None):
            return formatted_tools
        try:
            from ..hooks import HookEvent
            _inp = self._build_before_tool_definitions_input(formatted_tools)
            _results = await self._hook_runner.execute(HookEvent.BEFORE_TOOL_DEFINITIONS, _inp)
            # Fail closed on a blocking hook/plugin (see sync variant).
            if self._hook_runner.is_blocked(_results):
                _reason = next(
                    (getattr(r.output, "reason", None) for r in _results
                     if r.output and getattr(r.output, "is_denied", lambda: False)()),
                    None,
                ) or "Blocked by hook"
                logging.warning(
                    f"[before-tool-definitions] tool definitions blocked by hook: {_reason}"
                )
                return []
            return _inp.tool_definitions
        except Exception as _e:
            logging.debug(f"[before-tool-definitions] async hook skipped: {_e}")
            return formatted_tools

    def _prune_denied_tools(self, formatted_tools):
        """Remove tools whose permission resolves to ``deny`` from the payload.

        The advertised tool surface is shaped by the agent's effective
        permission tier (resolved at ``__init__`` into ``_perm_deny`` /
        ``_perm_allow``) so the model is never offered a tool it cannot call.
        ``ask``/``allow`` tools stay advertised — approval still happens at
        execution time (defence in depth). This is a no-op when no ``deny`` set
        and no ``allow`` set are configured, preserving backward compatibility.

        Args:
            formatted_tools: List of OpenAI-schema tool definitions.

        Returns:
            The filtered list (a new list only when something is pruned).
        """
        if not formatted_tools:
            return formatted_tools

        perm_deny = getattr(self, "_perm_deny", None)
        perm_allow = getattr(self, "_perm_allow", None)
        manager = getattr(self, "_permission_manager", None)

        # Fast path: no permission shaping configured -> advertise everything.
        if not perm_deny and perm_allow is None and manager is None:
            return formatted_tools

        def _tool_id(tool):
            if isinstance(tool, dict) and tool.get("type") == "function":
                return str(tool.get("function", {}).get("name") or "")
            return ""

        pruned = []
        for tool in formatted_tools:
            name = _tool_id(tool)
            if not name:
                # Keep unrecognized schemas as-is; cannot evaluate permission.
                pruned.append(tool)
                continue
            if not self._tool_name_allowed(name):
                logging.debug("Pruning permission-denied tool from payload: %s", name)
                continue
            pruned.append(tool)
        return pruned

    def _tool_name_allowed(self, name):
        """Return ``True`` if ``name`` is callable under the agent's permissions.

        Mirrors the execution-time enforcement in ``tool_execution.py``
        (``_perm_deny`` / ``_perm_allow``): a tool is denied if it is in the
        deny set or, when an allow set is configured, absent from it.
        ``ask``/``allow`` tools remain callable (approval happens at execution
        time). No-op (always allowed) when no permission shaping is configured.
        """
        if not name:
            return True
        perm_deny = getattr(self, "_perm_deny", None)
        perm_allow = getattr(self, "_perm_allow", None)
        if perm_deny and name in perm_deny:
            return False
        if perm_allow is not None and name not in perm_allow:
            return False
        # Consult the pattern-based PermissionManager (rules loaded from
        # .praisonai/permissions/, YAML or Python). A tool whose effective
        # decision is a hard ``deny`` is hidden from the schema; ``ask``/
        # ``allow`` stay visible (approval still happens at execution time).
        # No-op when no manager is attached, preserving backward compatibility.
        manager = getattr(self, "_permission_manager", None)
        if manager is not None:
            try:
                if manager.is_denied(name, getattr(self, "name", None)):
                    return False
            except Exception as e:  # noqa: BLE001
                logging.debug("permission manager is_denied failed for %s: %s", name, e)
        return True

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

    def _get_compaction_policy(self):
        """
        Get the active compaction policy for this agent.
        
        Shared logic used by both sync and async context budget computation.
        """
        from ..context.policy import get_default_policy
        
        # Get execution config and policy
        _execution_cfg = getattr(self, 'execution', None)
        
        if _execution_cfg:
            compaction_setting = getattr(_execution_cfg, 'context_compaction', True)
            if compaction_setting is False:
                # Explicitly disabled 
                return None
            elif compaction_setting is True:
                # Use default policy
                return get_default_policy()
            else:
                # Custom policy provided
                return compaction_setting
        else:
            # No execution config - use safe default
            return get_default_policy()

    def _compute_context_budget_core(self, messages, tools=None, system_prompt=None):
        """
        Core context budget computation logic shared by sync and async versions.
        
        Returns:
            tuple: (policy, budget_result) or (None, None) if compaction disabled
        """
        import logging
        
        # Get policy (None means disabled)
        policy = self._get_compaction_policy()
        if policy is None:
            return None, None
        
        # Get model name for context window lookup
        model_name = self.llm if isinstance(self.llm, str) else "gpt-4o-mini"
        
        # Compute budget using the policy
        budget_result = policy.compute_context_budget(
            messages=messages,
            model=model_name,
            tools=tools,
            system_prompt=system_prompt
        )
        
        # Log budget analysis if enabled
        if getattr(self, '_verbose_context', False):
            logging.info(
                f"[context-budget] {self.name}: {budget_result.current_tokens} tokens, "
                f"{budget_result.utilization:.1%} utilization, route: {budget_result.route.value}"
            )
        
        return policy, budget_result

    def _compute_context_budget_and_route(self, messages, tools=None, system_prompt=None):
        """
        Compute context budget and determine proactive route BEFORE LLM call.
        
        Replaces the old opt-in reactive approach with proactive budget checking.
        
        Returns:
            tuple: (route, compacted_messages) where route is from CompactionRoute enum
        """
        from ..context.policy import CompactionRoute
        from ..compaction import ContextCompactor
        
        # Use shared core logic
        policy, budget_result = self._compute_context_budget_core(messages, tools, system_prompt)
        
        # If compaction disabled, return unchanged
        if policy is None:
            return CompactionRoute.FITS, messages
        
        # Handle the routing decision
        if budget_result.route == CompactionRoute.FITS:
            return CompactionRoute.FITS, messages
        
        # Need some form of compaction - get max tokens for compactor
        _execution_cfg = getattr(self, 'execution', None)
        max_tokens = getattr(_execution_cfg, 'max_context_tokens', None) if _execution_cfg else None
        if max_tokens is None:
            # Use 90% of available tokens as max to leave room for output
            max_tokens = int(budget_result.available_tokens * 0.9)
        
        # Create compactor with policy-driven settings
        compactor = ContextCompactor(
            max_tokens=max_tokens,
            target_tokens=int(max_tokens * policy.target_utilization),
            preserve_recent=policy.preserve_last_n_turns
        )
        
        # Apply compaction based on route
        if budget_result.route == CompactionRoute.COMPACT_NEEDED:
            return self._apply_compaction(messages, compactor, policy)
        elif budget_result.route == CompactionRoute.TRUNCATE_TOOLS:
            return self._apply_tool_truncation(messages, compactor, policy)
        elif budget_result.route == CompactionRoute.COMPACT_THEN_TRUNCATE:
            # First try compaction
            route, compacted_messages = self._apply_compaction(messages, compactor, policy)
            # If still over budget, also truncate tools
            if compactor.needs_compaction(compacted_messages):
                return self._apply_tool_truncation(compacted_messages, compactor, policy)
            return route, compacted_messages
        
        return CompactionRoute.FITS, messages

    def _apply_compaction(self, messages, compactor, policy):
        """Apply standard context compaction."""
        from ..compaction.strategy import CompactionStrategy as LegacyStrategy
        from ..hooks import HookEvent as _HookEvent
        import logging
        
        # Map policy strategy to compactor strategy
        strategy_map = {
            "truncate": LegacyStrategy.TRUNCATE,
            "summarise": LegacyStrategy.SUMMARIZE,
            "drop_oldest_tools": LegacyStrategy.PRUNE,
            "sliding_window": LegacyStrategy.SLIDING,
        }
        
        compactor.strategy = strategy_map.get(policy.strategy.value, LegacyStrategy.PRUNE)
        
        # Execute hooks
        try:
            self._hook_runner.execute_sync(_HookEvent.BEFORE_COMPACTION, None)
        except Exception as e:
            logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
            if getattr(self, '_strict_hooks', False):
                raise
        
        # Perform compaction
        compacted_msgs, result = compactor.compact(messages)
        
        logging.info(
            f"[proactive-compaction] {self.name}: {result.original_tokens}→{result.compacted_tokens} tokens "
            f"({result.messages_removed} messages removed, strategy: {policy.strategy.value})"
        )

        # Issue #2741: Persist the compaction summary back into the bound
        # session so `--continue`/resume reconstructs the compacted context
        # instead of replaying the raw transcript. Guarded so it only fires
        # when a session store + session_id are bound and a summary exists.
        self._persist_compaction_checkpoint(result)
        
        try:
            self._hook_runner.execute_sync(_HookEvent.AFTER_COMPACTION, result)
        except Exception as e:
            logging.warning(f"AFTER_COMPACTION hook failed: {e}")
            if getattr(self, '_strict_hooks', False):
                raise
        
        from ..context.policy import CompactionRoute
        return CompactionRoute.COMPACT_NEEDED, compacted_msgs

    def _persist_compaction_checkpoint(self, result) -> None:
        """Persist a compaction summary into the bound session (Issue #2741).

        No-op unless a JSON session store and session_id are bound and the
        compaction produced a non-empty summary. Keeps resume cheap without
        bloating the agent flow or requiring new params.
        """
        import logging
        store = getattr(self, "_session_store", None)
        # Issue #2741: write to the same key the resume read path uses
        # (_history_session_id), falling back to _session_id. These are usually
        # identical, but can diverge when both session_id= and
        # MemoryConfig(session_id=...) are supplied with different values.
        session_id = getattr(self, "_history_session_id", None) or getattr(
            self, "_session_id", None
        )
        if store is None or session_id is None:
            return
        summary = getattr(result, "summary", "") or ""
        if not summary.strip():
            return
        if not hasattr(store, "append_compaction_checkpoint"):
            return
        try:
            store.append_compaction_checkpoint(
                session_id,
                summary,
                tokens_before=getattr(result, "original_tokens", 0) or 0,
                tokens_after=getattr(result, "compacted_tokens", 0) or 0,
            )
        except Exception as e:
            logging.debug(f"Failed to persist compaction checkpoint: {e}")

    def _apply_tool_truncation(self, messages, compactor, policy, log_tag="tool-truncation"):
        """Apply targeted tool output truncation."""
        from ..context.policy import CompactionRoute
        import logging
        
        # Create a copy to avoid modifying original
        truncated_msgs = []
        
        for msg in messages:
            if msg.get("role") == "tool" or msg.get("tool_call_id"):
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 1000:
                    # Truncate large tool outputs
                    truncated_msg = msg.copy()
                    head = content[:300]
                    tail = content[-200:] if len(content) > 500 else ""
                    truncated_msg["content"] = f"{head}\n...[truncated {len(content):,} chars for context budget]...\n{tail}"
                    truncated_msgs.append(truncated_msg)
                    continue
            
            truncated_msgs.append(msg)
        
        original_tokens = compactor.count_total_tokens(messages)
        new_tokens = compactor.count_total_tokens(truncated_msgs)
        
        logging.info(
            f"[{log_tag}] {self.name}: {original_tokens}→{new_tokens} tokens "
            f"(truncated large tool outputs)"
        )
        
        return CompactionRoute.TRUNCATE_TOOLS, truncated_msgs

    async def _compute_context_budget_and_route_async(self, messages, tools=None, system_prompt=None):
        """Async version of _compute_context_budget_and_route."""
        from ..context.policy import CompactionRoute
        from ..compaction import ContextCompactor
        
        # Use shared core logic (synchronous part)
        policy, budget_result = self._compute_context_budget_core(messages, tools, system_prompt)
        
        # If compaction disabled, return unchanged
        if policy is None:
            return CompactionRoute.FITS, messages
        
        # Handle the routing decision
        if budget_result.route == CompactionRoute.FITS:
            return CompactionRoute.FITS, messages
        
        # Need some form of compaction - get max tokens for compactor
        _execution_cfg = getattr(self, 'execution', None)
        max_tokens = getattr(_execution_cfg, 'max_context_tokens', None) if _execution_cfg else None
        if max_tokens is None:
            # Use 90% of available tokens as max to leave room for output
            max_tokens = int(budget_result.available_tokens * 0.9)
        
        # Create compactor with policy-driven settings
        compactor = ContextCompactor(
            max_tokens=max_tokens,
            target_tokens=int(max_tokens * policy.target_utilization),
            preserve_recent=policy.preserve_last_n_turns
        )
        
        # Apply compaction based on route
        if budget_result.route == CompactionRoute.COMPACT_NEEDED:
            return await self._apply_compaction_async(messages, compactor, policy)
        elif budget_result.route == CompactionRoute.TRUNCATE_TOOLS:
            return await self._apply_tool_truncation_async(messages, compactor, policy)
        elif budget_result.route == CompactionRoute.COMPACT_THEN_TRUNCATE:
            # First try compaction
            route, compacted_messages = await self._apply_compaction_async(messages, compactor, policy)
            # If still over budget, also truncate tools
            if compactor.needs_compaction(compacted_messages):
                return await self._apply_tool_truncation_async(compacted_messages, compactor, policy)
            return route, compacted_messages
        
        return CompactionRoute.FITS, messages

    async def _apply_compaction_async(self, messages, compactor, policy):
        """Async version of _apply_compaction."""
        from ..compaction.strategy import CompactionStrategy as LegacyStrategy
        from ..hooks import HookEvent as _HookEvent
        import logging
        
        # Map policy strategy to compactor strategy
        strategy_map = {
            "truncate": LegacyStrategy.TRUNCATE,
            "summarise": LegacyStrategy.SUMMARIZE,
            "drop_oldest_tools": LegacyStrategy.PRUNE,
            "sliding_window": LegacyStrategy.SLIDING,
        }
        
        compactor.strategy = strategy_map.get(policy.strategy.value, LegacyStrategy.PRUNE)
        
        # Execute hooks
        try:
            await self._hook_runner.execute(_HookEvent.BEFORE_COMPACTION, None)
        except Exception as e:
            logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
            if getattr(self, '_strict_hooks', False):
                raise
        
        # Perform compaction
        compacted_msgs, result = compactor.compact(messages)
        
        logging.info(
            f"[proactive-compaction-async] {self.name}: {result.original_tokens}→{result.compacted_tokens} tokens "
            f"({result.messages_removed} messages removed, strategy: {policy.strategy.value})"
        )
        
        try:
            await self._hook_runner.execute(_HookEvent.AFTER_COMPACTION, result)
        except Exception as e:
            logging.warning(f"AFTER_COMPACTION hook failed: {e}")
            if getattr(self, '_strict_hooks', False):
                raise
        
        from ..context.policy import CompactionRoute
        return CompactionRoute.COMPACT_NEEDED, compacted_msgs

    async def _apply_tool_truncation_async(self, messages, compactor, policy):
        """Async wrapper around _apply_tool_truncation (no awaitable work involved)."""
        return self._apply_tool_truncation(messages, compactor, policy, log_tag="tool-truncation-async")

    def _get_next_fallback_model(self, fallback_index):
        """Get the next fallback model from the chain, if available.
        
        Args:
            fallback_index: Current index in the fallback chain (0-based)
            
        Returns:
            str or None: Next model name if available, None otherwise
        """
        if not hasattr(self, 'fallback_models') or not self.fallback_models:
            return None
        if fallback_index >= len(self.fallback_models):
            return None
        return self.fallback_models[fallback_index]

    def _max_retry_depth(self) -> int:
        """Maximum LLM retry depth honoured by the recovery loop.

        Reads ``max_retries`` from the agent's configured ``RetryBackoffConfig``
        (``self._retry_config``) when present, so retry behaviour follows the
        user-configured policy end to end instead of a hardcoded limit. Falls
        back to ``2`` to preserve the previous default when no retry config is
        set.
        """
        retry_config = getattr(self, '_retry_config', None)
        max_retries = getattr(retry_config, 'max_retries', None)
        if isinstance(max_retries, int) and max_retries >= 0:
            return max_retries
        return 2

    def _chat_completion(self, messages, temperature=1.0, tools=None, stream=None, reasoning_steps=False, task_name=None, task_description=None, task_id=None, response_format=None, _retry_depth=0, _fallback_index=0):
        start_time = time.time()

        # --- Proactive Context Budget Management (default-on) ---
        # Analyzes token budget BEFORE LLM call and applies appropriate strategy
        try:
            route, compacted_messages = self._compute_context_budget_and_route(
                messages=messages, 
                tools=tools,
                system_prompt=None  # Already included in messages from _build_messages()
            )
            # Update messages in-place so callers see the changes
            messages[:] = compacted_messages
        except Exception as _ce:
            # Fallback to original messages if proactive handling fails
            if getattr(self, '_strict_hooks', False):
                raise
            logging.debug(f"[proactive-context] fallback to original messages: {_ce}")
        
        # --- Context compaction (opt-in via ExecutionConfig.context_compaction) ---
        # Compacts message history before sending to LLM. Zero overhead when disabled.
        from ..hooks import HookEvent as _HookEvent
        self._apply_context_compaction(messages, _HookEvent)

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
        _before_llm_results = self._hook_runner.execute_sync(HookEvent.BEFORE_LLM, before_llm_input)
        # Honour a blocking BEFORE_LLM hook/plugin (POLICY/GUARDRAIL) by
        # refusing to dispatch the request, mirroring how BEFORE_TOOL/BEFORE_AGENT
        # enforce blocks. Without this, a plugin that returns PluginDecision.deny()
        # (or raises GuardrailBlocked) would fail open and still hit the model.
        if self._hook_runner.is_blocked(_before_llm_results):
            _block_reason = next(
                (getattr(r.output, "reason", None) for r in _before_llm_results
                 if r.output and getattr(r.output, "is_denied", lambda: False)()),
                None,
            ) or "Blocked by hook"
            logging.warning(f"Agent {self.name} LLM request blocked by BEFORE_LLM hook: {_block_reason}")
            return f"[LLM request blocked by hook: {_block_reason}]"
        # C7 - honour any BEFORE_LLM hook that mutated the message stream
        # (e.g. PII redactor). The runner applies modified_input in-place on
        # before_llm_input.messages; adopt that value for the actual LLM call.
        messages = before_llm_input.messages

        # Pre-call budget guard (zero overhead when _max_budget is None).
        # Estimate this call's minimum cost from the known input size plus the
        # configured max_tokens output reservation and refuse to dispatch when
        # it would breach the ceiling. This turns max_budget into a genuine hard
        # cap instead of one that can be overshot by a whole LLM call.
        if self._max_budget and self._on_budget_exceeded == "stop":
            _est_min_cost = self._estimate_min_call_cost(
                messages, getattr(self, 'max_tokens', None)
            )
            with self._cost_lock:
                _projected_cost = self._total_cost + _est_min_cost
                _current_cost = self._total_cost
            if _projected_cost >= self._max_budget:
                raise BudgetExceededError(
                    f"Agent '{self.name}' would exceed budget before call: "
                    f"${_current_cost:.4f} + est ${_est_min_cost:.4f} >= "
                    f"${self._max_budget:.4f}",
                    budget_type="cost",
                    limit=self._max_budget,
                    used=_current_cost,
                    agent_id=self.name
                )

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
        # Let hooks/plugins inspect or rewrite advertised tool definitions
        formatted_tools = self._apply_before_tool_definitions_hook(formatted_tools)

        # Smart fallback for streaming: try streaming first, fall back to non-streaming if unsupported
        streaming_response = None
        if stream is None:
            # Auto-detect: prefer streaming for better UX, fallback if adapter doesn't support it
            try:
                # First attempt: try with streaming enabled for better user experience
                stream_callback = self.stream_emitter.emit if hasattr(self, 'stream_emitter') else None
                streaming_response = self._chat_completion_with_retry(
                    messages=messages,
                    temperature=temperature,
                    tools=formatted_tools,
                    stream=True,  # Try streaming first
                    reasoning_steps=reasoning_steps,
                    task_name=task_name,
                    task_description=task_description,
                    task_id=task_id,
                    response_format=response_format,
                    stream_callback=stream_callback,
                    emit_events=True
                )
            except ValueError as e:
                if "Streaming is not supported" in str(e):
                    # Fallback: retry with non-streaming for sync adapters
                    logging.debug(f"{self.name}: Streaming not supported by adapter, falling back to non-streaming")
                    stream = False  # Set for the main execution below
                else:
                    raise  # Re-raise if it's a different ValueError
            except Exception as e:
                from ..errors import LLMError
                # Don't retry if it's an LLMError that has exhausted retries
                if isinstance(e, LLMError):
                    raise  # Re-raise LLMErrors immediately to avoid double retry
                # For any other exception, fall back to non-streaming
                logging.debug(f"{self.name}: Streaming attempt failed, falling back to non-streaming")
                stream = False  # Set for the main execution below
        
        # If stream was explicitly set or fallback occurred, use the specified/fallback value
        try:
            # NEW: Unified protocol dispatch path (Issue #1304, #1362)
            # UNIFIED: Single protocol-driven dispatch path (fixes DRY violation)
            # All LLM providers now go through unified dispatcher for consistency and maintainability
            stream_callback = self.stream_emitter.emit if hasattr(self, 'stream_emitter') else None
            if streaming_response is not None:
                final_response = streaming_response
            else:
                final_response = self._chat_completion_with_retry(
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
            
            # Emit LLM response trace event on error
            _duration_ms = (time.time() - start_time) * 1000
            _trace_emitter.llm_response(
                self.name,
                duration_ms=_duration_ms,
                finish_reason="error",
                response_content=str(e),  # Include error for context replay
            )
            
            # Use structured error classification for all error types (replaces legacy heuristic checks)
            from ..llm.error_classifier import classify_llm_error
            from ..llm.retry_utils import jittered_backoff
            
            model_name = self.llm if isinstance(self.llm, str) else "unknown"
            session_id = getattr(self, '_session_id', 'unknown')
            
            # Determine provider from model name or use default
            provider = "openai"  # Default assumption
            if "claude" in model_name.lower() or "anthropic" in model_name.lower():
                provider = "anthropic"
            elif "azure" in model_name.lower():
                provider = "azure"
            
            # Get token counts for context-aware classification
            prompt_tokens = 0
            context_length = 0
            try:
                from ..context.tokens import estimate_messages_tokens
                prompt_tokens = estimate_messages_tokens(messages)
                context_length = prompt_tokens
            except Exception:
                pass  # Token estimation failed, continue without counts
            
            # Classify error with structured recovery hints
            classification = classify_llm_error(
                e,
                provider=provider,
                model=model_name,
                prompt_tokens=prompt_tokens,
                context_length=context_length,
                retry_depth=_retry_depth,
            )
            
            # Execute recovery actions based on classification
            if classification.should_compress_context and self.context_manager:
                try:
                    from ..context.budgeter import get_model_limit
                    model_limit = get_model_limit(model_name)
                    target = int(model_limit * 0.7)  # Target 70% of limit for safety
                    
                    # Apply emergency truncation
                    truncated_messages = self.context_manager.emergency_truncate(messages, target)
                    
                    logging.info(f"[{self.name}] {classification.user_message}")
                    
                    # Retry with compressed context (recursive call, bounded by configured policy)
                    if _retry_depth < self._max_retry_depth():
                        return self._chat_completion(
                            truncated_messages, temperature, tools, stream, 
                            reasoning_steps, task_name, task_description, task_id, response_format, 
                            _retry_depth=_retry_depth + 1,
                            _fallback_index=_fallback_index
                        )
                except Exception as compression_error:
                    logging.error(f"[{self.name}] Context compression failed: {compression_error}")
            
            if classification.should_rotate_credential:
                # TODO: Implement credential rotation when available
                logging.warning(f"[{self.name}] {classification.user_message} (credential rotation not yet implemented)")
                # Don't retry without actual credential rotation
                
            elif classification.should_fallback_model:
                # Try next model in the fallback chain
                next_model = self._get_next_fallback_model(_fallback_index)
                if next_model:
                    current_model = self.llm if isinstance(self.llm, str) else str(self.llm)
                    logging.info(f"[{self.name}] {current_model} unavailable — falling back to {next_model}")
                    
                    # Apply backoff if suggested
                    if classification.backoff_seconds and classification.backoff_seconds > 0:
                        time.sleep(classification.backoff_seconds)
                    
                    # Temporarily override the model and clear dispatcher cache for this call
                    original_llm = self.llm
                    original_dispatcher = getattr(self, '_unified_dispatcher', None)
                    try:
                        self.llm = next_model
                        self._unified_dispatcher = None  # Force recreation with new model
                        return self._chat_completion(
                            messages, temperature, tools, stream,
                            reasoning_steps, task_name, task_description, task_id, response_format,
                            _retry_depth=_retry_depth + 1,
                            _fallback_index=_fallback_index + 1
                        )
                    finally:
                        self.llm = original_llm
                        self._unified_dispatcher = original_dispatcher  # Restore original dispatcher
                else:
                    logging.warning(f"[{self.name}] {classification.user_message} (no more fallback models available)")
                    # Continue to error handling without retry
                
            elif classification.is_retryable and classification.backoff_seconds > 0:
                if _retry_depth < self._max_retry_depth():  # Bounded by configured RetryBackoffConfig.max_retries
                    logging.info(f"[{self.name}] {classification.user_message} (waiting {classification.backoff_seconds:.1f}s)")
                    time.sleep(classification.backoff_seconds)
                    return self._chat_completion(
                        messages, temperature, tools, stream, 
                        reasoning_steps, task_name, task_description, task_id, response_format, 
                        _retry_depth=_retry_depth + 1,
                        _fallback_index=_fallback_index
                    )
            
            # Include remediation hints for unimplemented recovery actions
            user_message = classification.user_message
            if classification.should_rotate_credential:
                user_message += " Credential rotation is not yet implemented."
            if classification.should_fallback_model:
                if not self.fallback_models:
                    user_message += " No fallback models configured."
                elif _fallback_index >= len(self.fallback_models):
                    user_message += f" All {len(self.fallback_models)} fallback models exhausted."
            
            # Create LLMError with classification context
            error = LLMError(
                str(e),
                model_name=model_name,
                agent_id=self.name,
                is_retryable=classification.is_retryable,
                context={
                    "session_id": session_id,
                    "error_category": classification.error_category,
                    "user_message": user_message,
                },
            )
            
            # Call error hook if available for error interception
            if hasattr(self, 'on_error') and self.on_error:
                try:
                    self.on_error(error)
                except Exception as hook_error:
                    logging.debug(f"Error in on_error hook: {hook_error}")
            
            raise error from e

    async def _handle_async_llm_error(
        self, 
        exc: Exception, 
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
        _retry_depth=0,
        _fallback_index=0
    ):
        """
        Handle LLM errors in async context using structured classification.
        Mirrors the sync error handling logic but with async-compatible primitives.
        """
        import asyncio
        from ..llm.error_classifier import classify_llm_error
        from ..errors import LLMError
        
        model_name = self.llm if isinstance(self.llm, str) else "unknown"
        session_id = getattr(self, '_session_id', 'unknown')
        
        # Determine provider from model name or use default
        provider = "openai"  # Default assumption
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "azure" in model_name.lower():
            provider = "azure"
        
        # Get token counts for context-aware classification
        prompt_tokens = 0
        context_length = 0
        try:
            from ..context.tokens import estimate_messages_tokens
            prompt_tokens = estimate_messages_tokens(messages)
            context_length = prompt_tokens
        except Exception:
            pass  # Token estimation failed, continue without counts
        
        # Classify error with structured recovery hints
        classification = classify_llm_error(
            exc,
            provider=provider,
            model=model_name,
            prompt_tokens=prompt_tokens,
            context_length=context_length,
            retry_depth=_retry_depth,
        )
        
        # Execute recovery actions based on classification (async-compatible)
        if classification.should_compress_context and self.context_manager:
            try:
                from ..context.budgeter import get_model_limit
                model_limit = get_model_limit(model_name)
                target = int(model_limit * 0.7)  # Target 70% of limit for safety
                
                # Apply emergency truncation
                truncated_messages = self.context_manager.emergency_truncate(messages, target)
                
                logging.info(f"[{self.name}] {classification.user_message}")
                
                # Retry with compressed context (recursive call, bounded by configured policy)
                if _retry_depth < self._max_retry_depth():
                    # Need to call the full async method that includes error handling
                    try:
                        return await self._execute_unified_achat_completion(
                            truncated_messages, temperature, tools, stream, 
                            reasoning_steps, task_name, task_description, task_id, response_format,
                            stream_callback, emit_events
                        )
                    except Exception as retry_error:
                        return await self._handle_async_llm_error(
                            retry_error, truncated_messages, temperature, tools, stream,
                            reasoning_steps, task_name, task_description, task_id, response_format,
                            stream_callback, emit_events, _retry_depth + 1, _fallback_index
                        )
            except Exception as compression_error:
                logging.error(f"[{self.name}] Context compression failed: {compression_error}")
        
        if classification.should_rotate_credential:
            # TODO: Implement credential rotation when available
            logging.warning(f"[{self.name}] {classification.user_message} (credential rotation not yet implemented)")
            # Don't retry without actual credential rotation
            
        elif classification.should_fallback_model:
            # Try next model in the fallback chain
            next_model = self._get_next_fallback_model(_fallback_index)
            if next_model:
                current_model = self.llm if isinstance(self.llm, str) else str(self.llm)
                logging.info(f"[{self.name}] {current_model} unavailable — falling back to {next_model}")
                
                # Apply backoff if suggested
                if classification.backoff_seconds and classification.backoff_seconds > 0:
                    await asyncio.sleep(classification.backoff_seconds)
                
                # Temporarily override the model and clear dispatcher cache for this call
                original_llm = self.llm
                original_dispatcher = getattr(self, '_unified_dispatcher', None)
                try:
                    self.llm = next_model
                    self._unified_dispatcher = None  # Force recreation with new model
                    return await self._execute_unified_achat_completion(
                        messages, temperature, tools, stream,
                        reasoning_steps, task_name, task_description, task_id, response_format,
                        stream_callback, emit_events
                    )
                except Exception as retry_error:
                    return await self._handle_async_llm_error(
                        retry_error, messages, temperature, tools, stream,
                        reasoning_steps, task_name, task_description, task_id, response_format,
                        stream_callback, emit_events, _retry_depth + 1, _fallback_index + 1
                    )
                finally:
                    self.llm = original_llm
                    self._unified_dispatcher = original_dispatcher  # Restore original dispatcher
            else:
                logging.warning(f"[{self.name}] {classification.user_message} (no more fallback models available)")
                # Continue to error handling without retry
            
        elif classification.is_retryable and classification.backoff_seconds > 0:
            if _retry_depth < self._max_retry_depth():  # Bounded by configured RetryBackoffConfig.max_retries
                logging.info(f"[{self.name}] {classification.user_message} (waiting {classification.backoff_seconds:.1f}s)")
                await asyncio.sleep(classification.backoff_seconds)
                # Need to call the full async method that includes error handling
                try:
                    return await self._execute_unified_achat_completion(
                        messages, temperature, tools, stream, 
                        reasoning_steps, task_name, task_description, task_id, response_format,
                        stream_callback, emit_events
                    )
                except Exception as retry_error:
                    return await self._handle_async_llm_error(
                        retry_error, messages, temperature, tools, stream,
                        reasoning_steps, task_name, task_description, task_id, response_format,
                        stream_callback, emit_events, _retry_depth + 1, _fallback_index
                    )
        
        # Include remediation hints for unimplemented recovery actions
        user_message = classification.user_message
        if classification.should_rotate_credential:
            user_message += " Credential rotation is not yet implemented."
        if classification.should_fallback_model:
            if not self.fallback_models:
                user_message += " No fallback models configured."
            elif _fallback_index >= len(self.fallback_models):
                user_message += f" All {len(self.fallback_models)} fallback models exhausted."
        
        # Create LLMError with classification context
        error = LLMError(
            str(exc),
            model_name=model_name,
            agent_id=self.name,
            is_retryable=classification.is_retryable,
            context={
                "session_id": session_id,
                "error_category": classification.error_category,
                "user_message": user_message,
            },
        )
        
        # Call error hook if available for error interception
        if hasattr(self, 'on_error') and self.on_error:
            try:
                # Note: calling sync hook from async context - this is intentional
                # for backward compatibility with existing hook implementations
                self.on_error(error)
            except Exception as hook_error:
                logging.debug(f"Error in on_error hook: {hook_error}")
        
        # Raise the enriched error
        raise error

    def _execute_unified_chat_completion(
        self, 
        messages, 
        temperature=1.0, 
        tools=None, 
        stream=None,
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
        
        This method provides a unified dispatch for all LLM providers using
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
        
        # Smart fallback for streaming: try streaming first, fall back to non-streaming if unsupported
        if stream is None:
            # Auto-detect: prefer streaming for better UX, fallback if adapter doesn't support it
            try:
                # First attempt: try with streaming enabled for better user experience
                if stream_callback is None and hasattr(self, 'stream_emitter'):
                    stream_callback = getattr(self.stream_emitter, 'emit', None)
                final_response = self._unified_dispatcher.chat_completion(
                    messages=messages,
                    tools=tools,
                    tool_choice=getattr(self, 'tool_choice', None),
                    temperature=temperature,
                    max_tokens=getattr(self, 'max_tokens', None),
                    stream=True,  # Try streaming first
                    response_format=response_format,
                    execute_tool_fn=getattr(self, 'execute_tool', None),
                    console=self.console if (self.verbose or True) else None,  # Enable console for streaming
                    display_fn=self._display_generating if self.verbose else None,
                    stream_callback=stream_callback,
                    emit_events=emit_events,
                    verbose=self.verbose,
                    max_iterations=self._resolve_max_steps(),
                    reasoning_steps=reasoning_steps,
                    task_name=task_name,
                    task_description=task_description,
                    task_id=task_id,
                    agent_name=getattr(self, 'name', 'assistant')
                )
                return final_response
            except ValueError as e:
                if "Streaming is not supported" in str(e):
                    # Fallback: retry with non-streaming for sync adapters
                    logging.debug(f"Agent: Streaming not supported by adapter, falling back to non-streaming")
                    stream = False  # Set for the main execution below
                else:
                    raise  # Re-raise if it's a different ValueError
            except Exception:
                # For any other exception, fall back to non-streaming
                logging.debug(f"Agent: Streaming attempt failed, falling back to non-streaming")
                stream = False  # Set for the main execution below

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
                max_iterations=self._resolve_max_steps(),
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
        stream=True,  # Async methods keep stream=True default (async adapters support streaming vs sync smart fallback)
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
        
        This method provides a unified async dispatch for all LLM providers using
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

        # Pre-call budget guard (parity with sync _chat_completion). Bots and
        # other async callers route through here, not _chat_completion.
        if self._max_budget and self._on_budget_exceeded == "stop":
            _est_min_cost = self._estimate_min_call_cost(
                messages, getattr(self, 'max_tokens', None)
            )
            with self._cost_lock:
                _projected_cost = self._total_cost + _est_min_cost
                _current_cost = self._total_cost
            if _projected_cost >= self._max_budget:
                raise BudgetExceededError(
                    f"Agent '{self.name}' would exceed budget before call: "
                    f"${_current_cost:.4f} + est ${_est_min_cost:.4f} >= "
                    f"${self._max_budget:.4f}",
                    budget_type="cost",
                    limit=self._max_budget,
                    used=_current_cost,
                    agent_id=self.name
                )
        
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
                execute_tool_fn=getattr(self, 'execute_tool_async', None),
                console=self.console if (self.verbose or stream) else None,
                display_fn=self._display_generating if self.verbose else None,
                stream_callback=stream_callback,
                emit_events=emit_events,
                verbose=self.verbose,
                max_iterations=self._resolve_max_steps(),
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

            # Post-call budget accounting (parity with sync _chat_completion).
            _prompt_tokens = 0
            _completion_tokens = 0
            _cost_usd = 0.0
            if final_response:
                _usage = getattr(final_response, 'usage', None)
                if _usage:
                    _prompt_tokens = getattr(_usage, 'prompt_tokens', 0) or 0
                    _completion_tokens = getattr(_usage, 'completion_tokens', 0) or 0
                    _cost_usd = self._calculate_llm_cost(
                        _prompt_tokens, _completion_tokens, response=final_response
                    )
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

            return final_response

        except BudgetExceededError:
            raise
        except Exception as e:
            from ..errors import LLMError
            # Apply the same structured error classification for async path
            return await self._handle_async_llm_error(
                e, messages, temperature, tools, stream, reasoning_steps,
                task_name, task_description, task_id, response_format, stream_callback, emit_events
            )

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
            # First check if compression will be needed
            self.context_manager._ledger.reset()
            if system_prompt:
                self.context_manager._ledger.track_system_prompt(system_prompt)
            if tools:
                self.context_manager._ledger.track_tools(tools or [])
            self.context_manager._ledger.track_history(messages)
            
            utilization = self.context_manager._ledger.get_utilization()
            needs_optimization = utilization >= self.context_manager.config.compact_threshold
            
            # Only call on_pre_compress hook when compression will actually occur
            if needs_optimization and self._memory_instance:
                try:
                    # Try async version first if in async context, fallback to sync
                    import asyncio
                    summary = ""
                    try:
                        loop = asyncio.get_running_loop()
                        # In async context - run async hook if available
                        if hasattr(self._memory_instance, 'aon_pre_compress'):
                            # Schedule async hook without blocking
                            task = asyncio.create_task(self._memory_instance.aon_pre_compress(messages))
                            # For now, we'll run sync hook to avoid blocking
                            # TODO: Make this method async-aware or run async hook in background
                            if hasattr(self._memory_instance, 'on_pre_compress'):
                                summary = self._memory_instance.on_pre_compress(messages)
                        elif hasattr(self._memory_instance, 'on_pre_compress'):
                            summary = self._memory_instance.on_pre_compress(messages)
                    except RuntimeError:
                        # Not in async context - use sync hook
                        if hasattr(self._memory_instance, 'on_pre_compress'):
                            summary = self._memory_instance.on_pre_compress(messages)
                    
                    if summary:
                        logging.debug(f"[{self.name}] Memory provider extracted: {summary[:100]}...")
                except Exception as e:
                    logging.warning(f"[{self.name}] Memory on_pre_compress hook failed: {e}")
            
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

    def _truncate_tool_output(self, tool_name: str, output: str, tool_call_id: str | None = None) -> str:
        """
        Truncate tool output according to configured budget.
        
        Zero overhead when context=False.
        
        Args:
            tool_name: Name of the tool
            output: Raw tool output
            tool_call_id: Optional ID for the tool call
            
        Returns:
            Truncated output if over budget, otherwise original
        """
        if not self.context_manager:
            return output
        
        try:
            run_id = getattr(self, '_run_id', None)
            return self.context_manager.truncate_tool_output(tool_name, output, tool_call_id, run_id)
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

    def chat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None, output_json: Optional[Any] = None, output_pydantic: Optional[Any] = None, reasoning_steps: bool = False, stream: Optional[bool] = None, task_name: Optional[str] = None, task_description: Optional[str] = None, task_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None, force_retrieval: bool = False, skip_retrieval: bool = False, attachments: Optional[List[str]] = None, tool_choice: Optional[str] = None, seed: Optional[int] = None, cancel_token: Optional[Any] = None) -> Optional[str]:
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

        # Check for steering messages before processing
        if hasattr(self, '_check_steering_messages'):
            try:
                steering_msg = self._check_steering_messages()
                if steering_msg:
                    # Inject steering message into prompt with clear separator
                    prompt = f"{prompt}\n\n{steering_msg}"
            except Exception as e:
                logger.warning(f"Steering check failed, continuing without steering: {e}")

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
            # C2 - cooperative cancellation: abort early if a pre-set token is given
            _cancel = cancel_token if cancel_token is not None else getattr(self, "interrupt_controller", None)
            if _cancel is not None and getattr(_cancel, "is_set", lambda: False)():
                reason = getattr(_cancel, "reason", None) or "cancelled before LLM call"
                raise InterruptedError(f"Agent chat cancelled: {reason}")

            return self._chat_impl(prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice, seed=seed, cancel_token=_cancel)
        finally:
            _trace_emitter.agent_end(self.name)

    def _chat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None, seed=None, cancel_token=None):
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
            if res.output and res.output.modified_input and "prompt" in res.output.modified_input:
                prompt = res.output.modified_input["prompt"]
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
                # Security fix: Distinguish None (inherit) vs [] (explicit deny)
                if tools is None:
                    # None means inherit agent's configured tools
                    tool_param = self.tools
                elif isinstance(tools, list) and len(tools) == 0:
                    # Empty list means explicitly deny all tools (security boundary)
                    tool_param = []
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
                    # --- Proactive Context Budget Management (sync custom LLM path) ---
                    system_prompt_for_llm = self._build_system_prompt(tools)
                    
                    # Apply proactive context budget analysis before any other processing
                    try:
                        route, compacted_history = self._compute_context_budget_and_route(
                            messages=self.chat_history,
                            tools=tool_param,
                            system_prompt=None  # Already included in messages from _build_messages()
                        )
                        # Use compacted history for further processing
                        working_history = compacted_history
                    except Exception as _ce:
                        # Fallback to original chat history if proactive handling fails
                        if getattr(self, '_strict_hooks', False):
                            raise
                        logging.debug(f"[proactive-context-sync] fallback to original history: {_ce}")
                        working_history = self.chat_history
                    
                    # Apply legacy context management on the (possibly compacted) history
                    # Zero overhead when context=False
                    processed_history, context_result = self._apply_context_management(
                        messages=working_history,
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
                        max_tool_calls_per_turn=self._resolve_max_tool_calls(),
                        reasoning_steps=reasoning_steps,
                        stream=stream
                    )
                    
                    # Pass tool_choice if specified (auto, required, none)
                    # Also check for YAML-configured tool_choice on the agent
                    effective_tool_choice = tool_choice or getattr(self, '_yaml_tool_choice', None)
                    if effective_tool_choice:
                        llm_kwargs['tool_choice'] = effective_tool_choice

                    # C1 - per-call seed overrides llm_instance.seed for determinism
                    if seed is not None:
                        llm_kwargs['seed'] = seed

                    # C2 - last-chance cancel check before handing to the LLM
                    if cancel_token is not None and getattr(cancel_token, 'is_set', lambda: False)():
                        reason = getattr(cancel_token, 'reason', None) or 'cancelled'
                        raise InterruptedError(f"Agent chat cancelled: {reason}")

                    # G2 - thread cancel token into the LLM tool loop so /stop halts
                    # mid-flight runs between tool iterations on every provider
                    if cancel_token is not None:
                        llm_kwargs['cancel_token'] = cancel_token

                    # G2 - thread steering drain so pending steering messages are
                    # injected between tool iterations of an in-flight run
                    if hasattr(self, '_drain_steering_messages') and getattr(self, '_message_steering', None) is not None:
                        llm_kwargs['steering_drain'] = self._drain_steering_messages

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

                        response = self._chat_completion(messages, temperature=temperature, tools=tools, reasoning_steps=reasoning_steps, stream=stream, task_name=task_name, task_description=task_description, task_id=task_id, response_format=response_format)
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
                                
                                reflection_output = _get_display_functions()['ReflectionOutput'](**reflection_data)
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
                            # For reflection, always use non-streaming to ensure compatibility with sync adapters
                            # and to avoid streaming complexity during regeneration process
                            use_stream = False
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
        """Clean and extract JSON from response text.
        
        NOTE: This method is duplicated in agents.Agents.clean_json_output.
        Keep both implementations in sync when modifying either.
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

    async def achat(self, prompt: str, temperature: float = 1.0, tools: Optional[List[Any]] = None, output_json: Optional[Any] = None, output_pydantic: Optional[Any] = None, reasoning_steps: bool = False, stream: Optional[bool] = None, task_name: Optional[str] = None, task_description: Optional[str] = None, task_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None, force_retrieval: bool = False, skip_retrieval: bool = False, attachments: Optional[List[str]] = None, tool_choice: Optional[str] = None, seed: Optional[int] = None, cancel_token: Optional[Any] = None):
        """Async version of chat method with self-reflection support.
        
        Args:
            prompt: Text query that WILL be stored in chat_history
            attachments: Optional list of image/file paths that are ephemeral
                        (used for THIS turn only, NEVER stored in history).
        """
        # Slash-command invocation: /skill-name [args] renders the skill body.
        prompt = self._resolve_skill_invocation(prompt)

        # Check for steering messages before processing
        if hasattr(self, '_check_steering_messages'):
            try:
                steering_msg = self._check_steering_messages()
                if steering_msg:
                    # Inject steering message into prompt with clear separator
                    prompt = f"{prompt}\n\n{steering_msg}"
            except Exception as e:
                logger.warning(f"Steering check failed, continuing without steering: {e}")

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
                attachments=attachments, _trace_emitter=_trace_emitter, tool_choice=tool_choice,
                seed=seed, cancel_token=cancel_token
            )
        finally:
            _trace_emitter.agent_end(self.name)

    async def _achat_impl(self, prompt, temperature, tools, output_json, output_pydantic, reasoning_steps, stream, task_name, task_description, task_id, config, force_retrieval, skip_retrieval, attachments, _trace_emitter, tool_choice=None, seed=None, cancel_token=None):
        """Internal async chat implementation (extracted for trace wrapping)."""
        # C2 - cooperative cancellation: abort early if a pre-set token is given
        _cancel = cancel_token if cancel_token is not None else getattr(self, "interrupt_controller", None)
        if _cancel is not None and getattr(_cancel, "is_set", lambda: False)():
            reason = getattr(_cancel, "reason", None) or "cancelled before LLM call"
            raise InterruptedError(f"Agent chat cancelled: {reason}")
        
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
            if res.output and res.output.modified_input and "prompt" in res.output.modified_input:
                prompt = res.output.modified_input["prompt"]
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

                # --- Proactive Context Budget Management (async custom LLM path) ---
                try:
                    route, compacted_history = await self._compute_context_budget_and_route_async(
                        messages=self.chat_history,
                        tools=tools,
                        system_prompt=None  # Already included in messages from _build_messages()
                    )
                    # Keep compacted history local until success - don't mutate shared state yet
                    effective_history = compacted_history
                except Exception as _ce:
                    if getattr(self, '_strict_hooks', False):
                        raise
                    logging.debug(f"[proactive-context-async] fallback: {_ce}")
                    effective_history = self.chat_history
                    
                # --- Context compaction (async custom LLM path) ---
                from ..hooks import HookEvent as _HE
                compacted = await self._apply_context_compaction_async(self.chat_history, _HE)
                if compacted:
                    # Use the modified chat_history after compaction
                    pass

                try:
                    # C1 - per-call seed forwarding (async path)  
                    llm_kwargs = {
                        'prompt': prompt,
                        'system_prompt': self._build_system_prompt(tools),
                        'chat_history': effective_history,
                        'temperature': temperature,
                        'tools': tools,
                        'output_json': output_json,
                        'output_pydantic': output_pydantic,
                        'verbose': self.verbose,
                        'markdown': self.markdown,
                        'reflection': self.self_reflect,
                        'max_reflect': self.max_reflect,
                        'min_reflect': self.min_reflect,
                        'console': self.console,
                        'agent_name': self.name,
                        'agent_role': self.role,
                        'agent_tools': [t.__name__ if hasattr(t, '__name__') else str(t) for t in (tools if tools is not None else self.tools)],
                        'task_name': task_name,
                        'task_description': task_description,
                        'task_id': task_id,
                        'execute_tool_fn': self.execute_tool_async,
                        'parallel_tool_calls': getattr(getattr(self, "execution", None), "parallel_tool_calls", False),
                        'max_tool_calls_per_turn': self._resolve_max_tool_calls(),
                        'reasoning_steps': reasoning_steps,
                        'stream': stream
                    }
                    
                    # C1 - per-call seed overrides llm_instance.seed for determinism  
                    if seed is not None:
                        llm_kwargs['seed'] = seed
                    
                    # C2 - last-chance cancel check before handing to the LLM
                    if _cancel is not None and getattr(_cancel, 'is_set', lambda: False)():
                        reason = getattr(_cancel, 'reason', None) or 'cancelled'
                        raise InterruptedError(f"Agent chat cancelled: {reason}")

                    # G2 - thread cancel token into the LLM tool loop so /stop halts
                    # mid-flight runs between tool iterations on every provider
                    if _cancel is not None:
                        llm_kwargs['cancel_token'] = _cancel

                    # G2 - thread steering drain so pending steering messages are
                    # injected between tool iterations of an in-flight run
                    if hasattr(self, '_drain_steering_messages') and getattr(self, '_message_steering', None) is not None:
                        llm_kwargs['steering_drain'] = self._drain_steering_messages

                    response_text = await self.llm_instance.get_response_async(**llm_kwargs)

                    # LLM call succeeded - now it's safe to commit any compacted history
                    if effective_history is not self.chat_history:
                        self._replace_chat_history(effective_history)

                    self._append_to_chat_history({"role": "assistant", "content": response_text})

                    if get_logger().getEffectiveLevel() == logging.DEBUG:
                        total_time = time.time() - start_time
                        logging.debug(f"Agent.achat completed in {total_time:.2f} seconds")
                    
                    # Apply guardrail validation for custom LLM response
                    try:
                        validated_response = await self._aapply_guardrail_with_retry(response_text, prompt, temperature, tools, task_name, task_description, task_id)
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

            # --- Proactive Context Budget Management (async standard OpenAI path) ---
            try:
                route, compacted_messages = await self._compute_context_budget_and_route_async(
                    messages=messages,
                    tools=tools,
                    system_prompt=None  # Already included in messages from _build_messages()
                )
                messages[:] = compacted_messages
            except Exception as _ce2:
                if getattr(self, '_strict_hooks', False):
                    raise
                logging.debug(f"[proactive-context-async-standard] fallback: {_ce2}")
                
            # --- Context compaction (async standard OpenAI path) ---
            from ..hooks import HookEvent as _HE2
            await self._apply_context_compaction_async(messages, _HE2)

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
                    # Let hooks/plugins inspect or rewrite advertised tool definitions
                    formatted_tools = await self._aapply_before_tool_definitions_hook(formatted_tools)
                    
                    # NEW: Unified protocol dispatch path (Issue #1304) - Async version
                    # Enable unified dispatch by default for DRY and feature parity (sync/async consistent)
                    if getattr(self, '_use_unified_llm_dispatch', True):
                        # Build response_format for native structured output (parity with sync path)
                        schema_model = output_pydantic or output_json
                        response_format = None
                        if schema_model and self._supports_native_structured_output():
                            response_format = self._build_response_format(schema_model)
                        
                        # Use composition instead of runtime class mutation for safety
                        response = await self._achat_completion_with_retry(
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
                        
                        # Process response - mirror sync _chat_impl behavior (lines ~1544-1602)
                        if not response:
                            # Rollback chat history on response failure
                            self._truncate_chat_history(chat_history_length)
                            return None

                        # Extract response content using the same method as sync
                        response_text = self._extract_llm_response_content(response)
                        if isinstance(response_text, str):
                            response_text = response_text.strip()

                        # Handle output_json or output_pydantic if specified
                        if output_json or output_pydantic:
                            # Add to chat history and return raw response
                            # User message already added before LLM call via _build_messages
                            self._append_to_chat_history({"role": "assistant", "content": response_text})
                            # Persist assistant message to DB
                            self._persist_message("assistant", response_text)
                            # Apply guardrail validation even for JSON output
                            try:
                                validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                # Execute callback after validation
                                self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                            except Exception as e:
                                logging.error(f"Agent {self.name}: Guardrail validation failed for JSON output: {e}")
                                # Rollback chat history on guardrail failure
                                self._truncate_chat_history(chat_history_length)
                                return None

                        # For regular responses (no self-reflection)
                        if not self.self_reflect:
                            # User message already added before LLM call via _build_messages
                            self._append_to_chat_history({"role": "assistant", "content": response_text})
                            # Persist assistant message to DB (non-reflect path)
                            self._persist_message("assistant", response_text)
                            if self.verbose:
                                logging.debug(f"Agent {self.name} final response: {response_text}")
                            # Return only reasoning content if reasoning_steps is True
                            if reasoning_steps and hasattr(response, 'choices') and response.choices and hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
                                # Apply guardrail to reasoning content
                                try:
                                    validated_reasoning = await self._aapply_guardrail_with_retry(response.choices[0].message.reasoning_content, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_reasoning, time.time() - start_time, task_name, task_description, task_id)
                                    return await self._atrigger_after_agent_hook(original_prompt, validated_reasoning, start_time)
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed for reasoning content: {e}")
                                    # Rollback chat history on guardrail failure
                                    self._truncate_chat_history(chat_history_length)
                                    return None
                            else:
                                # Apply guardrail to regular response content
                                try:
                                    validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                    # Execute callback after validation
                                    self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                    return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                                except Exception as e:
                                    logging.error(f"Agent {self.name}: Guardrail validation failed: {e}")
                                    # Rollback chat history on guardrail failure
                                    self._truncate_chat_history(chat_history_length)
                                    return None
                        
                        # If self-reflection is enabled, implement reflection logic
                        if self.self_reflect:
                            # Implement async self-reflection similar to sync path
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
                            
                            reflection_count = 0
                            
                            while True:
                                try:
                                    # Check if OpenAI client is available for self-reflection
                                    if self._openai_client is None:
                                        # For custom LLMs, self-reflection with structured output is not supported
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection'](f"Agent {self.name}: Self-reflection with structured output is not supported for custom LLM providers. Skipping reflection.", console=self.console)
                                        # Return the original response without reflection
                                        self._append_to_chat_history({"role": "assistant", "content": response_text})
                                        # Persist assistant message to DB
                                        self._persist_message("assistant", response_text)
                                        try:
                                            validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                            # Execute callback after validation
                                            self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                            return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                                        except Exception as e:
                                            logging.error(f"Agent {self.name}: Guardrail validation failed: {e}")
                                            # Rollback chat history on guardrail failure
                                            self._truncate_chat_history(chat_history_length)
                                            return None
                                    
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
                                        # Add to chat history and return
                                        self._append_to_chat_history({"role": "assistant", "content": response_text})
                                        # Persist assistant message to DB
                                        self._persist_message("assistant", response_text)
                                        try:
                                            validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                            # Execute callback after validation
                                            self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                            return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                                        except Exception as e:
                                            logging.error(f"Agent {self.name}: Guardrail validation failed after reflection: {e}")
                                            # Rollback chat history on guardrail failure
                                            self._truncate_chat_history(chat_history_length)
                                            return None
                                    
                                    # Check if we've hit max reflections
                                    if reflection_count >= self.max_reflect - 1:
                                        if self.verbose:
                                            _get_display_functions()['display_self_reflection']("Maximum reflection count reached, returning current response", console=self.console)
                                        # Add to chat history and return
                                        self._append_to_chat_history({"role": "assistant", "content": response_text})
                                        # Persist assistant message to DB
                                        self._persist_message("assistant", response_text)
                                        try:
                                            validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                            # Execute callback after validation
                                            self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                            return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                                        except Exception as e:
                                            logging.error(f"Agent {self.name}: Guardrail validation failed after max reflections: {e}")
                                            # Rollback chat history on guardrail failure
                                            self._truncate_chat_history(chat_history_length)
                                            return None
                                    
                                    # Regenerate response based on reflection
                                    regenerate_messages = reflection_messages + [
                                        {"role": "assistant", "content": f"Self Reflection: {reflection_output.reflection} Satisfactory?: {reflection_output.satisfactory}"},
                                        {"role": "user", "content": "Now regenerate your response using the reflection you made"}
                                    ]
                                    
                                    new_response = await self._achat_completion_with_retry(
                                        messages=regenerate_messages,
                                        temperature=temperature,
                                        tools=formatted_tools,
                                        stream=stream,
                                        reasoning_steps=reasoning_steps,
                                        task_name=task_name,
                                        task_description=task_description,
                                        task_id=task_id,
                                        response_format=response_format
                                    )
                                    
                                    if new_response:
                                        new_response_text = self._extract_llm_response_content(new_response)
                                        if isinstance(new_response_text, str):
                                            response_text = new_response_text.strip()
                                        # Update reflection_messages to include the new response for next iteration
                                        reflection_messages = regenerate_messages + [
                                            {"role": "assistant", "content": response_text}
                                        ]
                                    
                                    reflection_count += 1
                                    
                                except Exception as e:
                                    if self.verbose:
                                        _get_display_functions()['display_error'](f"Error in parsing self-reflection json {e}. Retrying", console=self.console)
                                    logging.error("Reflection parsing failed.", exc_info=True)
                                    reflection_count += 1
                                    if reflection_count >= self.max_reflect:
                                        # Return original response after max reflection attempts
                                        self._append_to_chat_history({"role": "assistant", "content": response_text})
                                        # Persist assistant message to DB
                                        self._persist_message("assistant", response_text)
                                        try:
                                            validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
                                            # Execute callback after validation
                                            self._execute_callback_and_display(original_prompt, validated_response, time.time() - start_time, task_name, task_description, task_id)
                                            return await self._atrigger_after_agent_hook(original_prompt, validated_response, start_time)
                                        except Exception as guard_e:
                                            logging.error(f"Agent {self.name}: Guardrail validation failed after reflection error: {guard_e}")
                                            # Rollback chat history on guardrail failure
                                            self._truncate_chat_history(chat_history_length)
                                            return None
                                    continue
                        
                        # This should never be reached due to the returns above
                        # But adding as safety fallback
                        logging.warning(f"Agent {self.name}: Unexpected code path reached in unified dispatch")
                        return None
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
                            validated_response = await self._aapply_guardrail_with_retry(response_text, original_prompt, temperature, tools, task_name, task_description, task_id)
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
                        _tool_blocked = self._hook_runner.is_blocked(_before_results)
                    except Exception as _hook_err:
                        logging.debug(f"BEFORE_TOOL hook error (non-fatal): {_hook_err}")
                        _tool_blocked = False
                    if _tool_blocked:
                        # Reason extraction must not be able to re-open a block:
                        # use attributes present on both HookResult (plugin
                        # bridge) and HookOutput, defaulting safely.
                        _block_reason = next(
                            (getattr(r.output, "reason", None) for r in _before_results
                             if r.output and getattr(r.output, "is_denied", lambda: False)()),
                            None,
                        ) or "Blocked by hook"
                        results.append(f"[Tool blocked by hook: {_block_reason}]")
                        continue

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
                        parallel_tool_calls=getattr(getattr(self, "execution", None), "parallel_tool_calls", False),
                        max_tool_calls_per_turn=self._resolve_max_tool_calls()
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
                        
                        # Execute tool calls and add results to chat history.
                        # Media-bearing follow-up messages are deferred until all
                        # tool replies for this turn are appended, keeping the
                        # tool replies consecutive (provider contract).
                        _deferred_media_followups = []
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
                                    # Add tool result to chat history (multimodal-aware)
                                    from .tool_execution import build_tool_result_message_pair
                                    _pair = build_tool_result_message_pair(
                                        tool_result, tool_call['id'],
                                        function_name=tool_call['function']['name'],
                                    )
                                    if _pair:
                                        _tool_msg, _followup_msg = _pair
                                        self._append_to_chat_history(_tool_msg)
                                        _deferred_media_followups.append(_followup_msg)
                                    else:
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

                        # Flush deferred media follow-ups after all tool replies.
                        for _m in _deferred_media_followups:
                            self._append_to_chat_history(_m)
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

    def _create_llm_summarize_function(self):
        """
        Create an async LLM summarization function for context compaction.
        
        Returns a callable that takes a prompt and returns an LLM response.
        """
        async def llm_summarize_async(prompt: str) -> str:
            """Call the agent's LLM to summarize text."""
            try:
                # Use the agent's unified chat completion for summarization
                summary_messages = [
                    {"role": "user", "content": prompt}
                ]
                
                response = await self._execute_unified_achat_completion(
                    messages=summary_messages,
                    temperature=0.3,  # Lower temperature for more consistent summaries
                    tools=None,  # No tools for summarization
                    stream=False,  # No streaming for internal summarization
                    emit_events=False,  # Don't emit events for internal calls
                )
                
                # Extract the content from response using existing method
                extracted = self._extract_llm_response_content(response)
                if not extracted or not str(extracted).strip():
                    raise ValueError("LLM summarization returned empty content")
                return str(extracted).strip()
                    
            except Exception as e:
                logging.warning(f"LLM summarization call failed: {e}")
                raise
        
        return llm_summarize_async

    def _apply_context_compaction(self, messages, hook_event_class):
        """
        Apply context compaction to messages if enabled (sync version).
        
        Args:
            messages: List of messages to potentially compact
            hook_event_class: Hook event class to use for before/after hooks
            
        Returns:
            bool: True if compaction was applied, False otherwise
        """
        _execution_cfg = getattr(self, 'execution', None)
        if not (_execution_cfg and getattr(_execution_cfg, 'context_compaction', False)):
            return False
            
        try:
            from ..compaction import ContextCompactor
            from ..compaction.strategy import CompactionStrategy
            
            _max_tok = getattr(_execution_cfg, 'max_context_tokens', None) or 8000
            _strategy = getattr(_execution_cfg, 'compaction_strategy', None) or CompactionStrategy.TRUNCATE
            
            # Create LLM summarization function if strategy is LLM_SUMMARIZE
            _llm_fn = None
            if _strategy == CompactionStrategy.LLM_SUMMARIZE:
                try:
                    _llm_fn = self._create_llm_summarize_function()
                except Exception as e:
                    logging.warning(f"Failed to create LLM summarize function: {e}")
            
            _compactor = ContextCompactor(
                max_tokens=_max_tok,
                strategy=_strategy,
                llm_summarize_fn=_llm_fn
            )
            
            if not _compactor.needs_compaction(messages):
                return False
                
            # Execute BEFORE_COMPACTION hook
            try:
                self._hook_runner.execute_sync(hook_event_class.BEFORE_COMPACTION, None)
            except Exception as e:
                logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
                if getattr(self, '_strict_hooks', False):
                    raise
            
            # Perform compaction
            if _strategy == CompactionStrategy.LLM_SUMMARIZE and _llm_fn:
                import asyncio
                try:
                    # Run async compaction in event loop
                    compacted_msgs, _cr = asyncio.run(_compactor.compact_async(messages))
                except RuntimeError:
                    # If already in async context, fall back to sync (naive) compaction
                    logging.warning(
                        f"[compaction] {self.name}: LLM_SUMMARIZE fell back to naive summarization "
                        f"(asyncio.run not available in sync context)"
                    )
                    compacted_msgs, _cr = _compactor.compact(messages)
            else:
                compacted_msgs, _cr = _compactor.compact(messages)
            
            messages[:] = compacted_msgs  # in-place update so callers see the change
            logging.info(
                f"[compaction] {self.name}: {_cr.original_tokens}→{_cr.compacted_tokens} tokens "
                f"({_cr.messages_removed} messages removed, strategy={_cr.strategy_used.value})"
            )
            
            # Execute AFTER_COMPACTION hook  
            try:
                self._hook_runner.execute_sync(hook_event_class.AFTER_COMPACTION, None)
            except Exception as e:
                logging.warning(f"AFTER_COMPACTION hook failed: {e}")
                if getattr(self, '_strict_hooks', False):
                    raise
                    
            return True
            
        except Exception as _ce:
            if getattr(self, '_strict_hooks', False):
                raise
            logging.debug(f"[compaction] skipped (non-fatal): {_ce}")
            return False

    async def _apply_context_compaction_async(self, messages, hook_event_class):
        """
        Apply context compaction to messages if enabled (async version).
        
        Args:
            messages: List of messages to potentially compact
            hook_event_class: Hook event class to use for before/after hooks
            
        Returns:
            bool: True if compaction was applied, False otherwise
        """
        _execution_cfg = getattr(self, 'execution', None)
        if not (_execution_cfg and getattr(_execution_cfg, 'context_compaction', False)):
            return False
            
        try:
            from ..compaction import ContextCompactor
            from ..compaction.strategy import CompactionStrategy
            
            _max_tok = getattr(_execution_cfg, 'max_context_tokens', None) or 8000
            _strategy = getattr(_execution_cfg, 'compaction_strategy', None) or CompactionStrategy.TRUNCATE
            
            # Create LLM summarization function if strategy is LLM_SUMMARIZE
            _llm_fn = None
            if _strategy == CompactionStrategy.LLM_SUMMARIZE:
                try:
                    _llm_fn = self._create_llm_summarize_function()
                except Exception as e:
                    logging.warning(f"Failed to create LLM summarize function: {e}")
            
            _compactor = ContextCompactor(
                max_tokens=_max_tok,
                strategy=_strategy,
                llm_summarize_fn=_llm_fn
            )
            
            if not _compactor.needs_compaction(messages):
                return False
                
            # Execute BEFORE_COMPACTION hook
            try:
                await self._hook_runner.execute(hook_event_class.BEFORE_COMPACTION, None)
            except Exception as e:
                logging.warning(f"BEFORE_COMPACTION hook failed: {e}")
                if getattr(self, '_strict_hooks', False):
                    raise
            
            # Perform compaction (use async version when available)
            if _strategy == CompactionStrategy.LLM_SUMMARIZE and _llm_fn:
                compacted_msgs, _cr = await _compactor.compact_async(messages)
            else:
                compacted_msgs, _cr = _compactor.compact(messages)
            
            # If messages is the same object as chat_history, replace chat history
            # Otherwise, update the passed messages list in-place
            if messages is self.chat_history:
                self._replace_chat_history(compacted_msgs)
            else:
                messages[:] = compacted_msgs
            logging.info(
                f"[compaction] {self.name}: {_cr.original_tokens}→{_cr.compacted_tokens} tokens "
                f"({_cr.messages_removed} messages removed, strategy={_cr.strategy_used.value})"
            )
            
            # Execute AFTER_COMPACTION hook  
            try:
                await self._hook_runner.execute(hook_event_class.AFTER_COMPACTION, None)
            except Exception as e:
                logging.warning(f"AFTER_COMPACTION hook failed: {e}")
                if getattr(self, '_strict_hooks', False):
                    raise
                    
            return True
            
        except Exception as _ce:
            if getattr(self, '_strict_hooks', False):
                raise
            logging.debug(f"[compaction] skipped (non-fatal): {_ce}")
            return False

    def _chat_completion_with_retry(self, messages, temperature=1.0, tools=None, stream=None, reasoning_steps=False, task_name=None, task_description=None, task_id=None, response_format=None, stream_callback=None, emit_events=True):
        """
        Wrapper for _execute_unified_chat_completion that adds jittered exponential backoff retry logic.
        
        This method wraps the unified chat completion call and adds retry capability for 
        transient failures like rate limits, network errors, and service outages.
        """
        retry_config = getattr(self, '_retry_config', None)
        if not retry_config:
            return self._execute_unified_chat_completion(messages, temperature, tools, stream, reasoning_steps, 
                                       task_name, task_description, task_id, response_format,
                                       stream_callback=stream_callback, emit_events=emit_events)
        
        from .retry_utils import jittered_backoff
        from ..hooks import HookEvent, OnRetryInput
        import time
        
        max_attempts = retry_config.max_retries + 1
        
        for attempt in range(max_attempts):
            try:
                # Call the underlying unified chat completion directly to avoid infinite recursion
                return self._execute_unified_chat_completion(messages, temperature, tools, stream, reasoning_steps, 
                                           task_name, task_description, task_id, response_format,
                                           stream_callback=stream_callback, emit_events=emit_events)
            
            except Exception as e:
                from ..errors import LLMError
                
                # Only retry LLMErrors that are marked as retryable
                if not isinstance(e, LLMError) or not e.is_retryable:
                    raise  # Re-raise non-retryable errors immediately
                
                # If this is the last attempt, re-raise the error
                if attempt >= max_attempts - 1:
                    raise
                
                # Calculate delay for this retry attempt
                delay = jittered_backoff(
                    attempt,
                    base_delay=retry_config.base_delay,
                    max_delay=retry_config.max_delay,
                    jitter_ratio=retry_config.jitter_ratio,
                )
                
                # Fire OnRetry hook with delay information
                retry_input = OnRetryInput(
                    session_id=getattr(self, '_session_id', 'default'),
                    cwd=os.getcwd(),
                    event_name=HookEvent.ON_RETRY,
                    timestamp=str(time.time()),
                    agent_name=self.name,
                    retry_count=attempt + 1,
                    max_retries=retry_config.max_retries,
                    error_message=str(e),
                    operation="llm_request",
                    delay_seconds=delay,
                    attempt=attempt
                )
                self._hook_runner.execute_sync(HookEvent.ON_RETRY, retry_input)
                
                # Log retry attempt (buffered to avoid spam during transient failures)
                logger.debug(f"[{self.name}] Retry {attempt + 1}/{max_attempts} after {delay:.1f}s: {str(e)[:100]}")
                
                # Sleep with interrupt awareness - make interruption terminal
                interrupt_fn = getattr(self, '_is_interrupted', lambda: False)
                sleep_start = time.time()
                while time.time() - sleep_start < delay:
                    if interrupt_fn():
                        # Interruption is terminal - stop retrying
                        raise RuntimeError("Agent interrupted during retry backoff")
                    time.sleep(min(0.2, delay - (time.time() - sleep_start)))
        
        # This should never be reached, but just in case
        raise RuntimeError("Retry loop completed without returning or raising an exception")

    async def _achat_completion_with_retry(self, messages, temperature=1.0, tools=None, stream=None, reasoning_steps=False, task_name=None, task_description=None, task_id=None, response_format=None, stream_callback=None, emit_events=True):
        """
        Async wrapper for _execute_unified_achat_completion that adds jittered exponential backoff retry logic.
        
        This method wraps the async chat completion call and adds retry capability for 
        transient failures like rate limits, network errors, and service outages.
        """
        retry_config = getattr(self, '_retry_config', None)
        if not retry_config:
            return await self._execute_unified_achat_completion(
                messages, temperature, tools, stream, reasoning_steps, 
                task_name, task_description, task_id, response_format,
                stream_callback=stream_callback, emit_events=emit_events
            )
        
        from .retry_utils import jittered_backoff, interruptible_sleep
        from ..hooks import HookEvent, OnRetryInput
        import time
        import asyncio
        
        max_attempts = retry_config.max_retries + 1
        
        for attempt in range(max_attempts):
            try:
                # Call the underlying unified chat completion directly to avoid infinite recursion
                return await self._execute_unified_achat_completion(
                    messages, temperature, tools, stream, reasoning_steps,
                    task_name, task_description, task_id, response_format,
                    stream_callback=stream_callback, emit_events=emit_events
                )
            
            except Exception as e:
                from ..errors import LLMError
                
                # Only retry LLMErrors that are marked as retryable
                if not isinstance(e, LLMError) or not e.is_retryable:
                    raise  # Re-raise non-retryable errors immediately
                
                # If this is the last attempt, re-raise the error
                if attempt >= max_attempts - 1:
                    raise
                
                # Calculate delay for this retry attempt
                delay = jittered_backoff(
                    attempt,
                    base_delay=retry_config.base_delay,
                    max_delay=retry_config.max_delay,
                    jitter_ratio=retry_config.jitter_ratio,
                )
                
                # Fire OnRetry hook with delay information
                retry_input = OnRetryInput(
                    session_id=getattr(self, '_session_id', 'default'),
                    cwd=os.getcwd(),
                    event_name=HookEvent.ON_RETRY,
                    timestamp=str(time.time()),
                    agent_name=self.name,
                    retry_count=attempt + 1,
                    max_retries=retry_config.max_retries,
                    error_message=str(e),
                    operation="async_llm_request",
                    delay_seconds=delay,
                    attempt=attempt
                )
                await self._hook_runner.execute_async(HookEvent.ON_RETRY, retry_input)
                
                # Log retry attempt
                logger.debug(f"[{self.name}] Async retry {attempt + 1}/{max_attempts} after {delay:.1f}s: {str(e)[:100]}")
                
                # Async sleep with interrupt awareness using the helper
                interrupt_fn = getattr(self, '_is_interrupted', lambda: False)
                if not await interruptible_sleep(delay, interrupt_fn=interrupt_fn):
                    raise RuntimeError("Agent interrupted during retry backoff")
        
        # This should never be reached, but just in case
        raise RuntimeError("Async retry loop completed without returning or raising an exception")
