"""
Cost calculation utilities for PraisonAI Agents.

Provides unified cost calculation with:
- litellm integration (when available) for 1000+ models
- Fallback pricing for common models when litellm not installed
- Zero performance impact via lazy imports
"""

from typing import Any, Dict, Optional

# Fallback pricing per 1M tokens (used when litellm not available)
# These are approximate and cover the most common models
_FALLBACK_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 1.10, "output": 4.40},
    "o1-preview": {"input": 15.00, "output": 60.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # Anthropic models
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    # Google models
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-exp": {"input": 0.10, "output": 0.40},
    "gemini-pro": {"input": 0.50, "output": 1.50},
    # DeepSeek models
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
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
        
    Returns:
        Estimated cost in USD (float)
    """
    # Use fallback pricing by default (fast, no imports)
    # Only use litellm if explicitly requested (e.g., for --save CLI flag)
    if not use_litellm:
        return _calculate_fallback_cost(prompt_tokens, completion_tokens, model)
    
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
                            'usage': {
                                'prompt_tokens': prompt_tokens,
                                'completion_tokens': completion_tokens,
                            },
                            'model': model or 'gpt-4o-mini',
                        },
                        model=model,
                    )
            else:
                # Build dict from tokens
                cost = completion_cost(
                    completion_response={
                        'usage': {
                            'prompt_tokens': prompt_tokens,
                            'completion_tokens': completion_tokens,
                        },
                        'model': model or 'gpt-4o-mini',
                    },
                    model=model,
                )
            
            if cost is not None and cost > 0:
                return round(cost, 6)
        except Exception:
            pass  # Fall through to fallback pricing
    
    # Fallback pricing calculation
    return _calculate_fallback_cost(prompt_tokens, completion_tokens, model)


def _calculate_fallback_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: Optional[str] = None,
) -> float:
    """
    Calculate cost using fallback pricing table.
    
    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        model: Model name
        
    Returns:
        Estimated cost in USD
    """
    model_name = (model or "gpt-4o-mini").lower()
    
    # Find matching pricing (partial match)
    pricing = _FALLBACK_PRICING.get("default")
    for key, price in _FALLBACK_PRICING.items():
        if key in model_name or model_name in key:
            pricing = price
            break
    
    # Calculate cost (pricing is per 1M tokens)
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    
    return round(input_cost + output_cost, 6)
