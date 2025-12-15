"""
Model capabilities configuration for different LLM providers.
This module defines which models support specific features like structured outputs.
"""

# Models that support OpenAI-style structured outputs (response_format with json_schema)
# Sources:
# - https://platform.openai.com/docs/guides/structured-outputs
# - https://platform.claude.com/docs/en/build-with-claude/structured-outputs
# - https://ai.google.dev/gemini-api/docs/structured-output
MODELS_SUPPORTING_STRUCTURED_OUTPUTS = {
    # OpenAI models with confirmed structured outputs support
    # Source: https://platform.openai.com/docs/guides/structured-outputs
    # "Structured Outputs with response_format: {type: "json_schema", ...} is only supported 
    # with the gpt-4o-mini, gpt-4o-mini-2024-07-18, and gpt-4o-2024-08-06 model snapshots and later"
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    # GPT-4.1 series
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-nano",
    "gpt-4.1-nano-2025-04-14",
    # GPT-5 series
    "gpt-5",
    "gpt-5-2025-08-07",
    "gpt-5-mini",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano",
    "gpt-5-nano-2025-08-07",
    "gpt-5-pro",
    "gpt-5-pro-2025-10-06",
    # o-series models with structured outputs
    "o1",
    "o1-2024-12-17",
    "o1-preview",
    "o1-mini",
    "o1-pro",
    "o1-pro-2025-03-19",
    "o3-mini",
    "o3",
    "o4-mini",
    # Legacy models (JSON mode only, not full json_schema)
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
    "gpt-4-turbo-2024-04-09",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    
    # Anthropic Claude models with structured outputs (beta)
    # Source: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
    # "Available for Claude Sonnet 4.5, Claude Opus 4.1, Claude Opus 4.5, and Claude Haiku 4.5"
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-5",
    "claude-opus-4-1-20250805",
    "claude-opus-4-1",
    "claude-opus-4-5-20251101",
    "claude-opus-4-5",
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    # Legacy Claude models (tool-based structured output)
    "claude-3-5-sonnet-latest",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-latest",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-latest",
    "claude-3-opus-20240229",
    
    # Google Gemini models with structured outputs
    # Source: https://ai.google.dev/gemini-api/docs/structured-output
    # All Gemini models support structured output
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-8b",
    "gemini-1.5-flash-8b-latest",
}

# Models that explicitly DON'T support structured outputs
MODELS_NOT_SUPPORTING_STRUCTURED_OUTPUTS = {
    # Audio preview models
    "gpt-4o-audio-preview",
    "gpt-5-nano-audio-preview",
    
    # Legacy o1 models (don't support system messages either)
    "o1-preview-2024-09-12",
    "o1-mini-2024-09-12",
}


