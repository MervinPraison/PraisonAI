"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, List, Optional, Tuple

from .._logging import get_logger
from .feature_configs import (
    CachingConfig, ExecutionConfig, GuardrailConfig, HooksConfig, KnowledgeConfig, LearnConfig, LLMConfig,
    MemoryConfig, OutputConfig, PlanningConfig, ReflectionConfig, SkillsConfig, TemplateConfig, WebConfig,
)
from .param_resolver import (
    ArrayMode, resolve, resolve_caching, resolve_execution, resolve_memory, resolve_planning,
    resolve_reflection, resolve_web,
)
from .parse_utils import canonical_preset_key
from .presets import DEFAULT_OUTPUT_MODE, EXECUTION_PRESETS, OUTPUT_PRESETS

logger = get_logger(__name__)


def resolve_agent_caching(caching: Any) -> Tuple[Optional[CachingConfig], bool, Optional[bool]]:
    """``caching=`` -> ``(config, cache, prompt_caching)``.

    ``None`` and ``True`` mean the default (enabled); ``False`` disables it and
    gives no config; presets, dicts and ``CachingConfig`` are resolved as before.
    """
    if caching is None or caching is True:
        config = CachingConfig()
    elif caching is False:
        config = None
    elif isinstance(caching, CachingConfig):
        config = caching
    else:
        config = resolve_caching(caching, CachingConfig, default=CachingConfig())
    if config:
        return config, config.enabled, config.prompt_caching
    if caching is False:
        return None, False, None
    return config, True, None


def resolve_agent_templates(templates: Any) -> Tuple[Optional[TemplateConfig], Optional[str], Optional[str], Optional[str], bool]:
    """``templates=`` -> ``(config, system_template, prompt_template, response_template, use_system_prompt)``.

    ``None`` (and, as before, a value ``resolve`` cannot turn into a config)
    means no templates and the default system prompt.
    """
    if templates is None:
        config = None
    elif isinstance(templates, TemplateConfig):
        config = templates
    elif isinstance(templates, dict):
        config = TemplateConfig(**templates)
    else:
        config = resolve(value=templates, param_name="templates", config_class=TemplateConfig, default=None)
    if config:
        return config, config.system, config.prompt, config.response, config.use_system_prompt
    return config, None, None, None, True


def resolve_agent_planning(planning: Any) -> Tuple[Optional[PlanningConfig], Dict[str, Any]]:
    """``planning=`` -> ``(config, overrides)``.

    *overrides* holds only the ``planning`` / ``planning_tools`` /
    ``planning_reasoning`` / ``plan_mode`` values this parameter sets; keys it
    does not set keep the caller's current value, as the inline block did.
    """
    if planning is None or planning is False:
        config = None
    elif planning is True:
        config = PlanningConfig()
    elif isinstance(planning, PlanningConfig):
        config = planning
    else:
        config = resolve_planning(planning, PlanningConfig)
    if config is not None:
        if isinstance(config, PlanningConfig):
            return config, {"planning": True, "planning_tools": config.tools,
                            "planning_reasoning": config.reasoning, "plan_mode": config.read_only}
        return config, {"planning": bool(config)}
    return config, {"planning": False}


def resolve_agent_reflection(reflection: Any) -> Tuple[Optional[ReflectionConfig], Dict[str, Any]]:
    """``reflection=`` -> ``(config, overrides)``.

    *overrides* holds only the ``self_reflect`` / ``min_reflect`` /
    ``max_reflect`` / ``reflect_llm`` / ``reflect_prompt`` values this
    parameter sets; ``None`` sets nothing, as the inline block did.
    """
    if reflection is None or reflection is False:
        config = None
    elif reflection is True:
        config = ReflectionConfig()
    elif isinstance(reflection, ReflectionConfig):
        config = reflection
    else:
        config = resolve_reflection(reflection, ReflectionConfig)
    if config is not None:
        if isinstance(config, ReflectionConfig):
            return config, {"self_reflect": True, "min_reflect": config.min_iterations,
                            "max_reflect": config.max_iterations, "reflect_llm": config.llm,
                            "reflect_prompt": config.prompt}
        return config, {"self_reflect": bool(config)}
    if reflection is True:
        return config, {"self_reflect": True}
    if reflection is False:
        return config, {"self_reflect": False}
    return config, {}


