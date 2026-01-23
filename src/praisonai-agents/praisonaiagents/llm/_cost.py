"""
Centralized Cost Calculation Module for PraisonAI Agents.

This module provides lazy-loaded cost calculation to avoid importing
litellm in the hot path when cost tracking is not needed.

Usage:
    from praisonaiagents.llm._cost import calculate_cost, is_cost_tracking_enabled
    
    # Only calculates cost if litellm is available and response is valid
    cost = calculate_cost(response, model="gpt-4o-mini")
"""

import os
import logging
from typing import Any, Dict, Optional

# Module-level cache for litellm (lazy loaded)
_litellm_module = None
_litellm_import_attempted = False


def _get_litellm():
    """
    Lazy import litellm module.
    
    Returns litellm module if available, None otherwise.
    Caches the result to avoid repeated import attempts.
    """
    global _litellm_module, _litellm_import_attempted
    
    if _litellm_import_attempted:
        return _litellm_module
    
    _litellm_import_attempted = True
    
    try:
        import litellm
        _litellm_module = litellm
        return litellm
    except ImportError:
        logging.debug("litellm not available for cost calculation")
        return None


def is_cost_tracking_enabled() -> bool:
    """
    Check if cost tracking should be enabled.
    
    Cost tracking is enabled when:
    1. PRAISONAI_TRACK_COST=true environment variable is set
    2. --save flag is used (sets PRAISONAI_SAVE_OUTPUT=true)
    3. metrics=True is passed to Agent
    
    Returns:
        True if cost tracking should be enabled
    """
    # Check environment variables
    track_cost = os.environ.get('PRAISONAI_TRACK_COST', '').lower() in ('true', '1', 'yes')
    save_output = os.environ.get('PRAISONAI_SAVE_OUTPUT', '').lower() in ('true', '1', 'yes')
    
    return track_cost or save_output


def calculate_cost(
    response: Any,
    model: Optional[str] = None,
    force: bool = False,
) -> Optional[float]:
    """
    Calculate cost for an LLM response.
    
    This function lazily imports litellm only when needed, avoiding
    the 1.5s import penalty in the hot path.
    
    Args:
        response: The LLM response object (OpenAI format or dict)
        model: Optional model name override
        force: Force cost calculation even if tracking is disabled
        
    Returns:
        Cost in USD if calculable, None otherwise
    """
    # Skip if cost tracking not enabled and not forced
    if not force and not is_cost_tracking_enabled():
        return None
    
    # Lazy import litellm
    litellm = _get_litellm()
    if litellm is None:
        return None
    
    try:
        # Handle different response formats
        if hasattr(response, 'model_dump'):
            # Pydantic model (OpenAI SDK response)
            response_dict = response.model_dump()
        elif isinstance(response, dict):
            response_dict = response
        else:
            # Try to convert to dict
            try:
                response_dict = dict(response)
            except (TypeError, ValueError):
                return None
        
        # Add model if provided and not in response
        if model and 'model' not in response_dict:
            response_dict['model'] = model
        
        # Calculate cost using litellm
        cost = litellm.completion_cost(completion_response=response_dict)
        return cost
        
    except Exception as e:
        logging.debug(f"Cost calculation failed: {e}")
        return None


def calculate_cost_from_tokens(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    force: bool = False,
) -> Optional[float]:
    """
    Calculate cost from token counts.
    
    Args:
        model: Model name
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        force: Force cost calculation even if tracking is disabled
        
    Returns:
        Cost in USD if calculable, None otherwise
    """
    # Skip if cost tracking not enabled and not forced
    if not force and not is_cost_tracking_enabled():
        return None
    
    # Lazy import litellm
    litellm = _get_litellm()
    if litellm is None:
        return None
    
    try:
        cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        # cost_per_token returns (prompt_cost, completion_cost)
        if isinstance(cost, tuple):
            return sum(cost)
        return cost
    except Exception as e:
        logging.debug(f"Token cost calculation failed: {e}")
        return None


def get_model_cost_info(model: str) -> Optional[Dict[str, float]]:
    """
    Get cost information for a model.
    
    Args:
        model: Model name
        
    Returns:
        Dict with 'input_cost_per_token' and 'output_cost_per_token' if available
    """
    litellm = _get_litellm()
    if litellm is None:
        return None
    
    try:
        model_info = litellm.get_model_info(model=model)
        if model_info:
            return {
                'input_cost_per_token': model_info.get('input_cost_per_token', 0),
                'output_cost_per_token': model_info.get('output_cost_per_token', 0),
            }
    except Exception:
        pass
    
    return None


def enable_cost_tracking():
    """Enable cost tracking via environment variable."""
    os.environ['PRAISONAI_TRACK_COST'] = 'true'


def disable_cost_tracking():
    """Disable cost tracking via environment variable."""
    os.environ.pop('PRAISONAI_TRACK_COST', None)
