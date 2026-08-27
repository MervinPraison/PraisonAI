"""
Reasoning-effort translation for PraisonAI Agents.

A single, graded, provider-portable reasoning-effort control that resolves to
each provider's native request parameter:

- OpenAI o-series / GPT-5 / xAI reasoning models -> native ``reasoning_effort``
  (``minimal|low|medium|high``).
- Anthropic / Gemini extended-thinking models -> a ``thinking`` token budget.
- Models without a reasoning control -> nothing (silently ignored,
  backward-compatible).

Zero overhead when unused: ``off``/``None`` resolves to an empty dict and the
helper is only imported on the request path when an effort is actually set.
"""

from typing import Any, Dict, Optional

# Canonical graded levels shared with the CLI surface
# (``praisonai_code.cli.features.thinking.THINKING_LEVELS``).
EFFORT_LEVELS = ("off", "minimal", "low", "medium", "high")

# Native ``reasoning_effort`` only accepts these; ``off`` is a no-op.
_NATIVE_EFFORT = {"minimal", "low", "medium", "high"}

# Extended-thinking token budgets for Anthropic/Gemini, mirroring the CLI's
# ``THINKING_BUDGET_MAP`` so a level means the same thing on every surface.
_EFFORT_BUDGET_MAP: Dict[str, Optional[int]] = {
    "off": None,
    "minimal": 2000,
    "low": 4000,
    "medium": 8000,
    "high": 16000,
}

# Inverse of the budget map: lets a legacy ``thinking_budget`` int be normalised
# back to the nearest graded level so both surfaces share one internal value.
_BUDGET_EFFORT_PAIRS = sorted(
    ((tokens, level) for level, tokens in _EFFORT_BUDGET_MAP.items() if tokens),
    key=lambda pair: pair[0],
)


def normalize_effort(value: Any) -> Optional[str]:
    """Normalise a reasoning-effort value to a canonical level or ``None``.

    Accepts a graded string (``off|minimal|low|medium|high``, case-insensitive)
    or a legacy ``thinking_budget`` int (mapped to the nearest level). Unknown
    or unset values return ``None`` (treated as "no reasoning control").
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Guard against ``True``/``False`` sneaking in via ``int`` handling.
        return "medium" if value else None
    if isinstance(value, str):
        level = value.strip().lower()
        return level if level in EFFORT_LEVELS else None
    if isinstance(value, int):
        if value <= 0:
            return None
        # Map a token budget to the smallest level whose budget covers it.
        for tokens, level in _BUDGET_EFFORT_PAIRS:
            if value <= tokens:
                return level
        return "high"
    return None


def _is_native_effort_model(model: str) -> bool:
    """OpenAI o-series / GPT-5 / xAI reasoning models take native effort."""
    from ..llm.model_capabilities import is_reasoning_model

    name = (model or "").lower()
    if name.startswith("xai/") or "grok" in name:
        return True
    return is_reasoning_model(model)


def _is_extended_thinking_model(model: str) -> bool:
    """Anthropic / Gemini models expose an extended-thinking token budget."""
    name = (model or "").lower()
    return (
        "claude" in name
        or "anthropic" in name
        or "gemini" in name
    )


def resolve_reasoning_params(effort: Any, model: str) -> Dict[str, Any]:
    """Translate a unified reasoning-effort level to provider-native kwargs.

    Args:
        effort: A graded level (``off|minimal|low|medium|high``) or a legacy
            ``thinking_budget`` int; anything else is treated as unset.
        model: The target model name (with or without provider prefix).

    Returns:
        A dict of native request params to merge into the completion call:
        ``{"reasoning_effort": <level>}`` for OpenAI/xAI reasoning models,
        ``{"thinking": {"type": "enabled", "budget_tokens": <int>}}`` for
        Anthropic/Gemini extended-thinking models, or ``{}`` when the effort is
        off/unset or the model has no reasoning control.
    """
    level = normalize_effort(effort)
    if level is None or level == "off":
        return {}

    # Anthropic / Gemini expose an extended-thinking token budget. Checked first
    # because these families can also match the generic reasoning-model
    # classifier, but their native control is the thinking budget, not
    # ``reasoning_effort``.
    if _is_extended_thinking_model(model):
        budget = _EFFORT_BUDGET_MAP.get(level)
        if budget:
            return {"thinking": {"type": "enabled", "budget_tokens": budget}}
        return {}

    # OpenAI o-series / GPT-5 / xAI reasoning models take native reasoning_effort.
    if _is_native_effort_model(model):
        if level in _NATIVE_EFFORT:
            return {"reasoning_effort": level}
        return {}

    # No known reasoning control for this model: silently ignore.
    return {}