def resolve_agent_hooks(hooks: Any) -> Tuple[Any, List[Any], Optional[Any], Optional[Any]]:
    """``hooks=`` -> ``(config, hooks_list, step_callback, registry)``.

    ``None`` means no hooks; a list passes through; a ``HooksConfig`` (or a
    dict resolved into one) gives its middleware, with ``on_step`` /
    ``on_tool_call`` appended to the same chain. ``registry`` is a
    ``HooksConfig``'s ``registry`` attribute, if it has one.
    """
    if hooks is None:
        config = None
    elif isinstance(hooks, (list, HooksConfig)):
        config = hooks
    else:
        config = resolve(
            value=hooks,
            param_name="hooks",
            config_class=HooksConfig,
            array_mode=ArrayMode.PASSTHROUGH,
            default=None,
        )
    hooks_list, step_callback, registry = [], None, None
    # Per-agent event-hook registry (isolates BEFORE_TOOL/AFTER_AGENT/...
    # hooks so they never fire on unrelated agents sharing the default
    # registry). A bare HookRegistry passed as ``hooks=`` still works too.
    if isinstance(config, list):
        hooks_list = config
    elif isinstance(config, HooksConfig):
        step_callback = config.on_step
        hooks_list = list(config.middleware or [])
        registry = getattr(config, "registry", None)
        # Route on_step / on_tool_call onto the SAME middleware chain
        # that already powers ``hooks=[...]`` (MiddlewareManager). Both
        # keys used to be stored-and-never-called, so the TypeError that
        # advertises them ("Valid keys: on_step, on_tool_call,
        # middleware") promised behaviour that did not exist.
        if config.on_step is not None or config.on_tool_call is not None:
            from ..hooks.middleware import as_step_hook, as_tool_call_hook
            if config.on_step is not None:
                hooks_list.append(as_step_hook(config.on_step))
            if config.on_tool_call is not None:
                hooks_list.append(as_tool_call_hook(config.on_tool_call))
    return config, hooks_list, step_callback, registry


def resolve_agent_web(web: Any, web_search: Optional[bool] = None,
                      web_fetch: Optional[bool] = None
                      ) -> Tuple[Optional[WebConfig], Optional[bool], Optional[bool], str, bool]:
    """``web=`` -> ``(config, web_search, web_fetch, search_provider, fetch_is_default)``.

    ``web_search`` / ``web_fetch`` are the values to keep when ``web`` is
    ``None``. ``fetch_is_default`` tells Agent's later model check that fetch
    was not asked for explicitly.
    """
    # ``web=True`` or a dict that does not mention fetch asks for defaults,
    # not for fetch specifically (X-14); see the model check in Agent.__init__.
    _web_fetch_is_default = web is True or (isinstance(web, dict) and "fetch" not in web)
    # Fast path: None/False -> no web (skip resolve() call)
    if web is None or web is False:
        _web_config = None
    elif web is True:
        _web_config = WebConfig()
    elif isinstance(web, WebConfig):
        _web_config = web
    else:
        _web_config = resolve_web(web, WebConfig)
    
    _search_provider = "duckduckgo"
    if _web_config is not None:
        if isinstance(_web_config, WebConfig):
            web_search = _web_config.search
            web_fetch = _web_config.fetch
            _search_provider = str(getattr(_web_config.search_provider, "value", _web_config.search_provider) or "duckduckgo").lower()
        else:
            web_search = bool(_web_config)
            web_fetch = bool(_web_config)
    elif web is True:
        web_search = True
        web_fetch = True
    elif web is False:
        web_search = False
        web_fetch = False
    return _web_config, web_search, web_fetch, _search_provider, _web_fetch_is_default


def resolve_agent_execution(execution: Any) -> Optional[ExecutionConfig]:
    """``execution=`` -> ``ExecutionConfig`` (or a falsy value, which Agent
    treats as the defaults).

    ``None`` means the defaults; a string is a preset name, case-insensitive,
    and an unknown name falls back to the defaults here (Agent validates
    preset strings earlier); dicts and ``ExecutionConfig`` resolve as before.
    """
    # Fast path: None -> default config (skip resolve() call)
    if execution is None:
        return ExecutionConfig()
    if isinstance(execution, ExecutionConfig):
        return execution
    if isinstance(execution, str):
        preset_value = EXECUTION_PRESETS.get(canonical_preset_key(execution))
        if preset_value is not None:
            return ExecutionConfig(**preset_value) if isinstance(preset_value, dict) else preset_value
        return ExecutionConfig()
    return resolve_execution(execution, ExecutionConfig, default=ExecutionConfig())


