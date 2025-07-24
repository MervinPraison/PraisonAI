import os

# Ensure litellm telemetry is disabled before imports
os.environ["LITELLM_TELEMETRY"] = "False"

# Import modules
from .llm import LLM, LLMContextLengthExceededException
from .openai_client import (
    OpenAIClient, 
    get_openai_client,
    ChatCompletionMessage,
    Choice,
    CompletionTokensDetails,
    PromptTokensDetails,
    CompletionUsage,
    ChatCompletion,
    ToolCall,
    process_stream_chunks
)
from .model_capabilities import (
    supports_structured_outputs,
    supports_streaming_with_tools
)
from .model_router import (
    ModelRouter,
    ModelProfile, 
    TaskComplexity,
    create_routing_agent
)

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
    "create_routing_agent"
]