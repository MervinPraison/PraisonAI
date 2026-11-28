"""
MCP (Model Context Protocol) Capabilities Module

Provides MCP server interaction functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class MCPResult:
    """Result from MCP operations."""
    tools: Optional[List[Dict[str, Any]]] = None
    resources: Optional[List[Dict[str, Any]]] = None
    prompts: Optional[List[Dict[str, Any]]] = None
    server_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPToolCallResult:
    """Result from MCP tool call."""
    result: Any
    tool_name: str
    server_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _build_mcp(
    command: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    **extra: Any,
):
    """Build an MCP client through the shared core config builder."""
    from praisonaiagents.mcp import MCP
    from praisonaiagents.mcp.loader import build_mcp
    from praisonaiagents.mcp.trust import is_mcp_url

    entry: Dict[str, Any] = dict(extra)
    if "url" not in entry:
        if is_mcp_url(command):
            entry["url"] = command
        else:
            entry["command"] = command
            entry["args"] = list(args or [])
            if env:
                entry["env"] = env
    if timeout is not None and "timeout" not in entry:
        entry["timeout"] = timeout
    # Keep expand_env=False (default): direct Python args must not expand ${VAR}.
    return build_mcp(entry, name=str(command or entry.get("url") or "server"), cls=MCP)


def mcp_list_tools(
    command: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> MCPResult:
    """
    List tools from an MCP server.
    
    Args:
        command: MCP server command (e.g., "npx")
        args: Command arguments
        env: Environment variables
        timeout: Request timeout in seconds
        metadata: Optional metadata for tracing
        
    Returns:
        MCPResult with available tools
        
    Example:
        >>> result = mcp_list_tools("npx", ["-y", "@modelcontextprotocol/server-filesystem", "."])
        >>> for tool in result.tools:
        ...     print(tool['name'])
    """
    try:
        mcp = _build_mcp(command=command, args=args, env=env, timeout=timeout, **kwargs)
        tools = mcp.get_tools()
        
        tool_list = []
        for tool in tools:
            tool_list.append({
                'name': getattr(tool, 'name', str(tool)),
                'description': getattr(tool, 'description', ''),
            })
        
        return MCPResult(
            tools=tool_list,
            server_name=command,
            metadata=metadata or {},
        )
    except ImportError:
        return MCPResult(
            tools=[],
            server_name=command,
            metadata={"error": "MCP not available", **(metadata or {})},
        )


async def amcp_list_tools(
    command: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> MCPResult:
    """
    Async: List tools from an MCP server.
    
    See mcp_list_tools() for full documentation.
    """
    return mcp_list_tools(
        command=command,
        args=args,
        env=env,
        timeout=timeout,
        metadata=metadata,
        **kwargs
    )


def mcp_call_tool(
    command: str,
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> MCPToolCallResult:
    """
    Call a tool on an MCP server.
    
    Args:
        command: MCP server command
        tool_name: Name of the tool to call
        tool_args: Arguments for the tool
        args: Command arguments
        env: Environment variables
        timeout: Request timeout in seconds
        metadata: Optional metadata for tracing
        
    Returns:
        MCPToolCallResult with tool result
    """
    try:
        mcp = _build_mcp(command=command, args=args, env=env, timeout=timeout, **kwargs)
        
        # Get the tool and call it
        tools = mcp.get_tools()
        for tool in tools:
            if getattr(tool, 'name', str(tool)) == tool_name:
                if callable(tool):
                    result = tool(**(tool_args or {}))
                else:
                    result = None
                
                return MCPToolCallResult(
                    result=result,
                    tool_name=tool_name,
                    server_name=command,
                    metadata=metadata or {},
                )
        
        return MCPToolCallResult(
            result=None,
            tool_name=tool_name,
            server_name=command,
            metadata={"error": f"Tool '{tool_name}' not found", **(metadata or {})},
        )
    except ImportError:
        return MCPToolCallResult(
            result=None,
            tool_name=tool_name,
            server_name=command,
            metadata={"error": "MCP not available", **(metadata or {})},
        )


async def amcp_call_tool(
    command: str,
    tool_name: str,
    tool_args: Optional[Dict[str, Any]] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> MCPToolCallResult:
    """
    Async: Call a tool on an MCP server.
    
    See mcp_call_tool() for full documentation.
    """
    return mcp_call_tool(
        command=command,
        tool_name=tool_name,
        tool_args=tool_args,
        args=args,
        env=env,
        timeout=timeout,
        metadata=metadata,
        **kwargs
    )