def resolve_agent_history(memory_config: Any, session_id: Optional[str], auto_save: Any,
                          name: Optional[str]) -> Tuple[bool, int, Optional[str], Optional[str]]:
    """History settings from the resolved memory config.

    Returns ``(history_enabled, history_limit, history_session_id, session_id)``.
    History is enabled via memory="history" preset or MemoryConfig(history=True).
    ``session_id`` is returned unchanged unless history is on and it was None.
    """
    _history_enabled = False
    _history_limit = 10
    _history_session_id = None
    
    # Check if memory config has history settings
    if memory_config is not None and isinstance(memory_config, MemoryConfig):
        if memory_config.history:
            _history_enabled = True
            _history_limit = memory_config.history_limit
            # Use explicit session_id from MemoryConfig if provided
            if memory_config.session_id:
                _history_session_id = memory_config.session_id
    
    # Use auto_save session if no explicit session and history is enabled
    if _history_enabled and _history_session_id is None and auto_save:
        _history_session_id = auto_save
    
    # Auto-generate session_id when history=True but no session_id set
    # This ensures _init_session_store() can create the store
    if _history_enabled and session_id is None and _history_session_id is not None:
        session_id = _history_session_id
    elif _history_enabled and session_id is None and _history_session_id is None:
        import hashlib as _hl
        import os as _os
        _name = name or "agent"
        # Workspace-scoped id so same-named agents in different projects don't
        # collide (Issue #3154). Opt out with PRAISONAI_GLOBAL_SESSIONS=true for
        # name-only global continuity.
        _global_scope = _os.environ.get("PRAISONAI_GLOBAL_SESSIONS", "").lower() in ("1", "true", "yes")
        if _global_scope:
            _workspace_id = "global"
        else:
            from ..session.workspace import workspace_id as _wid
            _workspace_id = _wid()
        _workspace_hash = _hl.sha256(f"{_workspace_id}:{_name}".encode()).hexdigest()[:8]
        _new_id = f"history_{_workspace_hash}"
        # Backward-compat ids (resolution order: name-only sha256, then md5)
        _name_sha_id = f"history_{_hl.sha256(_name.encode()).hexdigest()[:8]}"
        _name_md5_id = f"history_{_hl.md5(_name.encode()).hexdigest()[:8]}"
        # Resolve the migration lookup against the SAME directory the session
        # store uses at runtime, so a custom PRAISONAI_HOME is honoured (the
        # store reads from get_sessions_dir()). Fall back to the default path
        # only if that helper is unavailable.
        try:
            from ..paths import get_sessions_dir as _get_sessions_dir
            _session_dir = str(_get_sessions_dir())
        except Exception:
            _session_dir = _os.path.join(_os.path.expanduser("~"), ".praisonai", "sessions")
        # Prefer an existing workspace-scoped session. Legacy (pre-workspace)
        # name-only files are only adopted in global scope: doing so in a
        # workspace-scoped run would silently share Project A's history with a
        # same-named agent in Project B (Issue #3154). Global scope is the
        # explicit opt-in for that name-only continuity.
        if _os.path.exists(_os.path.join(_session_dir, f"{_new_id}.json")):
            session_id = _new_id
        elif _global_scope and _os.path.exists(_os.path.join(_session_dir, f"{_name_sha_id}.json")):
            session_id = _name_sha_id  # preserve existing history
        elif _global_scope and _os.path.exists(_os.path.join(_session_dir, f"{_name_md5_id}.json")):
            session_id = _name_md5_id  # preserve existing history
        else:
            session_id = _new_id
        _history_session_id = session_id
    return _history_enabled, _history_limit, _history_session_id, session_id


def resolve_agent_learn(learn: Any, memory_config: Any, memory: Any,
                        auto_memory: Optional[bool]) -> Tuple[Optional[LearnConfig], Any, Optional[bool]]:
    """``learn=`` -> ``(learn_config, memory, auto_memory)``.

    learn= is a first-class citizen, independent of memory=. ``memory`` comes
    back as a minimal dict when learning needs it (a dict ``memory`` gets its
    ``learn`` key set in place, as before); ``auto_memory`` is turned on by
    ``learn=True`` unless the caller set it.
    """
    _learn_config = None
    
    # Top-level learn= takes precedence over memory.learn
    if learn is not None:
        # Explicit top-level learn= param
        if learn is False:
            _learn_config = None
        elif learn is True:
            # learn=True is a coordinated posture (Issue #4864): enable
            # AGENTIC extraction AND a conversational-aware nudge cadence in
            # one switch, so an always-on companion bot actually learns.
            # nudge_min_tool_iters=0 lets a chat-only turn (no tool calls)
            # still nudge; auto_memory is turned on below so durable facts
            # are captured on every turn, not just tool-using ones.
            from ..memory.learn.protocols import LearnMode
            _learn_config = LearnConfig(
                mode=LearnMode.AGENTIC,
                nudge_interval=10,
                nudge_min_tool_iters=0,
            )
        elif isinstance(learn, LearnConfig):
            _learn_config = learn
        elif isinstance(learn, dict):
            _learn_config = LearnConfig(**learn)
        elif isinstance(learn, str):
            # String mode: "disabled", "agentic", "propose".
            # Normalise case/whitespace so this branch agrees with the
            # closed-set validation in _validate_preset_params (which
            # already accepted "AGENTIC"/" agentic "); otherwise a validated
            # value would fall through to the else and silently disable.
            from ..memory.learn.protocols import LearnMode
            _learn_mode = learn.strip().lower()
            if _learn_mode == "disabled":
                _learn_config = None
            elif _learn_mode == "agentic":
                _learn_config = LearnConfig(mode=LearnMode.AGENTIC)
            elif _learn_mode == "propose":
                _learn_config = LearnConfig(mode=LearnMode.PROPOSE)
            else:
                # Unknown string mode, disable learning
                _learn_config = None
        else:
            logger.warning(
                "Unsupported learn= value %r; expected bool, dict, or LearnConfig. "
                "Learning disabled.", learn
            )
            _learn_config = None
    elif memory_config is not None and isinstance(memory_config, MemoryConfig):
        # Fallback to memory.learn for backward compatibility
        if memory_config.learn:
            if memory_config.learn is True:
                # learn=True shorthand enables AGENTIC mode
                from ..memory.learn.protocols import LearnMode
                _learn_config = LearnConfig(mode=LearnMode.AGENTIC)
            elif isinstance(memory_config.learn, LearnConfig):
                _learn_config = memory_config.learn
            elif isinstance(memory_config.learn, dict):
                _learn_config = LearnConfig(**memory_config.learn)
    
    # If learn is enabled but memory is not, we need to enable memory for learn to work
    if _learn_config is not None and memory is None:
        # Enable minimal memory for learn to work
        memory = {"learn": _learn_config.to_dict() if hasattr(_learn_config, 'to_dict') else _learn_config}
    elif _learn_config is not None and isinstance(memory, dict):
        # Merge learn config into memory dict
        memory["learn"] = _learn_config.to_dict() if hasattr(_learn_config, 'to_dict') else _learn_config

    # Coordinated learn posture (Issue #4864): the ``learn=True`` shorthand
    # turns on conversational fact extraction too, so an always-on companion
    # accrues durable persona/preferences from plain chat — not just from
    # tool-using turns. Only defaults it on when the caller did not set
    # auto_memory explicitly (via MemoryConfig), so an explicit choice wins.
    if learn is True and auto_memory is None:
        auto_memory = True
    return _learn_config, memory, auto_memory


