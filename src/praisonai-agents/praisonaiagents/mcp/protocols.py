"""
Model Context Protocol (MCP) client protocols for PraisonAI Agents.

Defines protocol interfaces for MCP client extensibility following
the protocol-driven design pattern outlined in AGENTS.md.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class MCPClientProtocol(Protocol):
    """
    Protocol interface for MCP client implementations.
    
    Defines the minimal contract that all MCP clients must follow,
    enabling extensibility through different transport mechanisms
    (stdio, SSE, HTTP stream, WebSocket) while maintaining a
    consistent interface for agents.
    """

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from the MCP server.
        
        Returns:
            List of tool definitions from the server
        """
        ...

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get available tools from the MCP server.
        
        Alias for list_tools() to maintain backward compatibility.
        
        Returns:
            List of tool definitions from the server
        """
        ...

    def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server.
        
        Args:
            name: Tool name to call
            args: Tool arguments
            
        Returns:
            Tool execution result
            
        Raises:
            Exception: If tool call fails
        """
        ...

    def shutdown(self) -> None:
        """
        Shutdown the MCP client and clean up resources.
        
        This should gracefully close connections, terminate
        subprocesses, and release any held resources.
        """
        ...

    async def async_list_tools(self) -> List[Dict[str, Any]]:
        """
        Asynchronously list available tools from the MCP server.
        
        Returns:
            List of tool definitions from the server
        """
        ...

    async def async_get_tools(self) -> List[Dict[str, Any]]:
        """
        Asynchronously get available tools from the MCP server.
        
        Alias for async_list_tools() to maintain backward compatibility.
        
        Returns:
            List of tool definitions from the server
        """
        ...

    async def async_call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """
        Asynchronously call a tool on the MCP server.
        
        Args:
            name: Tool name to call
            args: Tool arguments
            
        Returns:
            Tool execution result
            
        Raises:
            Exception: If tool call fails
        """
        ...

    async def async_shutdown(self) -> None:
        """
        Asynchronously shutdown the MCP client and clean up resources.
        
        This should gracefully close connections, terminate
        subprocesses, and release any held resources.
        """
        ...