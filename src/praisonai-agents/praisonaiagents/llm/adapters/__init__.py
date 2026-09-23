"""
LLM Provider Adapters

Concrete implementations of LLMProviderAdapter protocol that replace
scattered provider dispatch logic throughout the core.

This demonstrates the protocol-driven approach for Gap 3 (streaming)
and integrates with Gap 2 (parallel tool execution).
"""

from ..protocols import LLMProviderAdapterProtocol
import json
import logging
import re
from typing import Dict, Any, List, Optional

_logger = logging.getLogger(__name__)


def resolve_ollama_chained_arguments(
    arguments: Dict[str, Any],
    tool_result_mapping: Dict[str, Any],
    *,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve exact Ollama function-name references without coercing values.

    Weak local models sometimes emit the name of an earlier function as a
    later argument.  Keep the complete result (including mappings, lists,
    negative numbers, and decimals) so the destination tool receives exactly
    what the first tool returned.
    """
    if not tool_result_mapping:
        return arguments
    resolved = dict(arguments)
    for arg_name, arg_value in resolved.items():
        if isinstance(arg_value, str) and arg_value in tool_result_mapping:
            replacement = tool_result_mapping[arg_value]
            resolved[arg_name] = replacement
            extra = {"correlation_id": correlation_id} if correlation_id else {}
            _logger.debug(
                "[OLLAMA_FIX] Replaced %s with a prior result in %s arguments",
                arg_value,
                arg_name,
                extra=extra,
            )
    return resolved


def record_ollama_tool_result(
    tool_result_mapping: Dict[str, Any],
    function_name: str,
    tool_result: Any,
) -> None:
    """Record an Ollama tool result exactly as returned by the callback."""
    if not function_name:
        return
    # Some execution paths return a ToolResult-like object rather than the
    # callback's raw payload.  Never expose its failure diagnostic as a
    # successful same-turn value.
    if getattr(tool_result, "error", None) is not None:
        return
    # The agent executor represents failures as an ``error`` mapping (or a
    # one-item list containing one). Never feed that diagnostic back as a
    # successful value to a dependent call in the same turn.
    if isinstance(tool_result, dict) and tool_result.get("error"):
        return
    if (
        isinstance(tool_result, list)
        and tool_result
        and isinstance(tool_result[0], dict)
        and tool_result[0].get("error")
    ):
        return
    tool_result_mapping[function_name] = tool_result


def collapse_union_param_types(tools):
    """Rewrite tool schemas a local server cannot parse.

    Ollama models `parameters.type` as a Go string, so a union like
    `{"type": ["string", "null"]}` -- which is exactly what an Optional[str]
    tool argument produces -- fails to unmarshal and 400s the WHOLE request,
    not just that tool. Collapsing the nullable to its single concrete member
    keeps the request valid; the field simply stops advertising that it is
    nullable.

    Only the nullable case (exactly one concrete type plus "null") is
    collapsed. A genuine heterogeneous union like ``["string", "integer"]``
    is left untouched: narrowing it to one arm would misrepresent the tool's
    accepted inputs and could push the model toward invalid calls. Such unions
    are rare in generated tool schemas and are the server's problem to reject,
    not ours to silently rewrite.

    Returns a new list; the caller's tool definitions are never mutated.
    """
    def fix(node):
        if isinstance(node, list):
            return [fix(item) for item in node]
        if not isinstance(node, dict):
            return node
        out = {}
        for key, value in node.items():
            if key == "type" and isinstance(value, list):
                concrete = [t for t in value if t != "null"]
                # Collapse only "<type> | null"; preserve real multi-type unions.
                if "null" in value and len(concrete) == 1:
                    out[key] = concrete[0]
                else:
                    out[key] = value
            else:
                out[key] = fix(value)
        return out

    if not tools:
        return tools
    return [fix(tool) for tool in tools]


def _advertised_tool_names(tools: List[Dict[str, Any]]) -> set:
    """The set of tool names the model was actually offered.

    Salvage must never invent a tool: a text-format call is only promoted when
    its name matches something advertised, so a model hallucinating a plausible
    name in prose cannot trigger an unexpected execution.
    """
    names = set()
    for tool in tools or []:
        if isinstance(tool, dict):
            name = tool.get("function", {}).get("name") or tool.get("name")
            if name:
                names.add(name)
    return names


_FENCE_RE = re.compile(
    r"(?P<fence>`{3,}|~{3,})"   # opening fence: >=3 backticks or tildes
    r"[\s\S]*?"                  # body (lazy)
    r"(?:(?P=fence)|\Z)",       # matching closing fence OR end-of-string
    re.MULTILINE,
)


def _mask_protected_ranges(text: str) -> str:
    """Blank out fenced code blocks so a call *shown* as an example is not run.

    Only the span content is replaced (with spaces of equal length) -- offsets
    are preserved, so nothing outside a fence shifts. Legitimate prose that
    merely contains angle brackets is untouched because it is not a tool-call
    dialect; the fence guard specifically protects documentation of a call.

    Both Markdown fence styles are recognised (``` and ~~~), and an *unclosed*
    fence is treated as running to end-of-text: a truncated example that opens
    a fence and names a real tool must not slip through as an executable call.
    """
    def blank(match):
        return " " * len(match.group(0))
    return _FENCE_RE.sub(blank, text)


def _make_tool_call(name: str, arguments: Any, seed: str, idx: int) -> Dict[str, Any]:
    return {
        "id": f"call_{name}_{idx}_{hash(seed) % 10000}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments) if isinstance(arguments, (dict, list)) else str(arguments),
        },
    }


# <tool_call>{"name": ..., "arguments": ...}</tool_call>
_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>", re.IGNORECASE)
# <function=name>{...}</function>
_FUNCTION_TAG_RE = re.compile(r"<function=([a-zA-Z0-9_\-]+)>\s*(\{[\s\S]*?\})\s*</function>", re.IGNORECASE)


def _recover_json_tool_calls(response_text: str, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Salvage a tool call a local model emitted as text instead of natively.

    Shared by every locally-served engine: small models routinely answer with
    the call as content instead of using the tool_calls field. Deliberately NOT
    on DefaultAdapter -- a hosted model returning JSON prose must never have it
    parsed as a tool call.

    Three dialects are recovered, in-process, with no extra LLM round trip:
      1. the whole content is a JSON object/array of ``{"name", "arguments"}``;
      2. one or more ``<tool_call>{...}</tool_call>`` blocks embedded in prose;
      3. one or more ``<function=name>{...}</function>`` blocks embedded in prose.

    Every recovered name is checked against the advertised tool allowlist so a
    call is never invented, and fenced code blocks are masked first so a call
    shown as a documentation example is never executed.
    """
    if not response_text or not tools:
        return None

    allowed = _advertised_tool_names(tools)
    if not allowed:
        return None

    # Fast path: a clean full-content JSON payload (the common case, unchanged).
    try:
        response_json = json.loads(response_text.strip())
        if isinstance(response_json, dict):
            response_json = [response_json]
        if isinstance(response_json, list):
            tool_calls: List[Dict[str, Any]] = []
            for idx, tool_json in enumerate(response_json):
                if isinstance(tool_json, dict) and tool_json.get("name") in allowed:
                    tool_calls.append(_make_tool_call(
                        tool_json["name"], tool_json.get("arguments", {}), response_text, idx))
            if tool_calls:
                return tool_calls
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    # Embedded dialects: only scan when a marker is present, and only outside
    # fenced code so an example call in documentation is never run. The marker
    # probe is case-insensitive to match the tag regexes -- a model that emits
    # <TOOL_CALL> or <FUNCTION=...> must recover just like the lowercase form.
    lowered = response_text.lower()
    if not any(marker in lowered for marker in ("<tool_call>", "<function=")):
        return None

    scan_text = _mask_protected_ranges(response_text)

    # Scan both dialects in a single pass ordered by position in the text, so a
    # model that interleaves <tool_call> and <function=> blocks yields calls in
    # the order it actually wrote them -- a dependent or side-effecting call is
    # never reordered ahead of one it relies on.
    matches = []
    for match in _TOOL_CALL_TAG_RE.finditer(scan_text):
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            name = data.get("name") or data.get("tool")
            if name in allowed:
                args = data.get("arguments", data.get("parameters", {}))
                matches.append((match.start(), name, args))

    for match in _FUNCTION_TAG_RE.finditer(scan_text):
        name = match.group(1)
        if name in allowed:
            try:
                args = json.loads(match.group(2))
            except (json.JSONDecodeError, TypeError):
                continue
            matches.append((match.start(), name, args))

    matches.sort(key=lambda m: m[0])
    salvaged = [
        _make_tool_call(name, args, response_text, idx)
        for idx, (_, name, args) in enumerate(matches)
    ]

    return salvaged if salvaged else None


class DefaultAdapter:
    """Default provider adapter with sensible fallbacks."""
    
    def format_tools(self, tools):
        """Hosted providers get the schema untouched -- they support all of it."""
        return tools

    def resolve_chained_arguments(
        self,
        arguments: Dict[str, Any],
        tool_result_mapping: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provider hook for same-turn tool-result references."""
        return arguments

    def record_tool_result(
        self,
        tool_result_mapping: Dict[str, Any],
        function_name: str,
        tool_result: Any,
    ) -> None:
        """Provider hook for recording results used by later tool calls."""
        return None

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

    def resolve_chained_arguments(
        self,
        arguments: Dict[str, Any],
        tool_result_mapping: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return resolve_ollama_chained_arguments(
            arguments, tool_result_mapping, correlation_id=correlation_id
        )

    def record_tool_result(
        self,
        tool_result_mapping: Dict[str, Any],
        function_name: str,
        tool_result: Any,
    ) -> None:
        record_ollama_tool_result(tool_result_mapping, function_name, tool_result)
    
    
    
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

    def format_tools(self, tools):
        # Ollama 400s the whole request on a union-typed parameter.
        return collapse_union_param_types(tools)

    # Read from the quirk catalogue rather than restating it. Hard-coding this
    # created a second source of truth: correcting the quirk note would have
    # left the behaviour unchanged, which is the drift the catalogue exists to
    # prevent.
    @property
    def format_and_tools_conflict(self) -> bool:
        try:
            from ...local.quirktable import Quirk, quirks_for
            from ...local.capabilities import ApiStyle, LocalEngine
            return Quirk.FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE in quirks_for(
                LocalEngine.OLLAMA, ApiStyle.OPENAI_CHAT)
        except Exception:  # noqa: BLE001 -- the catalogue must never break a request
            return True
    
    
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

    def format_tools(self, tools):
        # llama.cpp and vLLM share Ollama's strict parameter-type handling.
        return collapse_union_param_types(tools)


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
    "collapse_union_param_types",
    'DefaultAdapter',
    'OllamaAdapter', 
    'LocalOpenAIAdapter',
    'AnthropicAdapter',
    'GeminiAdapter',
    'get_provider_adapter',
    'add_provider_adapter',
]
