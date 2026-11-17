"""Pure resolvers for ``Agent.__init__`` parameters (G-19).

Each function turns one user-facing parameter into what ``Agent`` stores, so the
logic is unit-testable without building an agent. Names carry an ``agent_``
infix because ``config.resolve_<param>`` already exists with different
defaults (for example ``resolve_caching(None)`` returns ``None``).
"""

from typing import Any, Dict, Optional, Tuple

from .feature_configs import CachingConfig, GuardrailConfig, PlanningConfig, ReflectionConfig, TemplateConfig
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
