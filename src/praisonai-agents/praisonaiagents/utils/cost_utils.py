"""
Cost calculation utilities for PraisonAI Agents.

Provides unified cost calculation with:
- litellm integration (when available) for 1000+ models
- Fallback pricing for common models when litellm not installed
- Zero performance impact via lazy imports
"""

from typing import Any, Dict, Optional

# Fallback pricing per 1M tokens (used when litellm not available)
# These are approximate and cover the most common models.
# Optional "cache_read"/"cache_write" are multipliers of the input rate for
# prompt-cache hits/writes; when absent they default to 1.0 (flat input rate).
_FALLBACK_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00, "cache_read": 0.5},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.5},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o1": {"input": 15.00, "output": 60.00, "cache_read": 0.5},
    "o1-mini": {"input": 1.10, "output": 4.40, "cache_read": 0.5},
    "o1-preview": {"input": 15.00, "output": 60.00},
    "o3-mini": {"input": 1.10, "output": 4.40, "cache_read": 0.5},
    # Anthropic models
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00, "cache_read": 0.1, "cache_write": 1.25},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00, "cache_read": 0.1, "cache_write": 1.25},
    "claude-3-opus": {"input": 15.00, "output": 75.00, "cache_read": 0.1, "cache_write": 1.25},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25, "cache_read": 0.1, "cache_write": 1.25},
    # Google models
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "cache_read": 0.25},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "cache_read": 0.25},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cache_read": 0.25},
    "gemini-2.0-flash-exp": {"input": 0.10, "output": 0.40},
    "gemini-pro": {"input": 0.50, "output": 1.50},
    # DeepSeek models
    "deepseek-chat": {"input": 0.14, "output": 0.28, "cache_read": 0.1},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19, "cache_read": 0.25},
    # Default fallback
    "default": {"input": 1.00, "output": 3.00},
}

# Cache for litellm availability check
_litellm_available: Optional[bool] = None


def _check_litellm_available() -> bool:
    """Check if litellm is available (cached)."""
    global _litellm_available
    if _litellm_available is None:
        try:
            from litellm.cost_calculator import completion_cost  # noqa: F401
            _litellm_available = True
        except ImportError:
            _litellm_available = False
    return _litellm_available


def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: Optional[str] = None,
    response: Optional[Any] = None,
    use_litellm: bool = False,
    cached_tokens: Optional[int] = None,
    cache_write_tokens: Optional[int] = None,
) -> float:
    """
    Calculate LLM cost using fallback pricing (fast) or litellm (accurate).
    
    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        model: Model name (e.g., 'gpt-4o-mini', 'claude-3-5-sonnet')
        response: Optional LLM response object for litellm.completion_cost
        use_litellm: If True, use litellm for accurate pricing (slower, imports litellm).
                     Default False for performance - uses fast fallback pricing.
        cached_tokens: Prompt-cache hit tokens (included in prompt_tokens).
                       Read from ``response`` usage when not given.
        cache_write_tokens: Prompt-cache write tokens (included in prompt_tokens).
                            Read from ``response`` usage when not given.
        
    Returns:
        Estimated cost in USD (float)
    """
    # A positive cost reported by the provider/client is authoritative. A
    # reported 0.0 is ignored so unpriced models (custom base_url, proxies)
    # still accrue the fallback estimate and the budget guard keeps working.
    reported = _extract_reported_cost(response)
    if reported is not None:
        return round(reported, 6)

    usage = _get(response, "usage")
    if cached_tokens is None:
        cached_tokens = _usage_int(
            _get(_get(usage, "prompt_tokens_details"), "cached_tokens")
        ) or _usage_int(_get(usage, "cache_read_input_tokens"))
    if cache_write_tokens is None:
        cache_write_tokens = _usage_int(_get(usage, "cache_creation_input_tokens"))

    # Use fallback pricing by default (fast, no imports)
    # Only use litellm if explicitly requested (e.g., for --save CLI flag)
    if not use_litellm:
        return _calculate_fallback_cost(
            prompt_tokens, completion_tokens, model, cached_tokens, cache_write_tokens
        )
    
    # Try litellm only when explicitly requested (supports 1000+ models with accurate pricing)
    if _check_litellm_available():
        try:
            from litellm.cost_calculator import completion_cost
            
            # Build response dict for litellm
            if response is not None:
                # Use response object directly if available
                if hasattr(response, 'model_dump'):
                    cost = completion_cost(completion_response=response.model_dump())
                elif isinstance(response, dict):
                    cost = completion_cost(completion_response=response)
                else:
                    # Fallback to building dict from tokens
                    cost = completion_cost(
                        completion_response={
                            'usage': _litellm_usage(
                                prompt_tokens, completion_tokens, cached_tokens, cache_write_tokens
                            ),
                            'model': model or 'gpt-4o-mini',
                        },
                        model=model,
                    )
            else:
                # Build dict from tokens
                cost = completion_cost(
                    completion_response={
                        'usage': _litellm_usage(
                            prompt_tokens, completion_tokens, cached_tokens, cache_write_tokens
                        ),
                        'model': model or 'gpt-4o-mini',
                    },
                    model=model,
                )
            
            if cost is not None and cost > 0:
                return round(cost, 6)
        except Exception:
            pass  # Fall through to fallback pricing
    
    # Fallback pricing calculation
    return _calculate_fallback_cost(
        prompt_tokens, completion_tokens, model, cached_tokens, cache_write_tokens
    )


