"""
Model capabilities configuration for different LLM providers.

This module uses LiteLLM's helper functions as the primary source for model capability detection.
LiteLLM is maintained by many contributors and is more accurate and up-to-date.

When LiteLLM is not installed (lean provider-native installs), each ``supports_*`` helper
falls back to a small, conservative static heuristic instead of silently returning ``False``,
so capability gating stays usable without pulling in the optional ``litellm`` dependency.
The fallbacks are pattern-based only (no network, no new dependency); LiteLLM remains
authoritative whenever it is installed.

LiteLLM Helper Functions:
- litellm.supports_web_search(model=) - Check web search support
- litellm.supports_function_calling(model=) - Check function calling support
- litellm.supports_parallel_function_calling(model=) - Check parallel function calling
- litellm.supports_response_schema(model=) - Check JSON schema/structured outputs support
- litellm.utils.supports_prompt_caching(model=) - Check prompt caching support
- litellm.get_supported_openai_params(model=) - Get all supported params

Sources:
- https://docs.litellm.ai/docs/completion/web_search
- https://docs.litellm.ai/docs/completion/json_mode
- https://docs.litellm.ai/docs/completion/function_call
- https://docs.litellm.ai/docs/completion/prompt_caching
"""

from functools import lru_cache

from ._litellm_loader import get_litellm as _get_litellm


def _base_model_name(model_name: str) -> str:
    """Strip a leading ``provider/`` prefix and lowercase for pattern matching."""
    name = model_name.lower()
    if "/" in name:
        name = name.split("/", 1)[1]
    return name


def _fallback_supports_structured_outputs(model_name: str) -> bool:
    """Static heuristic used only when litellm is unavailable.

    Keeps capability gating correct for lean (litellm-free) installs instead of
    silently returning False. Deliberately conservative and pattern-based; no
    network, no new dependency.
    """
    name = _base_model_name(model_name)
    return any(
        p in name
        for p in ("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4", "gemini", "claude-3", "claude-sonnet", "claude-opus", "claude-haiku")
    )


def _fallback_supports_function_calling(model_name: str) -> bool:
    """Static heuristic used only when litellm is unavailable."""
    name = _base_model_name(model_name)
    if any(x in name for x in ("embedding", "whisper", "tts", "dall-e")):
        return False
    return any(
        p in name
        for p in ("gpt-4", "gpt-5", "gpt-3.5", "o1", "o3", "o4", "gemini", "claude", "llama-3", "mistral", "mixtral", "grok")
    )


def _fallback_supports_parallel_function_calling(model_name: str) -> bool:
    """Static heuristic used only when litellm is unavailable.

    Deliberately narrower than :func:`_fallback_supports_function_calling`:
    parallel tool calls are a stricter capability than serial function calling,
    so this only reports ``True`` for provider families known to support issuing
    multiple tool calls in a single turn. Models that support only serial tool
    calls conservatively return ``False``.
    """
    if not _fallback_supports_function_calling(model_name):
        return False
    name = _base_model_name(model_name)
    return any(
        p in name
        for p in ("gpt-4", "gpt-5", "gpt-3.5", "o1", "o3", "o4", "gemini", "claude")
    )


def _fallback_supports_web_search(model_name: str) -> bool:
    """Static heuristic used only when litellm is unavailable.

    Note: Anthropic Claude models are intentionally excluded here — they use
    ``web_fetch`` (see :func:`supports_web_fetch`), not native ``web_search``,
    mirroring litellm's own reporting.
    """
    name = _base_model_name(model_name)
    if "perplexity" in name or name.startswith("sonar"):
        return True
    if "search" in name:  # e.g. gpt-4o-search-preview
        return True
    return any(p in name for p in ("gemini-2", "grok-3"))


def _fallback_supports_prompt_caching(model_name: str) -> bool:
    """Static heuristic used only when litellm is unavailable."""
    name = _base_model_name(model_name)
    return any(p in name for p in ("claude-3", "claude-sonnet", "claude-opus", "claude-haiku", "gpt-4o", "gpt-4.1", "gpt-5", "deepseek"))


