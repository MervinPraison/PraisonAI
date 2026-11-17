"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, Optional, Tuple

from .feature_configs import CachingConfig, OutputConfig, PlanningConfig, ReflectionConfig, TemplateConfig
from .param_resolver import ArrayMode, resolve
from .parse_utils import canonical_preset_key
from .presets import (
    CACHING_PRESETS, DEFAULT_OUTPUT_MODE, OUTPUT_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS,
)


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