def resolve_agent_memory(memory: Any) -> Any:
    """``memory=`` -> ``MemoryConfig``, a live backend, or ``None``.

    ``None``/``False`` mean no memory and ``True`` the defaults. A live
    backend (an object with ``search`` and ``add``, or a ``db()`` instance
    with ``database_url``) passes through; presets, URLs, dicts and lists
    resolve as before.
    """
    # Fast path: None/False -> no memory (skip resolve() call)
    if memory is None or memory is False:
        return None
    if memory is True:
        return MemoryConfig()
    if isinstance(memory, MemoryConfig):
        return memory
    if hasattr(memory, 'search') and hasattr(memory, 'add'):
        return memory  # Memory instance passthrough
    if hasattr(memory, 'database_url'):
        return memory  # db() instance passthrough
    return resolve_memory(memory, MemoryConfig)


def resolve_agent_knowledge(knowledge: Any, user_retrieval_config: Any
                            ) -> Tuple[Any, Any, Any, Optional[Dict[str, Any]]]:
    """``knowledge=`` -> ``(config, knowledge, retrieval_config, embedder_config)``.

    ``knowledge`` comes back as what Agent hands to Knowledge: the sources
    list, a live instance, or ``None``. ``retrieval_config`` is the dict
    derived from a ``KnowledgeConfig`` with ``user_retrieval_config``
    (``Agent(retrieval_config=)``) merged on top.
    """
    retrieval_config = None
    embedder_config = None
    
    # Fast path: None/False -> no knowledge (skip resolve() call)
    if knowledge is None or knowledge is False:
        _knowledge_config = None
    elif knowledge is True:
        _knowledge_config = KnowledgeConfig()
    elif isinstance(knowledge, KnowledgeConfig):
        _knowledge_config = knowledge
    elif isinstance(knowledge, list):
        _knowledge_config = KnowledgeConfig(sources=knowledge)
    elif hasattr(knowledge, 'search') and hasattr(knowledge, 'add'):
        _knowledge_config = knowledge  # Knowledge instance passthrough
    else:
        _knowledge_config = resolve(
            value=knowledge,
            param_name="knowledge",
            config_class=KnowledgeConfig,
            instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
            array_mode=ArrayMode.SOURCES_WITH_CONFIG,
            string_mode="path_as_source",
            default=None,
        )
    
    if _knowledge_config is not None:
        if hasattr(_knowledge_config, 'search') and hasattr(_knowledge_config, 'add'):
            # Knowledge instance - pass through
            knowledge = _knowledge_config
        elif isinstance(_knowledge_config, KnowledgeConfig):
            embedder_config = _knowledge_config.embedder_config
            # Every declared field is forwarded. Previously only top_k /
            # rerank survived: 'threshold' was spelled 'min_score' by
            # RetrievalConfig.from_dict, 'rerank_model' had no field at
            # all, and chunking + vector_store were never forwarded, so
            # those settings were silently inert.
            _chunker = _knowledge_config.chunker or {}
            _strategy = _knowledge_config.chunking_strategy
            _strategy = getattr(_strategy, 'value', _strategy)
            _vector_store = _knowledge_config.vector_store or {}
            retrieval_config = {
                'enabled': _knowledge_config.auto_retrieve,
                'top_k': _knowledge_config.retrieval_k,
                'min_score': _knowledge_config.retrieval_threshold,
                'rerank': _knowledge_config.rerank,
                'rerank_model': _knowledge_config.rerank_model,
                'chunking_strategy': _chunker.get('type', _strategy),
                'chunk_size': _chunker.get('chunk_size', _knowledge_config.chunk_size),
                'chunk_overlap': _chunker.get(
                    'chunk_overlap', _knowledge_config.chunk_overlap),
            }
            if _vector_store:
                _vs = dict(_vector_store)
                _vs_provider = _vs.pop('provider', None)
                if _vs_provider:
                    retrieval_config['vector_store_provider'] = _vs_provider
                _vs_inner = _vs.pop('config', None)
                if isinstance(_vs_inner, dict):
                    _vs.update(_vs_inner)
                if 'collection_name' in _vs:
                    retrieval_config['collection_name'] = _vs.pop('collection_name')
                if 'path' in _vs:
                    retrieval_config['persist_path'] = _vs.pop('path')
                if _vs:
                    retrieval_config['vector_store_config'] = _vs
            # Forward embedder settings so they reach Knowledge (mem0).
            # embedder is a provider shorthand (e.g. "gemini"); embedder_config
            # is the full mem0 embedder dict. Only override when explicitly set.
            if _knowledge_config.embedder and _knowledge_config.embedder != "openai":
                retrieval_config.setdefault('embedder_provider', _knowledge_config.embedder)
            if _knowledge_config.embedder_config:
                retrieval_config.setdefault('embedder_config', _knowledge_config.embedder_config)
            # `config=` is an escape hatch for keys the dataclass does not
            # model. It now overrides the resolved values instead of
            # replacing the whole dict, which silently reset retrieval_k.
            if _knowledge_config.config:
                retrieval_config.update(_knowledge_config.config)
            knowledge = _knowledge_config.sources if _knowledge_config.sources else None
        elif isinstance(_knowledge_config, list):
            knowledge = _knowledge_config
    elif knowledge is False:
        knowledge = None

    # Explicit retrieval_config= (the RAG tuning surface shown in the docs
    # and docstring examples) is merged on top of whatever the knowledge=
    # param derived. A dict overrides the derived keys; a RetrievalConfig
    # instance (or when no knowledge= was given) replaces it wholesale so
    # the downstream RetrievalConfig resolver (in Agent.__init__) receives it unchanged.
    if user_retrieval_config is not None:
        if isinstance(user_retrieval_config, dict) and isinstance(retrieval_config, dict):
            retrieval_config.update(user_retrieval_config)
        else:
            retrieval_config = user_retrieval_config
    return _knowledge_config, knowledge, retrieval_config, embedder_config


