"""
Model capabilities configuration for different LLM providers.
This module defines which models support specific features like structured outputs.
"""

# Models that support OpenAI-style structured outputs (response_format with Pydantic models)
MODELS_SUPPORTING_STRUCTURED_OUTPUTS = {
    # OpenAI models
    "gpt-4o",
    "gpt-4o-mini",
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
}

# Models that explicitly DON'T support structured outputs
MODELS_NOT_SUPPORTING_STRUCTURED_OUTPUTS = {
    # Audio preview models
    "gpt-4o-audio-preview",
    "gpt-4o-mini-audio-preview",
    
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
    
    # First check if it's explicitly in the NOT supporting list
    if model_name in MODELS_NOT_SUPPORTING_STRUCTURED_OUTPUTS:
        return False
    
    # Then check if it's in the supporting list
    if model_name in MODELS_SUPPORTING_STRUCTURED_OUTPUTS:
        return True
    
    # For models with version suffixes, check the base model name
    base_model = model_name.split('-2024-')[0].split('-2025-')[0]
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