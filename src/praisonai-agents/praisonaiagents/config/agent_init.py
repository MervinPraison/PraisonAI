"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, List, Optional, Tuple

from .feature_configs import (
    CachingConfig, HooksConfig, PlanningConfig, ReflectionConfig,
    TemplateConfig, WebConfig, ExecutionConfig, MemoryConfig,
)
from .._logging import get_logger

from .feature_configs import CachingConfig, LearnConfig, MemoryConfig, PlanningConfig, ReflectionConfig, TemplateConfig
from .param_resolver import ArrayMode, resolve
from .presets import CACHING_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS, WEB_PRESETS
from .parse_utils import canonical_preset_key
from .presets import CACHING_PRESETS, EXECUTION_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS

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
        config = resolve(
            value=caching,
            param_name="caching",
            config_class=CachingConfig,
            presets=CACHING_PRESETS,
            default=CachingConfig(),
        )
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
        config = resolve(
            value=planning,
            param_name="planning",
            config_class=PlanningConfig,
            presets=PLANNING_PRESETS,
            string_mode="llm_model",
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=None,
        )
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
        config = resolve(
            value=reflection,
            param_name="reflection",
            config_class=ReflectionConfig,
            presets=REFLECTION_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=None,
        )
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
        _web_config = resolve(
            value=web,
            param_name="web",
            config_class=WebConfig,
            presets=WEB_PRESETS,
            array_mode=ArrayMode.PRESET_OVERRIDE,
            default=None,
        )
    
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
    return resolve(
        value=execution,
        param_name="execution",
        config_class=ExecutionConfig,
        presets=EXECUTION_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
        default=ExecutionConfig(),
    )


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