# File extensions that indicate a file path (for output parameter detection)
_FILE_EXTENSIONS = frozenset({'.txt', '.md', '.json', '.yaml', '.yml', '.html', '.csv', '.log', '.xml', '.rst'})

def _is_file_path(value: str) -> bool:
    """Check if a string looks like a file path (not a preset name).
    
    Used to detect when output="path/to/file.txt" should be treated as
    output_file instead of a preset name.
    
    Args:
        value: String to check
        
    Returns:
        True if the string looks like a file path
    """
    # Contains path separator
    if '/' in value or '\\' in value:
        return True
    # Ends with common file extension
    lower = value.lower()
    for ext in _FILE_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def resolve_agent_output(output: Any, env_output: Optional[str]) -> Tuple[Any, bool]:
    """``output=`` -> ``(config, has_explicit_output)``.

    DEFAULT: "silent" mode (zero overhead, fastest performance). ``env_output``
    is the ``PRAISONAI_OUTPUT`` value, used only when ``output`` is ``None``.
    A string is a preset name (case-insensitive) or, if it looks like a file
    path, the ``output_file``.
    """
    # Fast path: None -> silent defaults (use cached env var)
    if output is None:
        if env_output and env_output in OUTPUT_PRESETS:
            output = env_output
        else:
            output = DEFAULT_OUTPUT_MODE
        _has_explicit_output = False
    else:
        _has_explicit_output = True
    
    # Fast path: string preset lookup (most common case)
    if isinstance(output, str):
        output_lower = canonical_preset_key(output)
        preset_value = OUTPUT_PRESETS.get(output_lower)
        if preset_value is not None:
            _output_config = OutputConfig(**preset_value) if isinstance(preset_value, dict) else preset_value
        elif _is_file_path(output):
            # String looks like a file path - use as output_file
            _output_config = OutputConfig(output_file=output)
        else:
            _output_config = OutputConfig()  # Default silent
    elif isinstance(output, OutputConfig):
        _output_config = output
    else:
        # Complex case: use full resolver
        _output_config = resolve(
            value=output,
            param_name="output",
            config_class=OutputConfig,
            presets=OUTPUT_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=OutputConfig(),
        )
    return _output_config, _has_explicit_output


