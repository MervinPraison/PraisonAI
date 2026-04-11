"""
LLM Provider Adapters

Concrete implementations of LLMProviderAdapter protocol that replace
scattered provider dispatch logic throughout the core.

This demonstrates the protocol-driven approach for Gap 2.
"""

from ..protocols import LLMProviderAdapterProtocol
from ..model_capabilities import GEMINI_INTERNAL_TOOLS
from typing import Dict, Any, List, Optional


class DefaultAdapter:
    """Default provider adapter with sensible fallbacks."""
    
    def supports_prompt_caching(self) -> bool:
        return False
    
    def should_summarize_tools(self, iter_count: int) -> bool:
        return iter_count >= 5  # Conservative default
    
    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return tools  # No special formatting by default
    
    def post_tool_iteration(self, state: Dict[str, Any]) -> None:
        pass  # No post-processing by default
    
    def supports_structured_output(self) -> bool:
        return False  # Conservative default
    
    def supports_streaming(self) -> bool:
        return True  # Most providers support streaming
    
    def supports_streaming_with_tools(self) -> bool:
        return True  # Most providers support streaming with tools
    
    def get_max_iteration_threshold(self) -> int:
        return 10  # Conservative default
    
    def format_tool_result_message(self, function_name: str, tool_result: Any, tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        # Standard OpenAI-style tool result message
        message = {
            "role": "tool",
            "content": str(tool_result),
        }
        if tool_call_id is not None:
            message["tool_call_id"] = tool_call_id
        else:
            # Fallback for backward compatibility
            message["tool_call_id"] = f"call_{function_name}"
        return message
    
    def handle_empty_response_with_tools(self, state: Dict[str, Any]) -> bool:
        return False  # No special handling by default
    
    def get_default_settings(self) -> Dict[str, Any]:
        return {}  # No provider-specific defaults
    
    def parse_tool_calls(self, raw_response: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Default tool call parsing - use OpenAI-style format."""
        if "choices" in raw_response and len(raw_response["choices"]) > 0:
            message = raw_response["choices"][0].get("message", {})
            return message.get("tool_calls")
        return None
    
    def should_skip_streaming_with_tools(self) -> bool:
        return False  # Most providers support streaming with tools
    
    def recover_tool_calls_from_text(self, response_text: str, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        return None  # No text recovery by default
    
    def inject_cache_control(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return messages  # No cache control by default
    
    def extract_reasoning_tokens(self, response: Dict[str, Any]) -> int:
        return 0  # No reasoning tokens by default


class OllamaAdapter(DefaultAdapter):
    """
    Ollama-specific provider adapter.
    
    Handles Ollama's specific quirks:
    - Doesn't support streaming with tools reliably
    - Needs tool summarization after iteration 1
    - Uses natural language tool result format
    - Handles empty responses after tool execution
    """
    
    def should_summarize_tools(self, iter_count: int) -> bool:
        # Replaces: OLLAMA_SUMMARY_ITERATION_THRESHOLD logic
        # Must match LLM.OLLAMA_SUMMARY_ITERATION_THRESHOLD = 1
        return iter_count >= 1
    
    def supports_streaming_with_tools(self) -> bool:
        # Ollama doesn't reliably support streaming with tools
        return False
    
    def get_max_iteration_threshold(self) -> int:
        return 1  # Ollama-specific threshold
    
    def format_tool_result_message(self, function_name: str, tool_result: Any, tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        # Ollama uses natural language format for tool results
        return {
            "role": "user", 
            "content": f"Tool '{function_name}' returned: {tool_result}"
        }
    
    def handle_empty_response_with_tools(self, state: Dict[str, Any]) -> bool:
        # Handle Ollama's tendency to return empty responses after tool execution
        iteration_count = state.get('iteration_count', 0)
        has_tool_results = bool(state.get('accumulated_tool_results'))
        response_text = state.get('response_text', '').strip()
        
        if iteration_count >= 1 and has_tool_results and not response_text:
            return True  # Signal that special handling is needed
        return False
    
    def recover_tool_calls_from_text(self, response_text: str, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Ollama-specific tool call recovery from response text."""
        if not response_text or not tools:
            return None
        
        try:
            import json
            response_json = json.loads(response_text.strip())
            if isinstance(response_json, dict) and "name" in response_json:
                # Convert Ollama format to standard tool_calls format
                return [{
                    "id": f"call_{response_json['name']}_{hash(response_text) % 10000}",
                    "type": "function",
                    "function": {
                        "name": response_json["name"],
                        "arguments": json.dumps(response_json.get("arguments", {}))
                    }
                }]
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        
        return None
    
    def post_tool_iteration(self, state: Dict[str, Any]) -> None:
        # Replaces: Ollama-specific post-tool summary branches
        if (not state.get('response_text', '').strip() and 
            state.get('formatted_tools') and 
            state.get('iteration_count') == 0):
            # Add Ollama-specific summary logic here
            state['needs_summary'] = True
    
    def get_default_settings(self) -> Dict[str, Any]:
        return {
            'max_tool_repairs': 2,
            'force_tool_usage': 'auto'
        }


class AnthropicAdapter(DefaultAdapter):
    """Anthropic/Claude provider adapter."""
    
    def supports_prompt_caching(self) -> bool:
        return True  # Claude supports prompt caching
    
    def supports_structured_output(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        # litellm.acompletion with stream=True returns a ModelResponse (not async generator)
        # for Anthropic in the async path, causing 'async for requires __aiter__' error
        return False

    def supports_streaming_with_tools(self) -> bool:
        return False


class GeminiAdapter(DefaultAdapter):
    """
    Google Gemini provider adapter.
    
    Handles Gemini's specific quirks:
    - Has internal tools that need special formatting
    - Doesn't support streaming with tools reliably
    - Supports structured output
    """
    
    def should_skip_streaming_with_tools(self) -> bool:
        """Gemini should skip streaming when tools are present."""
        return True
    
    def supports_structured_output(self) -> bool:
        return True
    
    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Replaces: gemini_internal_tools handling in llm.py
        # Internal tool names match GEMINI_INTERNAL_TOOLS: {'googleSearch', 'urlContext', 'codeExecution'}
        formatted = []
        for tool in tools:
            if tool.get('name') in GEMINI_INTERNAL_TOOLS:
                # Convert to Gemini internal tool format
                formatted.append({
                    'type': 'function',
                    'function': tool
                })
            else:
                formatted.append(tool)
        return formatted
    
    def supports_streaming_with_tools(self) -> bool:
        # Gemini has issues with streaming + tools
        return False
    
    def supports_structured_output(self) -> bool:
        return True


# Provider adapter registry - public for extension
_provider_adapters: Dict[str, LLMProviderAdapterProtocol] = {}

# Register core adapters at import time
_default_adapter = DefaultAdapter()
_provider_adapters['default'] = _default_adapter
_provider_adapters['ollama'] = OllamaAdapter()
_provider_adapters['anthropic'] = AnthropicAdapter()
_provider_adapters['claude'] = AnthropicAdapter()  # Alias
_provider_adapters['gemini'] = GeminiAdapter()


def add_provider_adapter(name: str, adapter: LLMProviderAdapterProtocol) -> None:
    """
    Register a provider adapter by name.
    
    This enables new providers to be added without modifying core code.
    
    Args:
        name: Provider name (e.g., "cohere", "huggingface")
        adapter: Provider adapter implementing LLMProviderProtocol
    """
    _provider_adapters[name] = adapter


def get_provider_adapter(name: str) -> LLMProviderAdapterProtocol:
    """
    Get provider adapter by name with fallback to default.
    
    Args:
        name: Provider name (e.g., "anthropic", "ollama", "gemini")
        
    Returns:
        Provider adapter instance (default if name not found)
    """
    name_lower = name.lower()
    
    # Exact match first
    if name_lower in _provider_adapters:
        return _provider_adapters[name_lower]
        
    # Provider prefixes or substrings
    if "ollama" in name_lower:
        return _provider_adapters["ollama"]
    if "claude" in name_lower or "anthropic" in name_lower:
        return _provider_adapters["anthropic"]
    if "gemini" in name_lower:
        return _provider_adapters["gemini"]
        
    return _provider_adapters["default"]


def list_provider_adapters() -> List[str]:
    """List all registered provider adapter names."""
    return sorted(_provider_adapters.keys())


def has_provider_adapter(name: str) -> bool:
    """Check if a provider adapter is registered."""
    return name in _provider_adapters


__all__ = [
    'DefaultAdapter',
    'OllamaAdapter', 
    'AnthropicAdapter',
    'GeminiAdapter',
    'get_provider_adapter',
    'add_provider_adapter',
    'list_provider_adapters',
    'has_provider_adapter',
]