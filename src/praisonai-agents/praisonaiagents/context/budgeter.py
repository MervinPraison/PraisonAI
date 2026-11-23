"""
Context Budgeter for PraisonAI Agents.

Allocates token budgets across context segments based on model limits.
"""

import functools
import logging
import sys
from typing import Dict, Any, Optional
from .models import BudgetAllocation

logger = logging.getLogger(__name__)


# Model token limits (context window sizes)
MODEL_LIMITS: Dict[str, int] = {
    # OpenAI — gpt-5 family (1M context window)
    "gpt-5": 1047576,
    "gpt-5-mini": 1047576,
    "gpt-5-nano": 1047576,
    # OpenAI — gpt-4.1 family (1M context window)
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
    # OpenAI — gpt-4o family
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    # OpenAI — o-series
    "o3-mini": 200000,
    "o3": 200000,
    "o4-mini": 200000,
    # Anthropic
    "claude-3-5-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    # Google
    "gemini-2.0-flash": 1048576,
    "gemini-1.5-pro": 2097152,
    "gemini-1.5-flash": 1048576,
    # Defaults
    "default": 128000,
}

# Default output reserves by model family
OUTPUT_RESERVES: Dict[str, int] = {
    "gpt-5": 32768,
    "gpt-4.1": 32768,
    "gpt-4o": 16384,
    "gpt-4o-mini": 16384,
    "gpt-4-turbo": 4096,
    "gpt-4": 4096,
    "gpt-3.5-turbo": 4096,
    "o3": 100000,
    "o4-mini": 100000,
    "claude-3": 8192,
    "gemini": 8192,
    "default": 8000,
}


