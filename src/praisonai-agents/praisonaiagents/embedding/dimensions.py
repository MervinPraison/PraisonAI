"""
Embedding dimension utilities.

This module provides utilities for determining embedding dimensions
based on model names. Consolidates the dimension lookup logic that
was previously duplicated in memory.py and knowledge.py.
"""

from typing import Dict

# Common embedding model dimensions
# This is the single source of truth for dimension lookup
MODEL_DIMENSIONS: Dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "text-embedding-002": 1536,
    # Cohere models
    "embed-english-v3.0": 1024,
    "embed-multilingual-v3.0": 1024,
    "embed-english-light-v3.0": 384,
    "embed-multilingual-light-v3.0": 384,
    # Voyage models
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-code-3": 1024,
    # Mistral models
    "mistral-embed": 1024,
    # Jina models
    "jina-embeddings-v3": 1024,
    "jina-embeddings-v2-base-en": 768,
    # HuggingFace common models
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "bge-large-en-v1.5": 1024,
    "bge-base-en-v1.5": 768,
    "bge-small-en-v1.5": 384,
}

# Default dimension for unknown models
DEFAULT_DIMENSION = 1536


def get_dimensions(model_name: str) -> int:
    """Get embedding dimensions based on model name.
    
    This function checks if the model name contains any known model
    identifiers and returns the corresponding dimension. Falls back
    to the default dimension (1536) for unknown models.
    
    Args:
        model_name: The embedding model name (e.g., "text-embedding-3-small")
    
    Returns:
        The embedding dimension for the model
    
    Example:
        >>> get_dimensions("text-embedding-3-small")
        1536
        >>> get_dimensions("openai/text-embedding-3-large")
        3072
        >>> get_dimensions("unknown-model")
        1536
    """
    model_lower = model_name.lower()
    
    # Check for exact match first
    if model_lower in MODEL_DIMENSIONS:
        return MODEL_DIMENSIONS[model_lower]
    
    # Check if model name contains known model identifiers
    for model_key, dimensions in MODEL_DIMENSIONS.items():
        if model_key in model_lower:
            return dimensions
    
    # Default to 1536 for unknown models (OpenAI standard)
    return DEFAULT_DIMENSION
