"""
LLM Module for PraisonAI Agents.

This module provides language model integrations with lazy loading
to minimize import time when LLM functionality is not immediately needed.
"""
import os

# Ensure litellm telemetry is disabled before any imports
os.environ["LITELLM_TELEMETRY"] = "False"

# Module-level cache for lazy-loaded classes
_lazy_cache = {}


def __getattr__(name):
    """Lazy load LLM classes to avoid importing litellm at module load time."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "LLM":
        from .llm import LLM
        _lazy_cache[name] = LLM
        return LLM
    elif name == "LLMContextLengthExceededException":
        from .llm import LLMContextLengthExceededException
        _lazy_cache[name] = LLMContextLengthExceededException
        return LLMContextLengthExceededException
    elif name == "OpenAIClient":
        from .openai_client import OpenAIClient
        _lazy_cache[name] = OpenAIClient
        return OpenAIClient
    elif name == "get_openai_client":
        from .openai_client import get_openai_client
        _lazy_cache[name] = get_openai_client
        return get_openai_client
    elif name == "ChatCompletionMessage":
        from .openai_client import ChatCompletionMessage
        _lazy_cache[name] = ChatCompletionMessage
        return ChatCompletionMessage
    elif name == "Choice":
        from .openai_client import Choice
        _lazy_cache[name] = Choice
        return Choice
    elif name == "CompletionTokensDetails":
        from .openai_client import CompletionTokensDetails
        _lazy_cache[name] = CompletionTokensDetails
        return CompletionTokensDetails
    elif name == "PromptTokensDetails":
        from .openai_client import PromptTokensDetails
        _lazy_cache[name] = PromptTokensDetails
        return PromptTokensDetails
    elif name == "CompletionUsage":
        from .openai_client import CompletionUsage
        _lazy_cache[name] = CompletionUsage
        return CompletionUsage
    elif name == "ChatCompletion":
        from .openai_client import ChatCompletion
        _lazy_cache[name] = ChatCompletion
        return ChatCompletion
    elif name == "ToolCall":
        from .openai_client import ToolCall
        _lazy_cache[name] = ToolCall
        return ToolCall
    elif name == "process_stream_chunks":
        from .openai_client import process_stream_chunks
        _lazy_cache[name] = process_stream_chunks
        return process_stream_chunks
    elif name == "supports_structured_outputs":
        from .model_capabilities import supports_structured_outputs
        _lazy_cache[name] = supports_structured_outputs
        return supports_structured_outputs
    elif name == "supports_streaming_with_tools":
        from .model_capabilities import supports_streaming_with_tools
        _lazy_cache[name] = supports_streaming_with_tools
        return supports_streaming_with_tools
    elif name == "ModelRouter":
        from .model_router import ModelRouter
        _lazy_cache[name] = ModelRouter
        return ModelRouter
    elif name == "ModelProfile":
        from .model_router import ModelProfile
        _lazy_cache[name] = ModelProfile
        return ModelProfile
    elif name == "TaskComplexity":
        from .model_router import TaskComplexity
        _lazy_cache[name] = TaskComplexity
        return TaskComplexity
    elif name == "create_routing_agent":
        from .model_router import create_routing_agent
        _lazy_cache[name] = create_routing_agent
        return create_routing_agent
    elif name == "RateLimiter":
        from .rate_limiter import RateLimiter
        _lazy_cache[name] = RateLimiter
        return RateLimiter
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLM", 
    "LLMContextLengthExceededException", 
    "OpenAIClient", 
    "get_openai_client",
    "ChatCompletionMessage",
    "Choice",
    "CompletionTokensDetails",
    "PromptTokensDetails",
    "CompletionUsage",
    "ChatCompletion",
    "ToolCall",
    "process_stream_chunks",
    "supports_structured_outputs",
    "supports_streaming_with_tools",
    "ModelRouter",
    "ModelProfile",
    "TaskComplexity",
    "create_routing_agent",
    "RateLimiter"
]