def resolve_agent_guardrails(guardrails: Any, guardrail: Any, max_guardrail_retries: int
                             ) -> Tuple[Any, Any, int]:
    """``guardrails=`` -> ``(config, guardrail, max_guardrail_retries)``.

    ``guardrail`` and ``max_guardrail_retries`` are the values to keep when
    no guardrail is resolved. Raises instead of storing a guardrail that would
    never run (policy strings, unsupported values, unimplemented on_fail).
    """
    from .loader import apply_config_defaults

    # Fail loud instead of silently ignoring policy-string guardrails. The
    # documented `guardrails=["policy:strict", ...]` shorthand has no
    # enforcement path wired up, so accepting it silently would run with zero
    # enforcement — a "safe by default" violation. Checked before resolution
    # so the clear message wins over the generic resolver's error. Direct
    # users to the working `Agent(policy=PolicyEngine(...))` param.
    if isinstance(guardrails, (list, tuple)):
        from .parse_utils import is_policy_string
        _policy_strs = [g for g in guardrails if isinstance(g, str) and is_policy_string(g)]
        if _policy_strs:
            raise ValueError(
                f"Policy-string guardrails {_policy_strs} are not enforced. "
                "Use Agent(policy=PolicyEngine(...)) for tool policy enforcement, "
                "or pass a validator via guardrails=... / GuardrailConfig(validator=...)."
            )

    # Apply [defaults].guardrails from config when not explicitly provided,
    # mirroring the memory/web/caching/etc. resolution above so a config-wide
    # guardrail safety net is actually honoured instead of silently ignored.
    if guardrails is None:
        guardrails = apply_config_defaults("guardrails", None, GuardrailConfig)

    # Fast path: None/False -> no guardrails (skip resolve() call)
    if guardrails is None or guardrails is False:
        _guardrails_config = None
    elif callable(guardrails) and not isinstance(guardrails, type):
        _guardrails_config = guardrails  # Callable passthrough
    elif isinstance(guardrails, GuardrailConfig):
        _guardrails_config = guardrails
    elif isinstance(guardrails, str):
        # String could be LLM prompt - passthrough for later processing
        _guardrails_config = guardrails
    else:
        # A protocol-conforming guardrail *object* (validate_input /
        # validate_output / validate_tool_call) is not ``callable()``, so it
        # used to fall straight through to the resolver, which returns None
        # for an unknown object - the validator was silently discarded and
        # the agent ran with zero enforcement. Adapt it into a
        # ``GuardrailChain``, which is callable (so it satisfies the existing
        # guardrail runner) and forwards every protocol method.
        from ..guardrails.protocols import is_guardrail_object
        if is_guardrail_object(guardrails):
            from ..guardrails import GuardrailChain
            _guardrails_config = GuardrailChain([guardrails])
        elif isinstance(guardrails, (list, tuple)) and any(
            is_guardrail_object(g) for g in guardrails
        ):
            _bad = [g for g in guardrails if not is_guardrail_object(g)]
            if _bad:
                raise TypeError(
                    "guardrails=[...] may not mix guardrail objects with "
                    f"{[type(g).__name__ for g in _bad]}. Every item must implement "
                    "validate_input/validate_output/validate_tool_call, or wrap the "
                    "list yourself with GuardrailChain([...])."
                )
            from ..guardrails import GuardrailChain
            _guardrails_config = GuardrailChain(list(guardrails))
        else:
            from .param_resolver import resolve_guardrails as _resolve_guardrails
            _guardrails_config = _resolve_guardrails(
                value=guardrails,
                config_class=GuardrailConfig,
            )
    
    # Same fail-loud guard for GuardrailConfig.policy/.policies passed
    # directly — those fields are never consumed downstream, so silently
    # accepting them would also run with zero enforcement.
    if isinstance(_guardrails_config, GuardrailConfig) and (
        _guardrails_config.policy is not None or _guardrails_config.policies
    ):
        raise ValueError(
            "GuardrailConfig.policy/.policies are not enforced. "
            "Use Agent(policy=PolicyEngine(...)) for tool policy enforcement, "
            "or pass a validator via GuardrailConfig(validator=...)."
        )
    # GuardrailConfig.on_fail has a single implemented policy (retry, then
    # return the blocked message); refuse "skip"/"raise" rather than
    # silently behaving as "retry".
    if isinstance(_guardrails_config, GuardrailConfig) and (
        getattr(_guardrails_config.on_fail, "value", _guardrails_config.on_fail) != "retry"
    ):
        raise ValueError(
            f"GuardrailConfig.on_fail={_guardrails_config.on_fail!r} is not supported; "
            "only 'retry' is implemented. Remove on_fail, or handle a blocked "
            "response via Agent.last_guardrail_error."
        )

    # Fail loud when the value could not be turned into an enforceable
    # guardrail, instead of storing something that never runs. Silently
    # dropping a validator the caller explicitly asked for is a "safe by
    # default" violation, same rationale as the policy-string guard above.
    # An empty list/tuple resolves to None (no validator was actually
    # supplied), which the resolver already treated as a no-op on main -
    # keep that backward-compatible instead of raising on an empty opt-in.
    _is_empty_guardrails = (
        isinstance(guardrails, (list, tuple)) and len(guardrails) == 0
    )
    if (
        guardrails is not None
        and guardrails is not False
        and not _is_empty_guardrails
        and not (
            callable(_guardrails_config)
            or isinstance(_guardrails_config, (GuardrailConfig, str))
        )
    ):
        raise TypeError(
            f"guardrails={guardrails!r} (type {type(guardrails).__name__}) is not a "
            "supported guardrail. Pass a validator callable taking one TaskOutput, an "
            "object implementing validate_input/validate_output/validate_tool_call, a "
            "list of such objects, a GuardrailConfig, or a string LLM-validation prompt."
        )

    if _guardrails_config is not None:
        if callable(_guardrails_config) and not isinstance(_guardrails_config, type):
            # Callable validator function
            guardrail = _guardrails_config
        elif isinstance(_guardrails_config, GuardrailConfig):
            guardrail = _guardrails_config.validator or _guardrails_config.llm_validator
            max_guardrail_retries = _guardrails_config.max_retries
        elif isinstance(_guardrails_config, str):
            # LLM validator prompt
            guardrail = _guardrails_config
    return _guardrails_config, guardrail, max_guardrail_retries