def _litellm_usage(
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: Optional[int],
    cache_write_tokens: Optional[int],
) -> Dict[str, Any]:
    """Build a usage dict for litellm, carrying prompt-cache counts."""
    return {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'prompt_tokens_details': {'cached_tokens': _usage_int(cached_tokens)},
        'cache_read_input_tokens': _usage_int(cached_tokens),
        'cache_creation_input_tokens': _usage_int(cache_write_tokens),
    }


def _get(obj: Any, name: str) -> Any:
    """Read ``name`` from an object attribute or dict key (None if absent)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _usage_int(value: Any) -> int:
    """Coerce a usage counter to a non-negative int (0 for non-numeric)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(int(value), 0)


def _extract_reported_cost(response: Any) -> Optional[float]:
    """Return a provider/client-reported cost from a response, if present.

    Checks ``usage.cost`` (e.g. OpenRouter) and litellm's
    ``_hidden_params["response_cost"]``. Only real, positive numbers are
    accepted; zero means "unknown" and falls back to the local estimate.
    """
    if response is None:
        return None
    for value in (
        _get(_get(response, "usage"), "cost"),
        _get(_get(response, "_hidden_params"), "response_cost"),
    ):
        if not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _calculate_fallback_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: Optional[str] = None,
    cached_tokens: Optional[int] = 0,
    cache_write_tokens: Optional[int] = 0,
) -> float:
    """
    Calculate cost using fallback pricing table.
    
    Args:
        prompt_tokens: Number of input tokens (including cached/cache-write)
        completion_tokens: Number of output tokens
        model: Model name
        cached_tokens: Prompt-cache hit tokens, priced at the cache-read rate
        cache_write_tokens: Prompt-cache write tokens, priced at the cache-write rate
        
    Returns:
        Estimated cost in USD
    """
    model_name = (model or "gpt-4o-mini").lower()
    # Strip a provider prefix (e.g. "openai/gpt-4o-mini" -> "gpt-4o-mini") so
    # litellm-style names still resolve against the fallback table.
    if "/" in model_name:
        model_name = model_name.rsplit("/", 1)[-1]

    # Find matching pricing. Match longest keys first and require an exact
    # match or a prefix boundary ("<key>-...") so that "gpt-4o-mini" does not
    # fall through to the "gpt-4o" entry (which billed it at 16.7x the real
    # rate). "default" is excluded from matching and used only as a fallback.
    pricing = _FALLBACK_PRICING.get("default")
    for key in sorted(
        (k for k in _FALLBACK_PRICING if k != "default"), key=len, reverse=True
    ):
        if model_name == key or model_name.startswith(key + "-"):
            pricing = _FALLBACK_PRICING[key]
            break
    
    # Calculate cost (pricing is per 1M tokens). Cached/cache-write tokens are
    # part of prompt_tokens; price them at their multiplier of the input rate.
    cached = min(_usage_int(cached_tokens), prompt_tokens)
    cache_write = min(_usage_int(cache_write_tokens), prompt_tokens - cached)
    uncached = prompt_tokens - cached - cache_write
    input_cost = (
        uncached
        + cached * pricing.get("cache_read", 1.0)
        + cache_write * pricing.get("cache_write", 1.0)
    ) / 1_000_000 * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    
    return round(input_cost + output_cost, 6)
