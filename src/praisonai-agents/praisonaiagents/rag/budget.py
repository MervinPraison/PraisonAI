"""
Token Budget Infrastructure for PraisonAI Agents.

Provides dynamic token budget calculation for context building.
Ensures retrieved context never exceeds available token budget.

No heavy imports - only stdlib and typing.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# Model context window mapping (tokens)
# Updated with latest model information
MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    # OpenAI models
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4.1": 1000000,
    "gpt-4.1-mini": 1000000,
    "gpt-4.1-nano": 1000000,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "o1": 200000,
    "o1-mini": 128000,
    "o1-preview": 128000,
    "o3": 200000,
    "o3-mini": 200000,
    "o4-mini": 200000,
    
    # Anthropic models
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3.5-sonnet": 200000,
    "claude-3.5-haiku": 200000,
    "claude-3.7-sonnet": 200000,
    "claude-4-sonnet": 200000,
    "claude-sonnet-4": 200000,
    
    # Google models
    "gemini-pro": 32768,
    "gemini-1.0-pro": 32768,
    "gemini-1.5-pro": 1000000,
    "gemini-1.5-flash": 1000000,
    "gemini-2.0-flash": 1000000,
    "gemini-2.5-pro": 1000000,
    "gemini-2.5-flash": 1000000,
    
    # Mistral models
    "mistral-large": 128000,
    "mistral-medium": 32768,
    "mistral-small": 32768,
    "mixtral-8x7b": 32768,
    
    # Llama models
    "llama-3.1-405b": 128000,
    "llama-3.1-70b": 128000,
    "llama-3.1-8b": 128000,
    "llama-3.2-90b": 128000,
    "llama-3.2-11b": 128000,
    "llama-3.3-70b": 128000,
    "llama-4-maverick": 1000000,
    "llama-4-scout": 10000000,
    
    # DeepSeek models
    "deepseek-chat": 64000,
    "deepseek-coder": 64000,
    "deepseek-r1": 64000,
    
    # Cohere models
    "command-r": 128000,
    "command-r-plus": 128000,
}

# Default fallback for unknown models
DEFAULT_CONTEXT_WINDOW = 8192


def get_model_context_window(model_name: Optional[str]) -> int:
    """
    Get the context window size for a model.
    
    Args:
        model_name: Name of the model (e.g., "gpt-4-turbo", "claude-3-opus")
        
    Returns:
        Context window size in tokens
    """
    if not model_name:
        return DEFAULT_CONTEXT_WINDOW
    
    # Normalize model name
    model_lower = model_name.lower().strip()
    
    # Direct lookup
    if model_lower in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_lower]
    
    # Prefix matching for versioned models
    for prefix, tokens in MODEL_CONTEXT_WINDOWS.items():
        if model_lower.startswith(prefix):
            return tokens
    
    # Pattern matching for common patterns
    if "gpt-4o" in model_lower or "gpt-4-turbo" in model_lower:
        return 128000
    if "gpt-4" in model_lower:
        return 8192
    if "gpt-3.5" in model_lower:
        return 16385
    if "claude-3" in model_lower or "claude-4" in model_lower:
        return 200000
    if "gemini-1.5" in model_lower or "gemini-2" in model_lower:
        return 1000000
    if "gemini" in model_lower:
        return 32768
    if "llama-4" in model_lower:
        return 1000000
    if "llama-3" in model_lower:
        return 128000
    if "mistral" in model_lower or "mixtral" in model_lower:
        return 32768
    if "deepseek" in model_lower:
        return 64000
    if "command" in model_lower:
        return 128000
    
    return DEFAULT_CONTEXT_WINDOW


@dataclass
class TokenBudget:
    """
    Dynamic token budget calculation for context building.
    
    Calculates available tokens for retrieved context based on:
    - Model's maximum context window
    - Reserved tokens for response generation
    - Reserved tokens for system prompt
    - Reserved tokens for conversation history
    
    Attributes:
        model_max_tokens: Model's maximum context window
        reserved_response_tokens: Tokens reserved for response generation
        reserved_system_tokens: Tokens reserved for system prompt
        reserved_history_tokens: Tokens reserved for conversation history
    """
    model_max_tokens: int = 128000
    reserved_response_tokens: int = 4096
    reserved_system_tokens: int = 1000
    reserved_history_tokens: int = 2000
    
    @property
    def max_context_tokens(self) -> int:
        """
        Calculate maximum tokens available for retrieved context.
        
        This is the static budget based on reserved allocations.
        """
        available = (
            self.model_max_tokens
            - self.reserved_response_tokens
            - self.reserved_system_tokens
            - self.reserved_history_tokens
        )
        return max(0, available)
    
    def dynamic_budget(
        self,
        prompt_tokens: int = 0,
        history_tokens: int = 0,
        system_tokens: int = 0,
    ) -> int:
        """
        Calculate remaining tokens for context after accounting for actual usage.
        
        Args:
            prompt_tokens: Actual tokens used by current prompt
            history_tokens: Actual tokens used by conversation history
            system_tokens: Actual tokens used by system prompt
            
        Returns:
            Remaining tokens available for retrieved context
        """
        used = (
            prompt_tokens
            + history_tokens
            + system_tokens
            + self.reserved_response_tokens
        )
        remaining = self.model_max_tokens - used
        return max(0, remaining)
    
    @classmethod
    def from_model(cls, model_name: Optional[str], **kwargs) -> "TokenBudget":
        """
        Create TokenBudget from model name.
        
        Args:
            model_name: Name of the model
            **kwargs: Override default reserved token values
            
        Returns:
            TokenBudget configured for the model
        """
        context_window = get_model_context_window(model_name)
        return cls(model_max_tokens=context_window, **kwargs)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_max_tokens": self.model_max_tokens,
            "reserved_response_tokens": self.reserved_response_tokens,
            "reserved_system_tokens": self.reserved_system_tokens,
            "reserved_history_tokens": self.reserved_history_tokens,
            "max_context_tokens": self.max_context_tokens,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenBudget":
        """Create from dictionary."""
        return cls(
            model_max_tokens=data.get("model_max_tokens", 128000),
            reserved_response_tokens=data.get("reserved_response_tokens", 4096),
            reserved_system_tokens=data.get("reserved_system_tokens", 1000),
            reserved_history_tokens=data.get("reserved_history_tokens", 2000),
        )


@runtime_checkable
class BudgetEnforcerProtocol(Protocol):
    """
    Protocol for enforcing token budgets on retrieved chunks.
    
    Implementations must provide an enforce method that truncates
    chunks to fit within the available token budget.
    """
    
    def enforce(
        self,
        chunks: List[Dict[str, Any]],
        budget: TokenBudget,
        prompt_tokens: int = 0,
        history_tokens: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Enforce token budget on chunks.
        
        Args:
            chunks: List of chunks with 'text' and 'metadata' keys
            budget: TokenBudget instance
            prompt_tokens: Tokens used by current prompt
            history_tokens: Tokens used by conversation history
            
        Returns:
            Truncated list of chunks that fit within budget
        """
        ...


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    
    Uses a simple heuristic: ~4 characters per token for English text.
    This is a fast approximation; for exact counts, use tiktoken.
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    # Average of 4 characters per token for English
    # This is a conservative estimate
    return len(text) // 4 + 1