def resolve_agent_skills(skills: Any) -> Tuple[Any, Any, Any, bool]:
    """``skills=`` -> ``(config, paths, dirs, auto_discover)``.

    ``None`` means no skills (skips ``resolve()``). A list, or a single string
    (``'./dir'``, ``'name'``, ``'@bundle'``) as a one-item list, becomes
    ``SkillsConfig(paths=...)``.
    """
    _skills = None
    skills_dirs = None
    # Fast path: None -> no skills (skip resolve() call)
    if skills is None:
        _skills_config = None
    elif isinstance(skills, (list, str)):
        # A single string ('./dir', 'name', '@bundle') is a one-item list.
        _skills_config = SkillsConfig(paths=[skills] if isinstance(skills, str) else skills)
    elif isinstance(skills, SkillsConfig):
        _skills_config = skills
    else:
        _skills_config = resolve(
            value=skills,
            param_name="skills",
            config_class=SkillsConfig,
            array_mode=ArrayMode.SOURCES,
            string_mode="path_as_source",
            default=None,
        )
    _skills_auto_discover = False
    if _skills_config is not None:
        if isinstance(_skills_config, SkillsConfig):
            _skills = _skills_config.paths
            skills_dirs = _skills_config.dirs
            _skills_auto_discover = bool(_skills_config.auto_discover)
        elif isinstance(_skills_config, list):
            _skills = _skills_config
    return _skills_config, _skills, skills_dirs, _skills_auto_discover


def resolve_agent_model(
    llm: Any, model: Any, base_url: Any, api_key: Any, auth: Any, fallback_models: Any, owner: str,
) -> Tuple[Any, Any, Any, Any, Any, Any]:
    """``llm=`` / ``model=`` -> ``(llm, fallback_models, base_url, api_key, auth, auth_profiles)``.

    Passing both is refused. ``model=`` wins over ``llm=``. An ``LLMConfig`` on
    either supplies the model and fills ``base_url``/``api_key``/``auth`` only
    where the caller left them ``None``; on ``llm=`` its ``fallback_models``
    always replace the incoming ones, on ``model=`` only fill a gap. A plain
    ``llm=`` warns once (``DeprecationWarning`` at the caller of ``Agent(...)``).
    """
    from ..utils.model_alias import resolve_model_alias
    resolve_model_alias(llm, model, owner)

    auth_profiles = None
    if isinstance(llm, LLMConfig):
        llm_config_obj = llm
        llm = llm_config_obj.model
        fallback_models = llm_config_obj.fallback_models
        if base_url is None:
            base_url = llm_config_obj.base_url
        if api_key is None:
            api_key = llm_config_obj.api_key
        if auth is None:
            auth = llm_config_obj.auth
        auth_profiles = llm_config_obj.auth_profiles
    elif llm is not None and model is None:
        from ..utils.deprecation import warn_deprecated_param
        warn_deprecated_param(
            "llm",
            since="1.0.0",
            removal="2.0.0",
            alternative="use 'model' instead. Example: Agent(model='gpt-4o-mini')",
            stacklevel=4,  # warn_deprecated_param -> here -> Agent.__init__ -> caller
        )

    if model is not None:
        if isinstance(model, LLMConfig):
            llm = model.model
            if fallback_models is None:
                fallback_models = model.fallback_models
            if base_url is None:
                base_url = model.base_url
            if api_key is None:
                api_key = model.api_key
            if auth is None:
                auth = model.auth
            if auth_profiles is None:
                auth_profiles = model.auth_profiles
        else:
            llm = model  # model= takes precedence
    return llm, fallback_models, base_url, api_key, auth, auth_profiles


