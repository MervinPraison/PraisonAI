"""
Model capabilities configuration for different LLM providers.

This module uses LiteLLM's helper functions as the primary source for model capability detection.
LiteLLM is maintained by many contributors and is more accurate and up-to-date.

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
        return None


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
    
    try:
        litellm = _get_litellm()
        if litellm is None:
            return False
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_response_schema'):
            return litellm.supports_response_schema(model=model_name)
    except Exception:
        pass
    
    return False


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
    
    try:
        litellm = _get_litellm()
        if litellm is None:
            return False
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_function_calling'):
            return litellm.supports_function_calling(model=model_name)
    except Exception:
        pass
    
    return False


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
    
    try:
        litellm = _get_litellm()
        if litellm is None:
            return False
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_parallel_function_calling'):
            return litellm.supports_parallel_function_calling(model=model_name)
    except Exception:
        pass
    
    return False


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
    
    try:
        litellm = _get_litellm()
        if litellm is None:
            return False
        # Use LiteLLM's built-in check - most accurate and up-to-date
        if hasattr(litellm, 'supports_web_search'):
            return litellm.supports_web_search(model=model_name)
    except Exception:
        pass
    
    return False


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
    
    try:
        litellm = _get_litellm()
        if litellm is None:
            return False
        if hasattr(litellm, 'utils') and hasattr(litellm.utils, 'supports_prompt_caching'):
            return litellm.utils.supports_prompt_caching(model=model_name)
    except Exception:
        pass
    
    return False


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