@lru_cache(maxsize=256)
def supports_structured_outputs(model_name: str) -> bool:
    """
    Check if a model supports structured outputs (JSON schema).
    
    Uses LiteLLM's supports_response_schema() as the primary check.
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports structured outputs, False otherwise
    """
    if not model_name:
        return False
    
    litellm = None
    try:
        litellm = _get_litellm()
        if litellm is None:
            # litellm genuinely unavailable: use conservative static heuristic.
            return _fallback_supports_structured_outputs(model_name)
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_response_schema'):
            return litellm.supports_response_schema(model=model_name)
    except Exception:
        pass

    # litellm is installed but the helper is missing or raised: keep litellm
    # authoritative (return False) rather than overriding it with the heuristic.
    if litellm is not None:
        return False
    return _fallback_supports_structured_outputs(model_name)


@lru_cache(maxsize=256)
def supports_function_calling(model_name: str) -> bool:
    """
    Check if a model supports function calling.
    
    Uses LiteLLM's supports_function_calling() as the primary check.
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports function calling, False otherwise
    """
    if not model_name:
        return False
    
    litellm = None
    try:
        litellm = _get_litellm()
        if litellm is None:
            return _fallback_supports_function_calling(model_name)
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_function_calling'):
            return litellm.supports_function_calling(model=model_name)
    except Exception:
        pass

    if litellm is not None:
        return False
    return _fallback_supports_function_calling(model_name)


@lru_cache(maxsize=256)
def supports_parallel_function_calling(model_name: str) -> bool:
    """
    Check if a model supports parallel function calling.
    
    Uses LiteLLM's supports_parallel_function_calling() as the primary check.
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports parallel function calling, False otherwise
    """
    if not model_name:
        return False
    
    litellm = None
    try:
        litellm = _get_litellm()
        if litellm is None:
            return _fallback_supports_parallel_function_calling(model_name)
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_parallel_function_calling'):
            return litellm.supports_parallel_function_calling(model=model_name)
    except Exception:
        pass

    if litellm is not None:
        return False
    return _fallback_supports_parallel_function_calling(model_name)


def supports_streaming_with_tools(model_name: str) -> bool:
    """
    Check if a model supports streaming when tools are provided.
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports streaming with tools, False otherwise
    """
    # Models that support function calling generally support streaming with tools
    return supports_function_calling(model_name)


# Supported Gemini internal tools
GEMINI_INTERNAL_TOOLS = {'googleSearch', 'urlContext', 'codeExecution'}


@lru_cache(maxsize=256)
def supports_web_search(model_name: str) -> bool:
    """
    Check if a model supports native web search via LiteLLM.
    
    Uses LiteLLM's supports_web_search() as the primary check.
    
    Native web search allows the model to search the web in real-time
    without requiring external tools like DuckDuckGo.
    
    Supported providers:
    - OpenAI (gpt-4o-search-preview, gpt-4o-mini-search-preview)
    - xAI (grok-3)
    - Anthropic (claude-3-5-sonnet-latest, claude-sonnet-4, etc.)
    - Google/Vertex AI (gemini-2.0-flash, gemini-2.5-*, etc.)
    - Perplexity (all models)
    
    Args:
        model_name: The name of the model to check (with or without provider prefix)
        
    Returns:
        bool: True if the model supports native web search, False otherwise
    """
    if not model_name:
        return False
    
    litellm = None
    try:
        litellm = _get_litellm()
        if litellm is None:
            return _fallback_supports_web_search(model_name)
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_web_search'):
            return litellm.supports_web_search(model=model_name)
    except Exception:
        pass

    if litellm is not None:
        return False
    return _fallback_supports_web_search(model_name)


@lru_cache(maxsize=256)
def supports_prompt_caching(model_name: str) -> bool:
    """
    Check if a model supports prompt caching via LiteLLM.
    
    Uses LiteLLM's supports_prompt_caching() as the primary check.
    
    Prompt caching allows caching parts of prompts to reduce costs and latency
    on subsequent requests with similar prompts.
    
    Supported providers:
    - OpenAI (openai/) - Automatic caching for prompts ≥1024 tokens
    - Anthropic (anthropic/) - Manual caching with cache_control
    - Bedrock (bedrock/) - All models that support prompt caching
    - Deepseek (deepseek/) - Works like OpenAI
    
    Args:
        model_name: The name of the model to check (with or without provider prefix)
        
    Returns:
        bool: True if the model supports prompt caching, False otherwise
    """
    if not model_name:
        return False
    
    litellm = None
    try:
        litellm = _get_litellm()
        if litellm is None:
            return _fallback_supports_prompt_caching(model_name)
        if hasattr(litellm, 'utils') and hasattr(litellm.utils, 'supports_prompt_caching'):
            return litellm.utils.supports_prompt_caching(model=model_name)
    except Exception:
        pass

    if litellm is not None:
        return False
    return _fallback_supports_prompt_caching(model_name)


