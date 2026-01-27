"""
Token estimation and context length utilities.

Provides lightweight token counting and context length detection
without requiring external dependencies (tiktoken, etc.).

For more accurate token counting, litellm is used when available.

Zero Performance Impact:
- No module-level imports of optional dependencies
- Lazy loading of litellm
- Simple fallback algorithms

Example:
    >>> from praisonaiagents.eval.tokens import estimate_tokens, needs_chunking
    >>> tokens = estimate_tokens("Hello world")
    >>> if needs_chunking(large_text, "gpt-4o-mini"):
    ...     # Split into chunks
"""

import logging
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)


# Default context lengths for common models (fallback when litellm unavailable)
# Based on official documentation as of January 2025
DEFAULT_CONTEXT_LENGTHS: Dict[str, int] = {
    # OpenAI models
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "o1": 200000,
    "o1-mini": 128000,
    "o1-preview": 128000,
    "o3-mini": 200000,
    
    # Anthropic models
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-5-sonnet-latest": 200000,
    "claude-3-5-haiku-20241022": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "claude-2.1": 200000,
    "claude-2": 100000,
    
    # Google models
    "gemini-1.5-pro": 2097152,
    "gemini-1.5-flash": 1048576,
    "gemini-1.5-flash-8b": 1048576,
    "gemini-2.0-flash-exp": 1048576,
    "gemini-pro": 32760,
    
    # Mistral models
    "mistral-large-latest": 128000,
    "mistral-medium-latest": 32000,
    "mistral-small-latest": 32000,
    "codestral-latest": 32000,
    
    # DeepSeek models
    "deepseek-chat": 64000,
    "deepseek-coder": 64000,
    
    # Groq models
    "llama-3.3-70b-versatile": 128000,
    "llama-3.1-70b-versatile": 128000,
    "llama-3.1-8b-instant": 128000,
    "mixtral-8x7b-32768": 32768,
}

# Default context length for unknown models
DEFAULT_CONTEXT_LENGTH = 128000


def estimate_tokens(
    text: str,
    method: str = "max",
) -> int:
    """
    Estimate token count without external dependencies.
    
    Uses heuristics based on OpenAI's guidance:
    - ~4 characters per token for English text
    - ~0.75 tokens per word
    
    Args:
        text: Text to estimate tokens for
        method: Estimation method
            - "chars": Character count / 4
            - "words": Word count / 0.75
            - "max": Maximum of chars and words (default, conservative)
            - "min": Minimum of chars and words (optimistic)
            - "average": Average of chars and words
    
    Returns:
        Estimated token count
    
    Example:
        >>> estimate_tokens("Hello world")
        3
        >>> estimate_tokens("Hello world", method="chars")
        2
    """
    if not text:
        return 0
    
    # Character-based estimation (4 chars per token)
    char_count = len(text)
    tokens_by_chars = char_count // 4
    
    # Word-based estimation (0.75 tokens per word, i.e., 1 word = 1.33 tokens)
    word_count = len(text.split())
    tokens_by_words = int(word_count / 0.75)
    
    if method == "chars":
        return tokens_by_chars
    elif method == "words":
        return tokens_by_words
    elif method == "min":
        return min(tokens_by_chars, tokens_by_words)
    elif method == "average":
        return (tokens_by_chars + tokens_by_words) // 2
    else:  # "max" (default - conservative)
        return max(tokens_by_chars, tokens_by_words)


def get_context_length(
    model: str,
    use_litellm: bool = True,
) -> int:
    """
    Get the context window size for a model.
    
    Attempts to use litellm's model_cost for accurate info, falls back to built-in defaults.
    
    Note: litellm.get_max_tokens() returns OUTPUT token limit, not context window.
    We use model_cost['max_input_tokens'] which is the actual context window.
    
    Args:
        model: Model name (e.g., "gpt-4o-mini", "claude-3-5-sonnet-20241022")
        use_litellm: Whether to try litellm first (default: True)
    
    Returns:
        Context window size in tokens
    
    Example:
        >>> get_context_length("gpt-4o-mini")
        128000
        >>> get_context_length("claude-3-5-sonnet-20241022")
        200000
    """
    # Try litellm's model_cost first if available and requested
    # Note: get_max_tokens returns OUTPUT limit, model_cost has INPUT context window
    if use_litellm:
        try:
            from litellm import model_cost
            model_lower = model.lower()
            
            # Direct lookup
            if model_lower in model_cost:
                info = model_cost[model_lower]
                # Prefer max_input_tokens (context window), fallback to max_tokens
                if 'max_input_tokens' in info and info['max_input_tokens']:
                    return info['max_input_tokens']
                if 'max_tokens' in info and info['max_tokens']:
                    return info['max_tokens']
            
            # Try with provider prefix removed
            if "/" in model:
                base_model = model.split("/")[-1].lower()
                if base_model in model_cost:
                    info = model_cost[base_model]
                    if 'max_input_tokens' in info and info['max_input_tokens']:
                        return info['max_input_tokens']
                    if 'max_tokens' in info and info['max_tokens']:
                        return info['max_tokens']
        except ImportError:
            pass  # litellm not installed
        except Exception as e:
            logger.debug(f"litellm.model_cost lookup failed for {model}: {e}")
    
    # Normalize model name for lookup
    model_lower = model.lower()
    
    # Direct lookup
    if model_lower in DEFAULT_CONTEXT_LENGTHS:
        return DEFAULT_CONTEXT_LENGTHS[model_lower]
    
    # Try partial matching for versioned models
    for known_model, context_len in DEFAULT_CONTEXT_LENGTHS.items():
        if known_model in model_lower or model_lower in known_model:
            return context_len
    
    # Check for provider prefixes (e.g., "openai/gpt-4o-mini")
    if "/" in model:
        base_model = model.split("/")[-1].lower()
        if base_model in DEFAULT_CONTEXT_LENGTHS:
            return DEFAULT_CONTEXT_LENGTHS[base_model]
        for known_model, context_len in DEFAULT_CONTEXT_LENGTHS.items():
            if known_model in base_model or base_model in known_model:
                return context_len
    
    # Default fallback
    logger.debug(f"Unknown model '{model}', using default context length {DEFAULT_CONTEXT_LENGTH}")
    return DEFAULT_CONTEXT_LENGTH


