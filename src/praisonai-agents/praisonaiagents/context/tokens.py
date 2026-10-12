"""
Token Estimation for PraisonAI Agents.

Provides fast, offline token estimation with optional accurate tokenizer support.
"""

from functools import lru_cache
from typing import List, Dict, Any, Optional
import json


# Token estimation constants (based on OpenAI tokenizer patterns)
ASCII_TOKENS_PER_CHAR = 0.25  # ~4 chars per token for ASCII
NON_ASCII_TOKENS_PER_CHAR = 1.3  # CJK and other scripts are denser

# Optional tokenizer cache
_tokenizer_cache: Dict[str, Any] = {}


def estimate_tokens_heuristic(text: str) -> int:
    """
    Estimate token count using character-based heuristic.
    
    Fast and works offline. Accuracy: ~85-95% for English text.
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # C-speed counting instead of a per-character Python loop
    if text.isascii():
        return max(1, int(len(text) * ASCII_TOKENS_PER_CHAR))
    ascii_count = len(text.encode("ascii", "ignore"))
    total = (ascii_count * ASCII_TOKENS_PER_CHAR
             + (len(text) - ascii_count) * NON_ASCII_TOKENS_PER_CHAR)
    
    return max(1, int(total))


def _get_tiktoken_encoder(model: str):
    """Return a cached tiktoken encoder for ``model``, or None if unavailable.

    Failures (tiktoken missing, vocab download blocked) are negatively cached
    so we never retry a failing load on every message.
    """
    cache_key = model.lower()
    if cache_key in _tokenizer_cache:
        return _tokenizer_cache[cache_key]
    enc = None
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            # Unknown model (or failed load): cl100k_base is a close match for
            # GPT-4/3.5/Claude-style tokenisation
            enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        enc = None
    _tokenizer_cache[cache_key] = enc
    return enc


def estimate_tokens_accurate(text: str, model: str = "gpt-4") -> int:
    """
    Estimate tokens using tiktoken if available, else fallback to heuristic.
    
    Args:
        text: Text to estimate tokens for
        model: Model name for tokenizer selection
        
    Returns:
        Token count
    """
    if _get_tiktoken_encoder(model) is None:
        return estimate_tokens_heuristic(text)
    return _count_tiktoken_tokens(text, model)


@lru_cache(maxsize=4096)
def _count_tiktoken_tokens(text: str, model: str) -> int:
    # History messages are re-counted several times per turn; memoise them.
    try:
        return len(_get_tiktoken_encoder(model).encode(text))
    except Exception:
        # Fallback on any tokenization error
        return estimate_tokens_heuristic(text)


def estimate_message_tokens(message: Dict[str, Any], use_accurate: bool = False) -> int:
    """
    Estimate tokens for a single message.
    
    Handles various message formats including tool calls and multi-part content.
    
    Args:
        message: Message dict with role and content
        use_accurate: Use tiktoken if available
        
    Returns:
        Estimated token count
    """
    estimate_fn = estimate_tokens_accurate if use_accurate else estimate_tokens_heuristic
    
    total = 0
    
    # Role overhead (~4 tokens for role markers)
    total += 4
    
    # Content
    content = message.get("content", "")
    if isinstance(content, str):
        total += estimate_fn(content)
    elif isinstance(content, list):
        # Multi-part content (text, images, etc.)
        for part in content:
            if isinstance(part, dict):
                if "text" in part:
                    total += estimate_fn(str(part["text"]))
                elif "type" in part:
                    # Image or other media - estimate based on type
                    if part.get("type") == "image_url":
                        total += 85  # Base image token cost
                    else:
                        total += estimate_fn(json.dumps(part))
            else:
                total += estimate_fn(str(part))
    
    # Tool calls
    if "tool_calls" in message:
        for tool_call in message.get("tool_calls", []):
            if isinstance(tool_call, dict):
                # Function name and arguments
                func = tool_call.get("function", {})
                total += estimate_fn(func.get("name", ""))
                total += estimate_fn(func.get("arguments", ""))
                total += 10  # Overhead for tool call structure
    
    # Tool call ID (for tool responses)
    if "tool_call_id" in message:
        total += 10
    
    # Name field
    if "name" in message:
        total += estimate_fn(message["name"])
    
    return total


def estimate_messages_tokens(
    messages: List[Dict[str, Any]],
    use_accurate: bool = False
) -> int:
    """
    Estimate total tokens for a list of messages.
    
    Args:
        messages: List of message dicts
        use_accurate: Use tiktoken if available
        
    Returns:
        Total estimated token count
    """
    if not messages:
        return 0
    
    total = 0
    for msg in messages:
        total += estimate_message_tokens(msg, use_accurate)
    
    # Add overhead for message array structure
    total += 3  # Array markers
    
    return total


def estimate_tool_schema_tokens(
    tools: List[Dict[str, Any]],
    use_accurate: bool = False
) -> int:
    """
    Estimate tokens for tool/function schemas.
    
    Args:
        tools: List of tool definitions
        use_accurate: Use tiktoken if available
        
    Returns:
        Estimated token count
    """
    if not tools:
        return 0
    
    estimate_fn = estimate_tokens_accurate if use_accurate else estimate_tokens_heuristic
    
    # Serialize tools to JSON and estimate
    try:
        tools_json = json.dumps(tools)
        return estimate_fn(tools_json)
    except (TypeError, ValueError):
        # Fallback: estimate per-tool
        total = 0
        for tool in tools:
            if isinstance(tool, dict):
                total += estimate_fn(json.dumps(tool))
            else:
                total += 100  # Default estimate per tool
        return total


class TokenEstimatorImpl:
    """
    Token estimator implementation.
    
    Provides both heuristic and accurate estimation methods.
    """
    
    def __init__(self, use_accurate: bool = False, model: str = "gpt-4"):
        """
        Initialize estimator.
        
        Args:
            use_accurate: Use tiktoken if available
            model: Model name for tokenizer selection
        """
        self.use_accurate = use_accurate
        self.model = model
    
    def estimate(self, text: str) -> int:
        """Estimate tokens for text."""
        if self.use_accurate:
            return estimate_tokens_accurate(text, self.model)
        return estimate_tokens_heuristic(text)
    
    def estimate_messages(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate tokens for messages."""
        return estimate_messages_tokens(messages, self.use_accurate)
    
    def estimate_tools(self, tools: List[Dict[str, Any]]) -> int:
        """Estimate tokens for tool schemas."""
        return estimate_tool_schema_tokens(tools, self.use_accurate)


# Default estimator instance
_default_estimator: Optional[TokenEstimatorImpl] = None


def get_estimator(use_accurate: bool = False, model: str = "gpt-4") -> TokenEstimatorImpl:
    """Get or create a token estimator."""
    global _default_estimator
    
    if _default_estimator is None or _default_estimator.use_accurate != use_accurate:
        _default_estimator = TokenEstimatorImpl(use_accurate, model)
    
    return _default_estimator
