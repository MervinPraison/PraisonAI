"""
LLM Provider Adapters

Concrete implementations of LLMProviderAdapter protocol that replace
scattered provider dispatch logic throughout the core.

This demonstrates the protocol-driven approach for Gap 3 (streaming)
and integrates with Gap 2 (parallel tool execution).
"""

from ..protocols import LLMProviderAdapterProtocol
import json
from typing import Dict, Any, List, Optional


def _recover_json_tool_calls(response_text: str, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Recover a tool call a local model emitted as JSON text.

    Shared by every locally-served engine: small models routinely answer with
    the call as content instead of using the tool_calls field. Deliberately NOT
    on DefaultAdapter -- a hosted model returning JSON prose must never have it
    parsed as a tool call.
    """
    if not response_text or not tools:
        return None
    
    try:
        import json
        response_json = json.loads(response_text.strip())
        
        # Normalize to list so both single and multi-tool payloads are supported
        if isinstance(response_json, dict):
            response_json = [response_json]

        if isinstance(response_json, list):
            tool_calls: List[Dict[str, Any]] = []
            for idx, tool_json in enumerate(response_json):
                if isinstance(tool_json, dict) and "name" in tool_json:
                    tool_calls.append({
                        "id": f"call_{tool_json['name']}_{idx}_{hash(response_text) % 10000}",
                        "type": "function",
                        "function": {
                            "name": tool_json["name"],
                            "arguments": json.dumps(tool_json.get("arguments", {}))
                        }
                    })
            return tool_calls if tool_calls else None
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    
    return None


class DefaultAdapter:
    """Default provider adapter with sensible fallbacks."""
    
    def supports_prompt_caching(self) -> bool:
        return False
    
    def should_summarize_tools(self, iter_count: int) -> bool:
        return iter_count >= 5  # Conservative default
    
    
    
    
    def supports_streaming(self) -> bool:
        return True  # Most providers support streaming
    
    def supports_streaming_with_tools(self) -> bool:
        return True  # Most providers support streaming with tools
    
    
    
    def format_tool_result_message(self, function_name: str, tool_result: Any, tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        """Standard OpenAI-shaped tool result message.

        This is the union of five inline copies that had drifted apart in llm.py:
        it uses the fuller error sentence, reports a list-of-errors result as an
        error rather than dumping it as data, and guards json.dumps so a tool
        returning a set or a datetime does not crash the turn.
        """
        if tool_result is None:
            content = "Function returned an empty output"
        elif isinstance(tool_result, dict) and 'error' in tool_result:
            content = (f"Error: {tool_result.get('error', 'Unknown error')}. "
                       "Please inform the user that the operation could not be completed.")
        elif (isinstance(tool_result, list) and tool_result
                and isinstance(tool_result[0], dict) and 'error' in tool_result[0]):
            content = (f"Error: {tool_result[0].get('error', 'Unknown error')}. "
                       "Please inform the user that the operation could not be completed.")
        else:
            try:
                content = json.dumps(tool_result)
            except (TypeError, ValueError):
                content = str(tool_result)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id if tool_call_id is not None else f"call_{function_name}",
            "content": content,
        }
    
    def handle_empty_response_with_tools(self, state: Dict[str, Any]) -> bool:
        return False  # No special handling by default
    
    def get_default_settings(self) -> Dict[str, Any]:
        return {}  # No provider-specific defaults
    
    
    
    def recover_tool_calls_from_text(self, response_text: str, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        return None  # No text recovery by default
    
    


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
    
    
    
    def format_tool_result_message(self, function_name: str, tool_result: Any, tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        # Ollama uses natural language format for tool results.
        # Error results get a distinct, apology-oriented instruction so the model
        # explains the failure rather than echoing the raw error.
        is_error = False
        error_message = None
        if isinstance(tool_result, dict) and 'error' in tool_result:
            is_error = True
            error_message = tool_result.get('error', 'Unknown error')
        elif isinstance(tool_result, list) and len(tool_result) > 0:
            first_item = tool_result[0]
            if isinstance(first_item, dict) and 'error' in first_item:
                is_error = True
                error_message = first_item.get('error', 'Unknown error')

        if is_error:
            return {
                "role": "user",
                "content": f"""The tool "{function_name}" encountered an error:
{error_message}

Please provide a helpful response to the user explaining that the operation could not be completed. 
Be apologetic and suggest alternatives if possible. Do NOT repeat the raw error message.
Give a natural, conversational response."""
            }

        return {
            "role": "user",
            "content": f"""Tool execution complete.
Function: {function_name}
Result: {tool_result}

Now provide your final answer using this result. Summarize the information naturally for the user."""
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
        return _recover_json_tool_calls(response_text, tools)
    
    
    def get_default_settings(self) -> Dict[str, Any]:
        return {
            'max_tool_repairs': 2,
            'force_tool_usage': 'auto'
        }


class LocalOpenAIAdapter(DefaultAdapter):
    """Adapter for local servers that speak real OpenAI over HTTP.

    Covers LM Studio, vLLM and llama.cpp's ``llama-server``. These differ from
    Ollama in the way that matters most here: they implement the standard tool
    protocol correctly, so tool results stay ``role: "tool"`` and streaming with
    tools works. Inheriting ``DefaultAdapter``'s message handling is therefore
    deliberate -- applying Ollama's natural-language ``role: "user"`` rewrite
    would corrupt a conversation these servers handle properly.

    What they share with Ollama is the model: locally-served weights are often
    small and emit a malformed tool call now and then. So the one thing this
    adapter adds is a repair budget.

    ``force_tool_usage`` is deliberately NOT set. It injects prompts into every
    conversation, and vLLM commonly serves large, highly capable models where
    that is unwanted noise. ``max_tool_repairs`` costs nothing unless a tool
    call actually arrives malformed.
    """

    def get_default_settings(self) -> Dict[str, Any]:
        return {'max_tool_repairs': 2}

    def recover_tool_calls_from_text(self, response_text: str, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        # Same reason as Ollama: these servers front small local models that
        # answer with the tool call as text, especially after a repair prompt.
        return _recover_json_tool_calls(response_text, tools)


class AnthropicAdapter(DefaultAdapter):
    """Anthropic/Claude provider adapter."""
    
    def supports_prompt_caching(self) -> bool:
        return True  # Claude supports prompt caching
    

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
    
    
    
    
    def supports_streaming_with_tools(self) -> bool:
        # Gemini has issues with streaming + tools
        return False
    


# Provider adapter registry - public for extension
_provider_adapters: Dict[str, LLMProviderAdapterProtocol] = {}

# Register core adapters at import time
_default_adapter = DefaultAdapter()
_provider_adapters['default'] = _default_adapter
_provider_adapters['ollama'] = OllamaAdapter()
_provider_adapters['local'] = LocalOpenAIAdapter()
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
    if name_lower in {"local", "lm_studio", "lmstudio", "vllm", "hosted_vllm", "llamacpp", "llama_cpp"}:
        return _provider_adapters["local"]
    if "claude" in name_lower or "anthropic" in name_lower:
        return _provider_adapters["anthropic"]
    if "gemini" in name_lower:
        return _provider_adapters["gemini"]
        
    return _provider_adapters["default"]


__all__ = [
    'DefaultAdapter',
    'OllamaAdapter', 
    'LocalOpenAIAdapter',
    'AnthropicAdapter',
    'GeminiAdapter',
    'get_provider_adapter',
    'add_provider_adapter',
]