def count_tokens(
    text: str,
    model: str = "gpt-4o-mini",
    messages: Optional[list] = None,
    use_litellm: bool = True,
) -> int:
    """
    Count tokens, using litellm if available, otherwise estimate.
    
    Args:
        text: Text to count tokens for
        model: Model name for tokenizer selection
        messages: Optional list of message dicts (for chat format)
        use_litellm: Whether to try litellm (default: True)
    
    Returns:
        Token count (accurate if litellm available, estimated otherwise)
    
    Example:
        >>> count_tokens("Hello world", model="gpt-4o-mini")
        2
    """
    # For very large text (>100K chars), skip litellm to avoid slowness
    # and use estimation instead
    if len(text) > 100000:
        use_litellm = False
    
    # Try litellm first
    if use_litellm:
        try:
            from litellm import token_counter
            if messages:
                return token_counter(model=model, messages=messages)
            else:
                return token_counter(model=model, text=text)
        except ImportError:
            pass  # litellm not installed
        except Exception as e:
            logger.debug(f"litellm.token_counter failed: {e}")
    
    # Fallback to estimation
    return estimate_tokens(text, method="max")


def needs_chunking(
    text: str,
    model: str = "gpt-4o-mini",
    safety_margin: float = 0.8,
    return_info: bool = False,
) -> Union[bool, Dict]:
    """
    Determine if text needs to be chunked for the given model.
    
    Compares estimated token count against model's context window
    with a safety margin for prompt overhead.
    
    Args:
        text: Text to evaluate
        model: Model name to check context window for
        safety_margin: Fraction of context window to use (default: 0.8 = 80%)
            This leaves room for system prompt, instructions, and response.
        return_info: If True, return detailed info dict instead of bool
    
    Returns:
        bool: True if chunking is needed
        dict: If return_info=True, returns detailed analysis
    
    Example:
        >>> needs_chunking("Hello world", "gpt-4o-mini")
        False
        >>> needs_chunking(very_large_text, "gpt-4o-mini")
        True
        >>> needs_chunking(text, "gpt-4o-mini", return_info=True)
        {'needs_chunking': False, 'estimated_tokens': 100, 'context_length': 128000, 'utilization': 0.0008}
    """
    estimated_tokens = count_tokens(text, model=model)
    context_length = get_context_length(model)
    available_tokens = int(context_length * safety_margin)
    utilization = estimated_tokens / context_length if context_length > 0 else 1.0
    
    needs_chunk = estimated_tokens > available_tokens
    
    if return_info:
        return {
            "needs_chunking": needs_chunk,
            "estimated_tokens": estimated_tokens,
            "context_length": context_length,
            "available_tokens": available_tokens,
            "safety_margin": safety_margin,
            "utilization": round(utilization, 4),
        }
    
    return needs_chunk


def get_recommended_chunk_size(
    model: str = "gpt-4o-mini",
    target_chunks: int = 5,
    safety_margin: float = 0.8,
) -> int:
    """
    Get recommended chunk size in characters for a model.
    
    Calculates optimal chunk size based on model's context window
    and desired number of chunks.
    
    Args:
        model: Model name
        target_chunks: Target number of chunks (default: 5)
        safety_margin: Fraction of context to use (default: 0.8)
    
    Returns:
        Recommended chunk size in characters
    
    Example:
        >>> get_recommended_chunk_size("gpt-4o-mini")
        8192
    """
    context_length = get_context_length(model)
    available_tokens = int(context_length * safety_margin)
    
    # Tokens per chunk
    tokens_per_chunk = available_tokens // target_chunks
    
    # Convert to characters (4 chars per token)
    chars_per_chunk = tokens_per_chunk * 4
    
    # Clamp to reasonable range
    min_chunk = 4000
    max_chunk = 16000
    
    return max(min_chunk, min(max_chunk, chars_per_chunk))


__all__ = [
    "estimate_tokens",
    "get_context_length",
    "count_tokens",
    "needs_chunking",
    "get_recommended_chunk_size",
    "DEFAULT_CONTEXT_LENGTHS",
    "DEFAULT_CONTEXT_LENGTH",
]
