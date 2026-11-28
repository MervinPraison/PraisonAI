"""Provider-hosted tools, usable on any Agent.

These tools run on the provider's side rather than in this process: OpenAI's
web search and code interpreter, a vector-store file search, a hosted MCP
server. PraisonAI already built every one of these spec dicts -- but only
inside ``agent/deep_research_agent.py``, as constructor flags on that one class.
An ordinary ``Agent`` could not have hosted file search over an existing vector
store without switching agent types.

    from praisonaiagents import Agent
    from praisonaiagents.tools import WebSearchTool, FileSearchTool

    agent = Agent(
        instructions="Research assistant",
        tools=[WebSearchTool(), FileSearchTool(vector_store_ids=["vs_123"])],
    )

Each returns the provider spec as a plain dict, so it can be passed straight
through to the request. ``DeepResearchAgent`` builds its own tools from these,
so there is one definition of each rather than two that can drift.

A hosted tool has no Python callable behind it: the provider executes it. That
is why they are dicts and not FunctionTools, and why the LLM layer forwards
them untouched.
"""

from typing import Any, Dict, List, Optional, Union

__all__ = [
    "HOSTED_TOOL_TYPES",
    "WebSearchTool",
    "CodeInterpreterTool",
    "FileSearchTool",
    "HostedMCPTool",
    "is_hosted_tool",
]

#: Tool ``type`` values the LLM layer forwards to the provider untouched.
#: An allowlist rather than "anything that is not a function", so a genuinely
#: malformed tool is still reported instead of being sent and rejected upstream.
HOSTED_TOOL_TYPES = frozenset({
    "web_search_preview",
    "web_search",
    "code_interpreter",
    "file_search",
    "image_generation",
    "mcp",
    "computer_use_preview",
    "local_shell",
})


#: Per-type required fields. A tool whose type is allowlisted but is missing a
#: required field is malformed and must be dropped, not forwarded upstream where
#: the provider would reject it.
_REQUIRED_FIELDS: Dict[str, tuple] = {
    "mcp": ("server_url",),
}


def is_hosted_tool(tool: Any) -> bool:
    """True for a well-formed provider-hosted tool spec.

    Allowlisted by ``type`` and, where a type has required fields (e.g. ``mcp``
    needs ``server_url``), validated for their presence so a malformed hosted
    dict is still dropped instead of being sent and rejected upstream.
    """
    if not isinstance(tool, dict):
        return False
    tool_type = tool.get("type")
    if tool_type not in HOSTED_TOOL_TYPES:
        return False
    for field in _REQUIRED_FIELDS.get(tool_type, ()):  # type: ignore[union-attr]
        if not tool.get(field):
            return False
    return True


def WebSearchTool(*, search_context_size: Optional[str] = None) -> Dict[str, Any]:
    """Provider-side web search.

    Mirrors what DeepResearchAgent has always sent (``web_search_preview``).
    """
    spec: Dict[str, Any] = {"type": "web_search_preview"}
    if search_context_size:
        spec["search_context_size"] = search_context_size
    return spec


def CodeInterpreterTool(*, file_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Provider-side code execution in a managed container."""
    return {
        "type": "code_interpreter",
        "container": {"type": "auto", "file_ids": list(file_ids or [])},
    }


def FileSearchTool(
    *,
    vector_store_ids: Optional[List[str]] = None,
    max_num_results: Optional[int] = None,
) -> Dict[str, Any]:
    """Provider-side search over an existing vector store."""
    spec: Dict[str, Any] = {"type": "file_search"}
    if vector_store_ids:
        spec["vector_store_ids"] = list(vector_store_ids)
    if max_num_results is not None:
        spec["max_num_results"] = max_num_results
    return spec


_SECRET_KEYS = frozenset({"authorization", "authorization_token"})
ANTHROPIC_MCP_BETA_HEADER = "mcp-client-2025-11-20"


class _HostedToolSpec(dict):
    """Dict for a hosted MCP tool whose secret fields are redacted in repr/str."""

    def __repr__(self) -> str:
        if not any(k in self for k in _SECRET_KEYS):
            return super().__repr__()
        return repr({k: ("***" if k in _SECRET_KEYS else v) for k, v in self.items()})

    __str__ = __repr__

    def copy(self) -> "_HostedToolSpec":
        return _HostedToolSpec(self)

    def to_openai_dict(self) -> Dict[str, Any]:
        return hosted_mcp_to_openai(self)

    def to_anthropic_dict(self) -> Dict[str, Any]:
        return hosted_mcp_to_anthropic(self)


def hosted_mcp_to_openai(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a hosted MCP tool spec to OpenAI Responses ``mcp`` format."""
    out = _HostedToolSpec()
    for k, v in spec.items():
        if v is None or (k == "authorization" and not v):
            continue
        out[k] = list(v) if k == "allowed_tools" else (bool(v) if k == "defer_loading" else v)
    return out


def hosted_mcp_to_anthropic(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a hosted MCP tool spec to Anthropic ``mcp_servers`` + ``mcp_toolset``."""
    name = spec.get("server_label") or "mcp_server"
    server = _HostedToolSpec(type="url", url=spec["server_url"], name=name)
    auth = spec.get("authorization")
    if auth:
        server["authorization_token"] = auth[7:] if isinstance(auth, str) and auth.startswith("Bearer ") else auth

    toolset: Dict[str, Any] = {"type": "mcp_toolset", "mcp_server_name": name}
    default_config: Dict[str, Any] = {}
    if spec.get("allowed_tools") is not None:
        default_config["enabled"] = False
        if spec["allowed_tools"]:
            toolset["configs"] = {t: {"enabled": True} for t in spec["allowed_tools"]}
    if spec.get("defer_loading") is not None:
        default_config["defer_loading"] = bool(spec["defer_loading"])
    if default_config:
        toolset["default_config"] = default_config
    return {"mcp_server": server, "mcp_toolset": toolset}


def HostedMCPTool(
    *,
    server_url: str,
    server_label: str = "mcp_server",
    require_approval: Optional[Union[str, Dict[str, Any]]] = "never",
    authorization: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    defer_loading: Optional[bool] = None,
) -> Dict[str, Any]:
    """An MCP server the PROVIDER connects to, not this process.

    Distinct from ``praisonaiagents.mcp``, which runs the client here.
    """
    if not server_url:
        raise ValueError("HostedMCPTool needs a server_url: the provider connects to it, not this process.")
    return hosted_mcp_to_openai({
        "type": "mcp",
        "server_label": server_label,
        "server_url": server_url,
        "require_approval": require_approval,
        "authorization": authorization,
        "allowed_tools": allowed_tools,
        "defer_loading": defer_loading,
    })
