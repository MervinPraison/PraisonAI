"""MCP server hosting for PraisonAI — expose agents and tools to MCP clients.

Example:
    praisonai-mcp serve --transport stdio

    from praisonai_mcp.mcp_server import MCPServer
    server = MCPServer()
    server.run(transport="stdio")
"""

from __future__ import annotations

from praisonai_mcp._version import __version__


def serve_agents(
    agents,
    *,
    host: str = "127.0.0.1",
    port: int = 7777,
    transport: str = "http-stream",
    name: str = "praisonai-agents",
    **kwargs,
):
    """Serve one or more PraisonAI agents to any MCP client.

    Publishes ``ask_{agent_name}`` per agent plus ``list_agents`` over the
    spec-compliant transport, with per-session conversation continuity.

    Example::

        from praisonaiagents import Agent
        from praisonai_mcp import serve_agents

        serve_agents([support, billing], port=7777)

    Args:
        agents: an ``Agent`` or a list of ``Agent`` instances.
        host: bind host (default ``127.0.0.1``).
        port: bind port (default ``7777``).
        transport: ``"http-stream"`` (default) or ``"stdio"``.
    """
    from praisonai_mcp.mcp_server.server import MCPServer
    from praisonai_mcp.mcp_server.agent_adapter import register_agents

    if not isinstance(agents, (list, tuple)):
        agents = [agents]

    server = MCPServer(name=name)
    register_agents(server, list(agents))

    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "http-stream":
        server.run(transport="http-stream", host=host, port=port, **kwargs)
    else:
        raise ValueError(
            f"Unknown transport {transport!r}; expected 'http-stream' or 'stdio'."
        )
    return server


def __getattr__(name: str):
    if name == "MCPServer":
        from praisonai_mcp.mcp_server.server import MCPServer
        return MCPServer
    if name == "handle_mcp_command":
        from praisonai_mcp.mcp_server.cli import handle_mcp_command
        return handle_mcp_command
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["__version__", "MCPServer", "handle_mcp_command", "serve_agents"]
