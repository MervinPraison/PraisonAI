"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, Optional, Tuple

from .._logging import get_logger

from .feature_configs import CachingConfig, LearnConfig, MemoryConfig, PlanningConfig, ReflectionConfig, TemplateConfig
from .param_resolver import ArrayMode, resolve
from .presets import CACHING_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS

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