@functools.lru_cache(maxsize=1)
def _bundled_model_cost() -> Dict[str, Any]:
    """litellm's bundled ``model_prices_and_context_window`` data, read as JSON.

    ``import litellm`` costs about 3 s and ~3,000 modules; a context-window
    lookup only needs this one file, which litellm itself loads into
    ``model_cost``. ``find_spec`` locates the package without importing it.
    Returns ``{}`` when litellm is not installed.
    """
    try:
        import importlib.util
        import json
        import os
        spec = importlib.util.find_spec("litellm")
        for folder in (spec.submodule_search_locations or []) if spec else []:
            path = os.path.join(folder, "model_prices_and_context_window_backup.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
    except Exception:
        logger.debug("Could not read litellm's bundled model data", exc_info=True)
    return {}


def _litellm_model_info(model: str) -> Optional[Dict[str, Any]]:
    """
    Look up a model's info from litellm's ``model_cost`` registry.

    Uses the live ``litellm.model_cost`` when litellm is already imported,
    otherwise the same data from litellm's bundled JSON, so a lookup never
    imports litellm. Returns ``None`` when litellm is absent or the model
    is unknown.
    """
    model_cost = None
    if "litellm" in sys.modules:
        try:
            from litellm import model_cost
        except Exception:
            model_cost = None
    if model_cost is None:
        model_cost = _bundled_model_cost()

    try:
        model_lower = model.lower()
        if model_lower in model_cost:
            return model_cost[model_lower]
        # Try with provider prefix removed (e.g. "openai/gpt-4o" -> "gpt-4o")
        if "/" in model:
            base_model = model.split("/")[-1].lower()
            if base_model in model_cost:
                return model_cost[base_model]
    except Exception:
        return None
    return None
litellm_model_info = _litellm_model_info  # public name for other PraisonAI packages (G-22); the private name stays


def resolved_model_limit(model: Optional[str]) -> Optional[int]:
    """Full context window for ``model``, or None when it is unknown.

    The same lookup order as :func:`get_model_limit`, without the generic
    ``MODEL_LIMITS["default"]`` stand-in. A model whose real window happens
    to be 128000 (``gpt-4o``) still resolves. An unrecognised name returns
    None so a meter does not pretend the window is 128000.
    """
    if not model or not isinstance(model, str):
        return None

    # A local server told us the real window when it was probed. litellm knows no
    # local tag, so without this a 40960-token model inherits the generic 128000
    # default and compaction budgets it at three times its real room -- the
    # server then truncates silently. No probing here: this is a cached read.
    try:
        from ..local.embed import context_length_for
        probed = context_length_for(model)
        if probed:
            return int(probed)
    except Exception:  # noqa: BLE001 -- budgeting must never fail on a lookup
        logger.debug("Local context-window lookup failed for %s", model, exc_info=True)

    # Prefer data-driven lookup via litellm (context window = max_input_tokens)
    info = _litellm_model_info(model)
    if info:
        limit = info.get("max_input_tokens") or info.get("max_tokens")
        if limit:
            return int(limit)

    # Exact match. "default" is the stand-in, not a model.
    if model in MODEL_LIMITS and model != "default":
        return MODEL_LIMITS[model]

    # Partial match (e.g., "gpt-4o-2024-05-13" matches "gpt-4o")
    model_lower = model.lower()
    for key, limit in MODEL_LIMITS.items():
        if key == "default":
            continue
        if key in model_lower or model_lower.startswith(key):
            return limit

    return None


def get_model_limit(model: str) -> int:
    """
    Get context window limit for a model.

    Resolves against litellm's ``model_cost`` registry first (``max_input_tokens``),
    so any model the underlying LLM layer knows gets the correct window — then
    falls back to the static ``MODEL_LIMITS`` table for offline use.

    Args:
        model: Model name or identifier

    Returns:
        Context window size in tokens
    """
    return resolved_model_limit(model) or MODEL_LIMITS["default"]


# Full context windows, verified against the provider documentation. This is
# deliberately independent of LiteLLM's input-token cap and of request budgets.
_VERIFIED_OPENAI_WINDOWS = {
    "gpt-5": 400000,
    "gpt-5-2025-08-07": 400000,
    "gpt-5-mini": 400000,
    "gpt-5-mini-2025-08-07": 400000,
    "gpt-5-nano": 400000,
    "gpt-5-nano-2025-08-07": 400000,
}


def verified_context_window(model: Optional[str], *, endpoint: Optional[str] = None) -> Optional[int]:
    """Return a verified full window only for an actual official endpoint.

    https://developers.openai.com/api/docs/models/gpt-5 (and mini/nano).
    Unknown aliases, custom endpoints and absent provenance are unavailable.
    """
    from urllib.parse import urlsplit

    if not isinstance(model, str) or not isinstance(endpoint, str):
        return None
    try:
        url = urlsplit(endpoint)
        official = (url.scheme.lower() == "https" and url.hostname == "api.openai.com"
                    and url.port in (None, 443) and url.username is None and url.password is None
                    and url.path.rstrip("/") == "/v1" and not url.query and not url.fragment)
    except ValueError:
        return None
    if not official:
        return None
    name = model.lower()
    if name.startswith("openai/"):
        name = name[len("openai/"):]
    return _VERIFIED_OPENAI_WINDOWS.get(name)


def _non_negative_int(value: Any) -> int:
    """Token counts from providers are integers. Anything else counts as zero."""
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _usage_field(usage: Any, name: str) -> Any:
    """Read one field from a dict or an object. Missing is None, not zero."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get(name)
    return getattr(usage, name, None)


def occupancy_tokens(usage: Any) -> int:
    """Prompt tokens that fill the window. Output tokens are ignored.

    LiteLLM's Anthropic adapter already adds ``cache_read_input_tokens`` and
    ``cache_creation_input_tokens`` into ``prompt_tokens``, so that total is
    used as-is. A raw Anthropic usage object has only ``input_tokens`` (the
    uncached tail) plus those cache fields, and the cache is added. OpenAI's
    ``prompt_tokens`` already includes ``cached_tokens``; that subset is not
    read here, so it cannot be added twice.
    """
    if usage is None:
        return 0
    prompt_raw = _usage_field(usage, "prompt_tokens")
    input_raw = _usage_field(usage, "input_tokens")
    prompt = _non_negative_int(prompt_raw) if prompt_raw is not None else None
    inputted = _non_negative_int(input_raw) if input_raw is not None else None
    extra = _non_negative_int(
        _usage_field(usage, "cache_read_input_tokens")
    ) + _non_negative_int(_usage_field(usage, "cache_creation_input_tokens"))
    if prompt is not None and inputted is not None and extra:
        if prompt >= inputted + extra:
            return prompt
        # prompt_tokens was copied from the uncached tail and is no larger
        # than the cache itself. The cache is not in the total yet.
        if prompt <= inputted and prompt <= extra:
            return inputted + extra
        return prompt
    if inputted is not None and extra and prompt is None:
        return inputted + extra
    if prompt is not None:
        return prompt
    if inputted is not None:
        return inputted
    return 0


def context_window_usage(
    prompt_tokens: int,
    model: Optional[str],
    *,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    endpoint: Optional[str] = None,
) -> Optional[Dict[str, int]]:
    """Occupancy of the full context window for one prompt.

    ``prompt_tokens`` is the provider's input count. Output tokens are not
    included. Pass Anthropic ``cache_read_input_tokens`` and
    ``cache_creation_input_tokens``: those are excluded from Anthropic's
    ``input_tokens`` and must be added. Do not pass OpenAI ``cached_tokens``;
    those are already inside ``prompt_tokens``.

    Returns None when there is nothing to report or the actual endpoint and
    model do not have a verified window. ``percent`` is integer division of
    the full window and may exceed 100 when the prompt is over the limit.

    The dict keys are ``used``, ``limit``, and ``percent``.
    """
    limit = verified_context_window(model, endpoint=endpoint)
    if not limit:
        return None
    used = (
        _non_negative_int(prompt_tokens)
        + _non_negative_int(cache_read_tokens)
        + _non_negative_int(cache_creation_tokens)
    )
    if used <= 0:
        return None
    return {"used": used, "limit": limit, "percent": used * 100 // limit}


def compaction_context_payload(
    context_tokens: int,
    model: Optional[str],
    message_count: int = 0,
) -> Dict[str, Any]:
    """Snapshot passed to ``BEFORE_COMPACTION``.

    ``context_tokens`` is the size of the messages about to be compacted.
    ``context_window_size`` and ``context_usage_percent`` are present only
    when the model window is known.
    """
    tokens = _non_negative_int(context_tokens)
    payload: Dict[str, Any] = {
        "context_tokens": tokens,
        "message_count": _non_negative_int(message_count),
    }
    usage = context_window_usage(tokens, model)
    if usage:
        payload["context_window_size"] = usage["limit"]
        payload["context_usage_percent"] = usage["percent"]
    return payload


def get_output_reserve(model: str) -> int:
    """
    Get recommended output token reserve for a model.

    Resolves against litellm's ``model_cost`` registry first
    (``max_output_tokens``), then falls back to the static ``OUTPUT_RESERVES``
    table for offline use.

    Args:
        model: Model name

    Returns:
        Output reserve in tokens
    """
    # Prefer data-driven lookup via litellm (output reserve = max_output_tokens)
    info = _litellm_model_info(model)
    if info:
        reserve = info.get("max_output_tokens")
        if reserve:
            return reserve

    model_lower = model.lower()
    
    for key, reserve in OUTPUT_RESERVES.items():
        if key in model_lower:
            return reserve
    
    return OUTPUT_RESERVES["default"]


class ContextBudgeter:
    """
    Allocates token budgets across context segments.
    
    Ensures context fits within model limits while reserving
    space for output generation.
    
    Example:
        budgeter = ContextBudgeter(model="gpt-4o")
        allocation = budgeter.allocate()
        print(f"History budget: {allocation.history_budget}")
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        model_limit: Optional[int] = None,
        output_reserve: Optional[int] = None,
        # Segment budget overrides (absolute tokens)
        system_prompt_budget: int = 2000,
        rules_budget: int = 500,
        skills_budget: int = 500,
        memory_budget: int = 1000,
        tools_schema_budget: int = 2000,
        tool_outputs_budget: int = 20000,
        buffer_budget: int = 1000,
        # Ratio-based allocation (if set, overrides fixed budgets)
        history_ratio: Optional[float] = None,
    ):
        """
        Initialize budgeter.
        
        Args:
            model: Model name for limit lookup
            model_limit: Override model limit
            output_reserve: Override output reserve
            system_prompt_budget: Budget for system prompt
            rules_budget: Budget for rules
            skills_budget: Budget for skills
            memory_budget: Budget for memory
            tools_schema_budget: Budget for tool schemas
            tool_outputs_budget: Budget for tool outputs
            buffer_budget: Safety buffer
            history_ratio: If set, allocate this ratio of usable for history
        """
        self.model = model
        self.model_limit = model_limit or get_model_limit(model)
        self.output_reserve = output_reserve or get_output_reserve(model)
        
        self.system_prompt_budget = system_prompt_budget
        self.rules_budget = rules_budget
        self.skills_budget = skills_budget
        self.memory_budget = memory_budget
        self.tools_schema_budget = tools_schema_budget
        self.tool_outputs_budget = tool_outputs_budget
        self.buffer_budget = buffer_budget
        self.history_ratio = history_ratio
    
    @property
    def usable(self) -> int:
        """Usable tokens after output reserve."""
        return self.model_limit - self.output_reserve
    
    def allocate(self) -> BudgetAllocation:
        """
        Create a budget allocation.
        
        Returns:
            BudgetAllocation with segment budgets
        """
        allocation = BudgetAllocation(
            model_limit=self.model_limit,
            output_reserve=self.output_reserve,
            system_prompt=self.system_prompt_budget,
            rules=self.rules_budget,
            skills=self.skills_budget,
            memory=self.memory_budget,
            tools_schema=self.tools_schema_budget,
            tool_outputs=self.tool_outputs_budget,
            buffer=self.buffer_budget,
            history=-1,  # Dynamic
        )
        
        # If history_ratio is set, compute history budget from ratio
        if self.history_ratio is not None:
            allocation.history = int(self.usable * self.history_ratio)
        
        return allocation
    
    def check_overflow(
        self,
        current_tokens: int,
        threshold: float = 0.8
    ) -> bool:
        """
        Check if current tokens exceed threshold.
        
        Args:
            current_tokens: Current total tokens
            threshold: Threshold as fraction of usable (0.0-1.0)
            
        Returns:
            True if overflow threshold exceeded
        """
        return current_tokens > (self.usable * threshold)
    
    def get_remaining(self, current_tokens: int) -> int:
        """
        Get remaining tokens before hitting usable limit.
        
        Args:
            current_tokens: Current total tokens
            
        Returns:
            Remaining tokens (can be negative if over limit)
        """
        return self.usable - current_tokens
    
    def get_utilization(self, current_tokens: int) -> float:
        """
        Get current utilization as fraction.
        
        Args:
            current_tokens: Current total tokens
            
        Returns:
            Utilization (0.0-1.0+)
        """
        if self.usable == 0:
            return 0.0
        return current_tokens / self.usable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert budgeter state to dictionary."""
        return {
            "model": self.model,
            "model_limit": self.model_limit,
            "output_reserve": self.output_reserve,
            "usable": self.usable,
            "allocation": self.allocate().to_dict(),
        }
