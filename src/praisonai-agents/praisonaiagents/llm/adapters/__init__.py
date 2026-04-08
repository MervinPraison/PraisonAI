"""
LLM Provider Adapters

Concrete implementations of LLMProviderAdapter protocol that replace
scattered provider dispatch logic throughout the core.

This demonstrates the protocol-driven approach for Gap 2.
"""

from ..protocols import LLMProviderAdapter
from ..model_capabilities import GEMINI_INTERNAL_TOOLS
from typing import Dict, Any, List


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


class OllamaAdapter(DefaultAdapter):
    """
    Ollama-specific provider adapter.
    
    Demonstrates how to extract Ollama-specific logic from llm.py
    scattered provider dispatch into a clean adapter.
    """
    
    def should_summarize_tools(self, iter_count: int) -> bool:
        # Replaces: OLLAMA_SUMMARY_ITERATION_THRESHOLD logic
        # Must match LLM.OLLAMA_SUMMARY_ITERATION_THRESHOLD = 1
        return iter_count >= 1
    
    def post_tool_iteration(self, state: Dict[str, Any]) -> None:
        # Replaces: Ollama-specific post-tool summary branches
        if (not state.get('response_text', '').strip() and 
            state.get('formatted_tools') and 
            state.get('iteration_count') == 0):
            # Add Ollama-specific summary logic here
            state['needs_summary'] = True


class AnthropicAdapter(DefaultAdapter):
    """Anthropic/Claude provider adapter."""
    
    def supports_prompt_caching(self) -> bool:
        return True  # Claude supports prompt caching
    
    def supports_structured_output(self) -> bool:
        return True


class GeminiAdapter(DefaultAdapter):
    """Google Gemini provider adapter."""
    
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
    
    def supports_structured_output(self) -> bool:
        return True


# Provider adapter registry
_provider_adapters = {
    'default': DefaultAdapter(),
    'ollama': OllamaAdapter(),
    'anthropic': AnthropicAdapter(),
    'claude': AnthropicAdapter(),
    'gemini': GeminiAdapter(),
}


def get_provider_adapter(model: str) -> LLMProviderAdapter:
    """
    Get provider adapter for a model string.
    
    This replaces scattered model.startswith() checks in llm.py.
    
    Args:
        model: Model identifier (e.g., "claude-3.5", "ollama/llama3", "gemini-pro")
        
    Returns:
        Provider adapter instance
    """
    model_lower = model.lower()
    
    if model_lower.startswith('claude-') or 'anthropic' in model_lower:
        return _provider_adapters['anthropic']
    elif model_lower.startswith('ollama/') or 'ollama' in model_lower:
        return _provider_adapters['ollama']
    elif model_lower.startswith('gemini-') or model_lower.startswith('gemini/'):
        return _provider_adapters['gemini']
    else:
        return _provider_adapters['default']


__all__ = [
    'DefaultAdapter',
    'OllamaAdapter', 
    'AnthropicAdapter',
    'GeminiAdapter',
    'get_provider_adapter',
]