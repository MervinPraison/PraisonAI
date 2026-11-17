"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, Optional, Tuple

from .feature_configs import CachingConfig, MemoryConfig, PlanningConfig, ReflectionConfig, TemplateConfig
from .param_resolver import ArrayMode, resolve
from .presets import CACHING_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS


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
