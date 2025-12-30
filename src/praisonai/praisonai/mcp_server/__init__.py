"""
PraisonAI MCP Server Module

Exposes PraisonAI capabilities as an MCP server that any MCP client can connect to.

MCP Protocol Version: 2025-11-25

Supports:
- STDIO transport (default, for Claude Desktop, Cursor, etc.)
- HTTP Stream transport (MCP 2025-11-25 spec)
- Recipe-to-MCP server bridge
- Tasks API (experimental)
- Elicitation (form and URL modes)
- OAuth 2.1 / OpenID Connect authentication
- Icons and rich metadata

Usage:
    # STDIO mode (for Claude Desktop config)
    praisonai mcp serve --transport stdio
    
    # HTTP Stream mode
    praisonai mcp serve --transport http-stream --port 8080
    
    # Serve a recipe as MCP server
    praisonai mcp serve-recipe support-reply --transport stdio
    
    # Programmatic usage
    from praisonai.mcp_server import MCPServer, RecipeMCPAdapter
    
    server = MCPServer()
    server.run(transport="stdio")
    
    # Recipe as MCP server
    adapter = RecipeMCPAdapter("support-reply")
    adapter.load()
    server = adapter.to_mcp_server()
    server.run(transport="stdio")
"""

__all__ = [
    # Core server
    "MCPServer",
    "MCPToolRegistry",
    "MCPResourceRegistry",
    "MCPPromptRegistry",
    "register_tool",
    "register_resource",
    "register_prompt",
    # Recipe adapter
    "RecipeMCPAdapter",
    "RecipeMCPConfig",
    "create_recipe_mcp_server",
    # Tasks API
    "TaskManager",
    "TaskStore",
    "Task",
    "TaskState",
    # Elicitation
    "ElicitationHandler",
    "ElicitationRequest",
    "ElicitationResult",
    # Sampling
    "SamplingHandler",
    "SamplingRequest",
    "SamplingResponse",
    # Icons
    "IconMetadata",
    "RichMetadata",
]


def __getattr__(name):
    """Lazy load server components."""
    # Core server
    if name == "MCPServer":
        from .server import MCPServer
        return MCPServer
    elif name == "MCPToolRegistry":
        from .registry import MCPToolRegistry
        return MCPToolRegistry
    elif name == "MCPResourceRegistry":
        from .registry import MCPResourceRegistry
        return MCPResourceRegistry
    elif name == "MCPPromptRegistry":
        from .registry import MCPPromptRegistry
        return MCPPromptRegistry
    elif name == "register_tool":
        from .registry import register_tool
        return register_tool
    elif name == "register_resource":
        from .registry import register_resource
        return register_resource
    elif name == "register_prompt":
        from .registry import register_prompt
        return register_prompt
    
    # Recipe adapter
    elif name == "RecipeMCPAdapter":
        from .recipe_adapter import RecipeMCPAdapter
        return RecipeMCPAdapter
    elif name == "RecipeMCPConfig":
        from .recipe_adapter import RecipeMCPConfig
        return RecipeMCPConfig
    elif name == "create_recipe_mcp_server":
        from .recipe_adapter import create_recipe_mcp_server
        return create_recipe_mcp_server
    
    # Tasks API
    elif name == "TaskManager":
        from .tasks import TaskManager
        return TaskManager
    elif name == "TaskStore":
        from .tasks import TaskStore
        return TaskStore
    elif name == "Task":
        from .tasks import Task
        return Task
    elif name == "TaskState":
        from .tasks import TaskState
        return TaskState
    
    # Elicitation
    elif name == "ElicitationHandler":
        from .elicitation import ElicitationHandler
        return ElicitationHandler
    elif name == "ElicitationRequest":
        from .elicitation import ElicitationRequest
        return ElicitationRequest
    elif name == "ElicitationResult":
        from .elicitation import ElicitationResult
        return ElicitationResult
    
    # Sampling
    elif name == "SamplingHandler":
        from .sampling import SamplingHandler
        return SamplingHandler
    elif name == "SamplingRequest":
        from .sampling import SamplingRequest
        return SamplingRequest
    elif name == "SamplingResponse":
        from .sampling import SamplingResponse
        return SamplingResponse
    
    # Icons
    elif name == "IconMetadata":
        from .icons import IconMetadata
        return IconMetadata
    elif name == "RichMetadata":
        from .icons import RichMetadata
        return RichMetadata
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
