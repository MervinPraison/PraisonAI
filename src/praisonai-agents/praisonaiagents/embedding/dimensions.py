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
    # Locally-served embedders (Ollama tags). Dimensions measured by embedding a
    # probe string through a live Ollama 0.33.2 and counting the returned vector,
    # cross-checked against `<family>.embedding_length` from /api/show. Without
    # these every local embedder inherited DEFAULT_DIMENSION (1536, OpenAI's),
    # so a vector index was built 2x-4x the size the model actually produces.
    "nomic-embed-text": 768,      # measured
    "mxbai-embed-large": 1024,    # measured
    "all-minilm": 384,            # measured; Ollama's short tag for all-MiniLM
    # HuggingFace common models
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "bge-large-en-v1.5": 1024,
    "bge-base-en-v1.5": 768,
    "bge-small-en-v1.5": 384,
}

# Default dimension for unknown models
DEFAULT_DIMENSION = 1536

# Precomputed lowercased lookup so mixed-case keys (e.g. "all-MiniLM-L6-v2")
# resolve on the exact-match path, and precomputed length-descending entries
# so specific keys ("voyage-3-lite") win over prefixes ("voyage-3") without
# sorting/lowercasing on every call.
_LOWER_MODEL_DIMENSIONS: Dict[str, int] = {
    key.lower(): value for key, value in MODEL_DIMENSIONS.items()
}
_SORTED_MODEL_DIMENSIONS = sorted(
    _LOWER_MODEL_DIMENSIONS.items(), key=lambda item: len(item[0]), reverse=True
)


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
        >>> get_dimensions("ollama/nomic-embed-text:v1.5")
        768
        >>> get_dimensions("unknown-model")
        1536
    """
    model_lower = model_name.lower()

    # Check for exact match first (lowercased lookup handles mixed-case keys)
    if model_lower in _LOWER_MODEL_DIMENSIONS:
        return _LOWER_MODEL_DIMENSIONS[model_lower]

    # Local models are written the way their runtime names them:
    # "ollama/nomic-embed-text:v1.5". Strip the litellm-style provider prefix
    # and the version tag, then retry the exact match, so a tagged local model
    # resolves instead of falling through to the OpenAI default.
    normalised = model_lower.rsplit("/", 1)[-1].split(":", 1)[0]
    if normalised != model_lower and normalised in _LOWER_MODEL_DIMENSIONS:
        return _LOWER_MODEL_DIMENSIONS[normalised]
    
    # Check if model name contains known model identifiers.
    # Entries are pre-sorted by key length (longest first) so more specific
    # keys like "voyage-3-lite" match before shorter prefixes like "voyage-3".
    for model_key, dimensions in _SORTED_MODEL_DIMENSIONS:
        if model_key in model_lower or model_key in normalised:
            return dimensions
    
    # Default to 1536 for unknown models (OpenAI standard)
    return DEFAULT_DIMENSION
