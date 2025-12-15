"""
Model capabilities configuration for different LLM providers.
This module defines which models support specific features like structured outputs.
"""

# Models that support OpenAI-style structured outputs (response_format with Pydantic models)
MODELS_SUPPORTING_STRUCTURED_OUTPUTS = {
    # OpenAI models
    "gpt-5-nano",
    "gpt-5-nano",
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
    "gpt-4-turbo-2024-04-09",
    "gpt-4-1106-preview",
    "gpt-4-0125-preview",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    
    # New/Future OpenAI models (as mentioned by user)
    "codex-mini",
    "o3-pro",
    "gpt-4.5-preview",
    "o3-mini",
    "o1",
    "o1-preview",
    "o1-mini",
    "gpt-4.1",
    "gpt-4.1-nano",
    "gpt-4.1-mini",
    "o4-mini",
    "o3",
    
    # Gemini models that support structured outputs
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
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
    
    Args:
        model_name: The name of the model to check
        
    Returns:
        bool: True if the model supports structured outputs, False otherwise
    """
    if not model_name:
        return False
    
    # Strip provider prefixes (e.g., 'google/', 'openai/', etc.)
    model_without_provider = model_name
    for prefix in ['google/', 'openai/', 'anthropic/', 'gemini/', 'mistral/', 'deepseek/', 'groq/']:
        if model_name.startswith(prefix):
            model_without_provider = model_name[len(prefix):]
            break
    
    # First check if it's explicitly in the NOT supporting list
    if model_without_provider in MODELS_NOT_SUPPORTING_STRUCTURED_OUTPUTS:
        return False
    
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