class DefaultBudgetEnforcer:
    """
    Default implementation of BudgetEnforcerProtocol.
    
    Truncates chunks to fit within available token budget.
    Uses simple token estimation for speed.
    """
    
    def __init__(self, token_estimator=None):
        """
        Initialize enforcer.
        
        Args:
            token_estimator: Optional custom token estimation function
        """
        self._token_estimator = token_estimator or estimate_tokens
    
    def enforce(
        self,
        chunks: List[Dict[str, Any]],
        budget: TokenBudget,
        prompt_tokens: int = 0,
        history_tokens: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Enforce token budget on chunks.
        
        Iteratively adds chunks until budget is exhausted.
        """
        available = budget.dynamic_budget(
            prompt_tokens=prompt_tokens,
            history_tokens=history_tokens,
        )
        
        result = []
        used_tokens = 0
        
        for chunk in chunks:
            text = chunk.get("text", "")
            chunk_tokens = self._token_estimator(text)
            
            if used_tokens + chunk_tokens <= available:
                result.append(chunk)
                used_tokens += chunk_tokens
            else:
                # Try to fit partial chunk if there's remaining space
                remaining = available - used_tokens
                if remaining > 100:  # Only if meaningful space remains
                    # Truncate text to fit
                    chars_to_keep = remaining * 4  # Approximate
                    truncated_text = text[:chars_to_keep]
                    if truncated_text:
                        truncated_chunk = {
                            **chunk,
                            "text": truncated_text + "...",
                            "metadata": {
                                **chunk.get("metadata", {}),
                                "_truncated": True,
                            },
                        }
                        result.append(truncated_chunk)
                break
        
        return result
