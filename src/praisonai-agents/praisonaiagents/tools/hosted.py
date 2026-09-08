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

from typing import Any, Dict, List, Optional

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


def is_hosted_tool(tool: Any) -> bool:
    """True for a provider-hosted tool spec."""
    return isinstance(tool, dict) and tool.get("type") in HOSTED_TOOL_TYPES


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


def HostedMCPTool(
    *,
    server_url: str,
    server_label: str = "mcp_server",
    require_approval: str = "never",
) -> Dict[str, Any]:
    """An MCP server the PROVIDER connects to, not this process.

    Distinct from ``praisonaiagents.mcp``, which runs the client here.
    """
    if not server_url:
        raise ValueError("HostedMCPTool needs a server_url: the provider connects to it, not this process.")
    return {
        "type": "mcp",
        "server_label": server_label,
        "server_url": server_url,
        "require_approval": require_approval,
    }