def resolve_agent_llm_options(
    retry: Any, reasoning_effort: Optional[str], **options: Any,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """``retry=`` / ``reasoning_effort=`` -> ``(retry_init_params, option_kwargs)``.

    *retry_init_params* is ``{"max_retries": n}`` for a ``RetryBackoffConfig``,
    a dict (validated through ``RetryBackoffConfig``) or ``False`` (0), else
    empty, so the custom-LLM path honours ``retry=`` instead of LLM's own
    default. *option_kwargs* is *options* plus those retry kwargs, plus
    ``reasoning_effort`` only when given.
    """
    from ..agent.retry_utils import RetryBackoffConfig

    retry_init_params: Dict[str, Any] = {}
    if isinstance(retry, RetryBackoffConfig):
        retry_init_params = {'max_retries': retry.max_retries}
    elif isinstance(retry, dict):
        retry_init_params = {'max_retries': RetryBackoffConfig(**retry).max_retries}
    elif retry is False:
        retry_init_params = {'max_retries': 0}

    option_kwargs = {**options, **retry_init_params}
    if reasoning_effort is not None:
        option_kwargs['reasoning_effort'] = reasoning_effort
    return retry_init_params, option_kwargs


def resolve_agent_local(
    llm: str, base_url: Any, api_key: Any, retrieval_config: Any, embedder_config: Any,
    memory: Any, discover: Any,
) -> Tuple[str, Any, Any, Any, Any]:
    """``llm="local"`` / ``"local:<engine>/<model>"`` ->
    ``(llm, base_url, api_key, embedder_config, target)``.

    Resolves the local target, fills ``base_url`` (Ollama takes the server
    root; every other engine its OpenAI ``/v1`` URL) and ``api_key`` only where
    the caller left them ``None``. When memory or knowledge will embed and no
    embedder is set, picks an embedding model the server serves (via
    ``discover(target)``) so documents stay on the machine, carries its vector
    width, and sets it on ``retrieval_config`` (updated in place) too; if none
    is served it warns instead. An explicit embedder always wins.
    """
    from ..local import LocalEngine, resolve as resolve_local

    spec = llm[len("local:"):] if llm.startswith("local:") else None
    target = resolve_local(spec or None)
    llm = target.litellm_model
    if base_url is None:
        # Ollama's litellm provider builds its own /api paths from the server
        # root. Every other local engine speaks OpenAI under /v1: the bare root
        # sent chat to /chat/completions, which they answer with 404.
        base_url = (target.base_url if target.engine is LocalEngine.OLLAMA
                    else target.openai_base_url)
    if api_key is None:
        api_key = target.api_key

    # Keep a local agent local end to end: without this, knowledge/memory
    # embedded against OpenAI, sending documents and queries off the machine.
    wants_embeddings = (retrieval_config is not None or embedder_config is not None
                        or memory not in (None, False))
    # retrieval_config may be a dict or a RetrievalConfig instance.
    rc_embedder = (retrieval_config.get('embedder_config') if isinstance(retrieval_config, dict)
                   else getattr(retrieval_config, 'embedder_config', None))
    if wants_embeddings and not embedder_config and not rc_embedder:
        from ..local import local_embedder_config, select_embedding_model
        discovery = discover(target)
        embed_model = select_embedding_model(
            getattr(discovery, 'models', ()) if discovery else (),
            getattr(discovery, 'model_meta', ()) if discovery else ())
        if embed_model:
            embedder_config = local_embedder_config(target.engine, target.base_url, embed_model)
            # Carry the real vector width (local/ cannot import the dimension
            # table). A width the server measured wins; the table only fills a
            # gap, and never with the generic default: a guessed width is worse
            # than letting the store infer one from the first vector.
            cfg = embedder_config.setdefault("config", {})
            if not cfg.get("embedding_dims"):
                try:
                    from ..embedding.dimensions import DEFAULT_DIMENSION, get_dimensions
                    dims = get_dimensions(embed_model)
                    if dims and dims != DEFAULT_DIMENSION:
                        cfg["embedding_dims"] = dims
                except Exception:  # noqa: BLE001 -- a missing width must not break setup
                    logger.debug("No vector width for %r; the store infers it", embed_model,
                                 exc_info=True)
            if isinstance(retrieval_config, dict):
                retrieval_config.setdefault('embedder_config', embedder_config)
            elif retrieval_config is not None and getattr(
                    retrieval_config, 'embedder_config', None) is None:
                retrieval_config.embedder_config = embedder_config
        else:
            logger.warning(
                "llm=%r resolved a local model, but %s serves no embedding "
                "model, so knowledge/memory would embed against a remote "
                "provider -- sending your documents off this machine. "
                "Pull one (e.g. `ollama pull nomic-embed-text`) or set an "
                "explicit embedder to silence this.",
                llm, target.base_url)
    return llm, base_url, api_key, embedder_config, target