# Models that support web fetch via LiteLLM (Anthropic only)
# Web fetch retrieves full content from specific URLs (web pages and PDFs)
# Source: https://docs.litellm.ai/docs/completion/web_fetch
# Note: LiteLLM doesn't have a supports_web_fetch() helper yet, so we maintain a static list
MODELS_SUPPORTING_WEB_FETCH = {
    # Anthropic Claude models with web fetch support
    "claude-opus-4-1-20250805",
    "claude-opus-4-1",
    "claude-opus-4-20250514",
    "claude-opus-4",
    "claude-sonnet-4-20250514",
    "claude-sonnet-4",
    "claude-3-7-sonnet-20250219",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-latest",
    "claude-3-5-haiku-20241022",
}


@lru_cache(maxsize=256)
def supports_web_fetch(model_name: str) -> bool:
    """
    Check if a model supports web fetch via LiteLLM.
    
    Web fetch allows the model to retrieve full content from specific URLs
    (web pages and PDF documents). Currently only supported by Anthropic Claude models.
    
    Note: LiteLLM doesn't have a supports_web_fetch() helper yet, so we use a static list
    with auto-detection for Claude 4+ models.
    
    Args:
        model_name: The name of the model to check (with or without provider prefix)
        
    Returns:
        bool: True if the model supports web fetch, False otherwise
    """
    if not model_name:
        return False
    
    # Strip provider prefixes
    model_without_provider = model_name
    for prefix in ['anthropic/', 'bedrock/', 'vertex_ai/']:
        if model_name.startswith(prefix):
            model_without_provider = model_name[len(prefix):]
            break
    
    # Check our static list
    if model_without_provider in MODELS_SUPPORTING_WEB_FETCH:
        return True
    
    # Check base model name (without version suffix)
    base_model = model_without_provider.split('-2024-')[0].split('-2025-')[0]
    if base_model in MODELS_SUPPORTING_WEB_FETCH:
        return True
    
    # Auto-support for Claude 4+ models (Anthropic only)
    model_lower = model_without_provider.lower()
    if 'claude' in model_lower:
        import re
        # Match patterns like claude-4, claude-5, claude-sonnet-4, claude-opus-4, etc.
        version_match = re.search(r'claude-(?:sonnet-|opus-|haiku-)?(\d+)', model_lower)
        if version_match:
            version = int(version_match.group(1))
            if version >= 4:  # Claude 4 and later
                return True
    
    return False


@lru_cache(maxsize=256)
def is_reasoning_model(model_name: str) -> bool:
    """
    Check if a model is a reasoning model (OpenAI o1/o3/gpt-5.x class).

    Reasoning models require ``max_completion_tokens`` instead of ``max_tokens``
    and reject several sampling params (temperature, top_p, etc.).

    Uses LiteLLM's ``supports_reasoning()`` as the primary check, with a
    prefix-based fallback for models LiteLLM doesn't know about yet.

    Args:
        model_name: The name of the model to check (with or without provider prefix)

    Returns:
        bool: True if the model is a reasoning model, False otherwise
    """
    if not model_name:
        return False

    try:
        litellm = _get_litellm()
        if litellm is not None and hasattr(litellm, 'supports_reasoning'):
            if litellm.supports_reasoning(model=model_name):
                return True
    except Exception:
        pass

    # Fallback prefix match for reasoning-class models (strip provider prefix)
    model = model_name.split('/')[-1].lower()
    return (
        model.startswith('o1')
        or model.startswith('o3')
        or model.startswith('o4')
        or model.startswith('gpt-5')
    )


def is_gemini_internal_tool(tool) -> bool:
    """
    Check if a tool is a Gemini internal tool and should be included in formatted tools.
    
    Gemini internal tools are single-key dictionaries with specific tool names.
    Examples: {"googleSearch": {}}, {"urlContext": {}}, {"codeExecution": {}}
    
    Args:
        tool: The tool to check
        
    Returns:
        bool: True if the tool is a recognized Gemini internal tool, False otherwise
    """
    if isinstance(tool, dict) and len(tool) == 1:
        tool_name = next(iter(tool.keys()))
        return tool_name in GEMINI_INTERNAL_TOOLS
    return False