def supports_structured_outputs(model_name: str) -> bool:
    """
    Check if a model supports OpenAI-style structured outputs.
    
    OpenAI structured outputs are supported by gpt-4o-2024-08-06 and later models.
    This includes all gpt-4.1, gpt-5, o1, o3, o4 series models.
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports structured outputs, False otherwise
    """
    if not model_name:
        return False
    
    # Strip provider prefixes (e.g., 'google/', 'openai/', etc.)
    model_without_provider = model_name
    for prefix in ['google/', 'openai/', 'anthropic/', 'gemini/', 'mistral/', 'deepseek/', 'groq/', 'azure/']:
        if model_name.startswith(prefix):
            model_without_provider = model_name[len(prefix):]
            break
    
    # First check if it's explicitly in the NOT supporting list
    if model_without_provider in MODELS_NOT_SUPPORTING_STRUCTURED_OUTPUTS:
        return False
    
    # Auto-support for newer OpenAI models (gpt-4.1+, gpt-5+, o-series)
    # Per OpenAI docs: "gpt-4o-2024-08-06 model snapshots and later"
    model_lower = model_without_provider.lower()
    
    # GPT-4.1 and later (4.1, 4.2, 4.5, etc.)
    if model_lower.startswith('gpt-4.') and not model_lower.startswith('gpt-4.0'):
        # Extract version number after 'gpt-4.'
        try:
            version_part = model_lower.split('gpt-4.')[1].split('-')[0]
            if version_part.replace('.', '').isdigit():
                version = float(version_part) if '.' in version_part else int(version_part)
                if version >= 1:  # gpt-4.1 and later
                    return True
        except (IndexError, ValueError):
            pass
    
    # GPT-5 and later series - auto support
    if model_lower.startswith('gpt-5') or model_lower.startswith('gpt-6') or model_lower.startswith('gpt-7'):
        return True
    
    # o-series models (o1, o3, o4, etc.) - auto support
    if model_lower.startswith('o1') or model_lower.startswith('o3') or model_lower.startswith('o4'):
        # Exclude legacy o1 models that don't support it
        if model_without_provider not in MODELS_NOT_SUPPORTING_STRUCTURED_OUTPUTS:
            return True
    
    # All Gemini models support structured outputs
    if model_lower.startswith('gemini'):
        return True
    
    # Claude 4+ models support structured outputs
    if 'claude' in model_lower:
        # Claude 4, 5, 6, etc. - extract version number
        import re
        # Match patterns like claude-4, claude-5, claude-sonnet-4, claude-opus-4-5, etc.
        version_match = re.search(r'claude-(?:sonnet-|opus-|haiku-)?(\d+)', model_lower)
        if version_match:
            version = int(version_match.group(1))
            if version >= 4:  # Claude 4 and later
                return True
    
    # Then check if it's in the supporting list
    if model_without_provider in MODELS_SUPPORTING_STRUCTURED_OUTPUTS:
        return True
    
    # For models with version suffixes, check the base model name
    base_model = model_without_provider.split('-2024-')[0].split('-2025-')[0]
    if base_model in MODELS_SUPPORTING_STRUCTURED_OUTPUTS:
        return True
    
    # Default to False for unknown models
    return False


def supports_streaming_with_tools(model_name: str) -> bool:
    """
    Check if a model supports streaming when tools are provided.
    Most models that support structured outputs also support streaming with tools.
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports streaming with tools, False otherwise
    """
    # For now, use the same logic as structured outputs
    # In the future, this could be a separate list if needed
    return supports_structured_outputs(model_name)


# Supported Gemini internal tools
GEMINI_INTERNAL_TOOLS = {'googleSearch', 'urlContext', 'codeExecution'}


# Models that support native web search via LiteLLM (v1.71.0+)
# These models have built-in web search capabilities
# Sources:
# - https://docs.litellm.ai/docs/completion/web_search
# - https://docs.anthropic.com/en/docs/build-with-claude/tool-use/web-search
# - https://ai.google.dev/gemini-api/docs/grounding
MODELS_SUPPORTING_WEB_SEARCH = {
    # OpenAI models with web search
    "gpt-4o-search-preview",
    "gpt-4o-search-preview-2025-03-11",
    "gpt-4o-mini-search-preview",
    "gpt-4o-mini-search-preview-2025-03-11",
    
    # xAI models with web search (includes X/Twitter data)
    "grok-3",
    "grok-3-latest",
    
    # Anthropic Claude models with web search
    # Source: https://docs.anthropic.com/en/docs/build-with-claude/tool-use/web-search
    # Claude Sonnet 4.5
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-5",
    # Claude Sonnet 4
    "claude-sonnet-4-20250514",
    "claude-sonnet-4",
    # Claude Sonnet 3.7 (deprecated)
    "claude-3-7-sonnet-20250219",
    "claude-3-7-sonnet-latest",
    # Claude Haiku 4.5
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    # Claude Haiku 3.5
    "claude-3-5-haiku-latest",
    "claude-3-5-haiku-20241022",
    # Claude Opus 4.5
    "claude-opus-4-5-20251101",
    "claude-opus-4-5",
    # Claude Opus 4.1
    "claude-opus-4-1-20250805",
    "claude-opus-4-1",
    # Claude Opus 4
    "claude-opus-4-20250514",
    "claude-opus-4",
    # Legacy Claude 3.5 Sonnet (still supported per LiteLLM)
    "claude-3-5-sonnet-latest",
    "claude-3-5-sonnet-20241022",
    
    # Google Gemini models with Grounding (Google Search)
    # Source: https://ai.google.dev/gemini-api/docs/grounding
    # Gemini 2.5
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    # Gemini 2.0
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-latest",
    # Gemini 1.5
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
}


def supports_web_search(model_name: str) -> bool:
    """
    Check if a model supports native web search via LiteLLM.
    
    Native web search allows the model to search the web in real-time
    without requiring external tools like DuckDuckGo.
    
    Supported providers:
    - OpenAI (gpt-4o-search-preview, gpt-4o-mini-search-preview, gpt-5-search-api)
    - xAI (grok-3)
    - Anthropic (claude-3-5-sonnet-latest, claude-3-7-sonnet, claude-4-*, etc.)
    - Google/Vertex AI (gemini-2.0-flash, gemini-2.5-*, etc.)
    - Perplexity (all models)
    
    Args:
        model_name: The name of the model to check (with or without provider prefix)
        
    Returns:
        bool: True if the model supports native web search, False otherwise
    """
    if not model_name:
        return False
    
    # Strip provider prefixes first
    model_without_provider = model_name
    for prefix in ['openai/', 'xai/', 'anthropic/', 'google/', 'gemini/', 'vertex_ai/', 'perplexity/']:
        if model_name.startswith(prefix):
            model_without_provider = model_name[len(prefix):]
            break
    
    # Check our static list first (most comprehensive)
    if model_without_provider in MODELS_SUPPORTING_WEB_SEARCH:
        return True
    
    # Perplexity models all support web search
    if model_name.startswith('perplexity/'):
        return True
    
    # Check base model name (without version suffix)
    base_model = model_without_provider.split('-2024-')[0].split('-2025-')[0]
    if base_model in MODELS_SUPPORTING_WEB_SEARCH:
        return True
    
    # Try LiteLLM's built-in check as fallback (for models not in our list)
    try:
        import litellm
        if hasattr(litellm, 'supports_web_search'):
            return litellm.supports_web_search(model=model_name)
    except Exception:
        pass
    
    return False


# Models that support web fetch via LiteLLM (Anthropic only)
# Web fetch retrieves full content from specific URLs (web pages and PDFs)
# Source: https://docs.litellm.ai/docs/completion/web_fetch
MODELS_SUPPORTING_WEB_FETCH = {
    # Anthropic Claude models with web fetch support
    # Claude Opus 4.1
    "claude-opus-4-1-20250805",
    "claude-opus-4-1",
    # Claude Opus 4
    "claude-opus-4-20250514",
    "claude-opus-4",
    # Claude Sonnet 4
    "claude-sonnet-4-20250514",
    "claude-sonnet-4",
    # Claude Sonnet 3.7
    "claude-3-7-sonnet-20250219",
    "claude-3-7-sonnet-latest",
    # Claude Sonnet 3.5 v2 (deprecated)
    "claude-3-5-sonnet-latest",
    "claude-3-5-sonnet-20241022",
    # Claude Haiku 3.5
    "claude-3-5-haiku-latest",
    "claude-3-5-haiku-20241022",
}


def supports_web_fetch(model_name: str) -> bool:
    """
    Check if a model supports web fetch via LiteLLM.
    
    Web fetch allows the model to retrieve full content from specific URLs
    (web pages and PDF documents). This is different from web search which
    searches the internet for information.
    
    Currently only supported by Anthropic Claude models.
    
    Supported models:
    - claude-opus-4-1-20250805 (Claude Opus 4.1)
    - claude-opus-4-20250514 (Claude Opus 4)
    - claude-sonnet-4-20250514 (Claude Sonnet 4)
    - claude-3-7-sonnet-20250219 (Claude Sonnet 3.7)
    - claude-3-5-sonnet-latest (Claude Sonnet 3.5 v2)
    - claude-3-5-haiku-latest (Claude Haiku 3.5)
    
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