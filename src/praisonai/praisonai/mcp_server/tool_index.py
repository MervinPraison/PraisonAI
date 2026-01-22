"""
MCP Tool Index for Dynamic Context Discovery.

Provides file-backed indexing of MCP tool schemas for efficient loading.
Only tool names and hints are loaded statically; full schemas are loaded on demand.

Usage:
    from praisonai.mcp_server.tool_index import MCPToolIndex
    
    index = MCPToolIndex()
    
    # Sync tools from a server
    index.sync("brave-search")
    
    # Get minimal static context (names + hints)
    static_context = index.get_static_context()
    
    # Load full schema on demand
    schema = index.describe("brave-search", "web_search")
"""

import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from praisonaiagents.storage.protocols import StorageBackendProtocol

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """Minimal tool information for static context."""
    name: str
    hint: str  # One-line description
    server: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "hint": self.hint,
            "server": self.server,
        }


@dataclass
class ServerStatus:
    """Status information for an MCP server."""
    server: str
    available: bool = True
    auth_required: bool = False
    last_sync: float = 0
    tool_count: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "server": self.server,
            "available": self.available,
            "auth_required": self.auth_required,
            "last_sync": self.last_sync,
            "tool_count": self.tool_count,
            "error": self.error,
        }


class MCPToolIndex:
    """
    File-backed index of MCP tool schemas.
    
    Directory layout:
    ~/.praison/mcp/
    ├── servers/
    │   ├── brave-search/
    │   │   ├── _index.json      # Tool names + hints
    │   │   ├── _status.json     # Server status
    │   │   ├── web_search.json  # Full schema
    │   │   └── local_search.json
    │   └── github/
    │       └── ...
    └── config.json              # Server configurations
    
    Features:
    - Minimal static context (names + hints only)
    - Full schemas loaded on demand
    - Server status tracking
    - Offline-first with sync
    """
    
    def __init__(
        self,
        base_dir: str = "~/.praison/mcp",
        backend: Optional["StorageBackendProtocol"] = None,
    ):
        """
        Initialize the tool index.
        
        Args:
            base_dir: Base directory for MCP tool index (file-based storage)
            backend: Optional storage backend (file, sqlite, redis).
                     If provided, base_dir is ignored and backend is used.
        
        Example with SQLite backend:
            ```python
            from praisonaiagents.storage import SQLiteBackend
            backend = SQLiteBackend("~/.praison/mcp.db")
            index = MCPToolIndex(backend=backend)
            ```
        """
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.servers_dir = self.base_dir / "servers"
        self._backend = backend
        
        if backend is None:
            self._ensure_dirs()
    
    def _ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.servers_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_server_dir(self, server: str) -> Path:
        """Get directory for a server's tools."""
        server_dir = self.servers_dir / server
        server_dir.mkdir(parents=True, exist_ok=True)
        return server_dir
    
    def sync(self, server: str, tools: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        Sync tool schemas from an MCP server.
        
        Args:
            server: Server name
            tools: List of tool schemas (if None, tries to fetch from server)
            
        Returns:
            Number of tools synced
        """
        server_dir = self._get_server_dir(server)
        
        if tools is None:
            # Try to get tools from MCP
            tools = self._fetch_tools_from_server(server)
        
        if not tools:
            self._update_status(server, available=False, error="No tools found")
            return 0
        
        # Build index
        index_data = []
        for tool in tools:
            tool_name = tool.get("name", "")
            if not tool_name:
                continue
            
            # Extract hint (first line of description)
            description = tool.get("description", "")
            hint = description.split("\n")[0][:100] if description else ""
            
            index_data.append({
                "name": tool_name,
                "hint": hint,
            })
            
            # Save full schema
            schema_path = server_dir / f"{tool_name}.json"
            schema_path.write_text(json.dumps(tool, indent=2))
        
        # Save index
        if self._backend is not None:
            self._backend.save(f"mcp:{server}:index", index_data)
        else:
            index_path = server_dir / "_index.json"
            index_path.write_text(json.dumps(index_data, indent=2))
        
        # Update status
        self._update_status(
            server,
            available=True,
            tool_count=len(index_data),
            last_sync=time.time(),
        )
        
        logger.info(f"Synced {len(index_data)} tools from {server}")
        return len(index_data)
    
    def _fetch_tools_from_server(self, server: str) -> List[Dict[str, Any]]:
        """
        Fetch tools from an MCP server.
        
        This is a placeholder - actual implementation would use MCP client.
        """
        # Try to use existing MCP infrastructure
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents.mcp") is not None:
                # MCP module available but would need server config to connect
                pass
            return []
        except Exception:
            return []
    
    def _update_status(
        self,
        server: str,
        available: bool = True,
        auth_required: bool = False,
        tool_count: int = 0,
        last_sync: float = 0,
        error: Optional[str] = None,
    ) -> None:
        """Update server status file."""
        status = ServerStatus(
            server=server,
            available=available,
            auth_required=auth_required,
            tool_count=tool_count,
            last_sync=last_sync or time.time(),
            error=error,
        )
        
        if self._backend is not None:
            self._backend.save(f"mcp:{server}:status", status.to_dict())
        else:
            server_dir = self._get_server_dir(server)
            status_path = server_dir / "_status.json"
            status_path.write_text(json.dumps(status.to_dict(), indent=2))
    
    def get_status(self, server: str) -> Optional[ServerStatus]:
        """
        Get status for a server.
        
        Args:
            server: Server name
            
        Returns:
            ServerStatus or None if not found
        """
        if self._backend is not None:
            data = self._backend.load(f"mcp:{server}:status")
            if data:
                try:
                    return ServerStatus(**data)
                except TypeError:
                    return None
            return None
        
        server_dir = self._get_server_dir(server)
        status_path = server_dir / "_status.json"
        
        if not status_path.exists():
            return None
        
        try:
            data = json.loads(status_path.read_text())
            return ServerStatus(**data)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def list_servers(self) -> List[str]:
        """List all indexed servers."""
        if self._backend is not None:
            keys = self._backend.list_keys(prefix="mcp:")
            servers = set()
            for key in keys:
                # Extract server from "mcp:<server>:index" or "mcp:<server>:status"
                parts = key.split(":")
                if len(parts) >= 2:
                    servers.add(parts[1])
            return sorted(servers)
        
        servers = []
        for path in self.servers_dir.iterdir():
            if path.is_dir():
                servers.append(path.name)
        return sorted(servers)
    
    def list_tools(self, server: str) -> List[ToolInfo]:
        """
        List tools for a server (from index).
        
        Args:
            server: Server name
            
        Returns:
            List of ToolInfo objects
        """
        server_dir = self._get_server_dir(server)
        index_path = server_dir / "_index.json"
        
        if not index_path.exists():
            return []
        
        try:
            data = json.loads(index_path.read_text())
            return [
                ToolInfo(name=t["name"], hint=t.get("hint", ""), server=server)
                for t in data
            ]
        except (json.JSONDecodeError, KeyError):
            return []
    
    def describe(self, server: str, tool: str) -> Optional[Dict[str, Any]]:
        """
        Get full schema for a tool (loaded on demand).
        
        Args:
            server: Server name
            tool: Tool name
            
        Returns:
            Full tool schema or None if not found
        """
        server_dir = self._get_server_dir(server)
        schema_path = server_dir / f"{tool}.json"
        
        if not schema_path.exists():
            return None
        
        try:
            return json.loads(schema_path.read_text())
        except json.JSONDecodeError:
            return None
    
    def get_static_context(self, servers: Optional[List[str]] = None) -> str:
        """
        Get minimal static context for all indexed tools.
        
        This is the token-efficient representation for system prompts.
        Only includes tool names and one-line hints.
        
        Args:
            servers: List of servers to include (None for all)
            
        Returns:
            Formatted string for system prompt
        """
        target_servers = servers or self.list_servers()
        
        lines = ["Available MCP Tools:"]
        
        for server in target_servers:
            tools = self.list_tools(server)
            if not tools:
                continue
            
            lines.append(f"\n[{server}]")
            for tool in tools:
                lines.append(f"  - {tool.name}: {tool.hint}")
        
        lines.append("\nUse 'describe_tool' to get full schema for any tool.")
        
        return "\n".join(lines)
    
    def get_all_tools(self) -> List[ToolInfo]:
        """Get all tools from all servers."""
        all_tools = []
        for server in self.list_servers():
            all_tools.extend(self.list_tools(server))
        return all_tools
    
    def search_tools(self, query: str) -> List[ToolInfo]:
        """
        Search tools by name or hint.
        
        Args:
            query: Search query
            
        Returns:
            List of matching ToolInfo objects
        """
        import re
        
        pattern = re.compile(query, re.IGNORECASE)
        matches = []
        
        for tool in self.get_all_tools():
            if pattern.search(tool.name) or pattern.search(tool.hint):
                matches.append(tool)
        
        return matches
    
    def clear_server(self, server: str) -> bool:
        """
        Clear all cached data for a server.
        
        Args:
            server: Server name
            
        Returns:
            True if cleared successfully
        """
        import shutil
        
        server_dir = self.servers_dir / server
        if server_dir.exists():
            shutil.rmtree(server_dir)
            return True
        return False


def create_mcp_tools(
    index: Optional[MCPToolIndex] = None,
    base_dir: str = "~/.praison/mcp",
):
    """
    Create tools for agents to interact with MCP tool index.
    
    Returns a list of tool functions that can be passed to Agent(tools=[...]).
    
    Tools created:
    - mcp_list_tools: List available MCP tools
    - mcp_describe_tool: Get full schema for a tool
    - mcp_search_tools: Search tools by name/description
    
    Example:
        tools = create_mcp_tools()
        agent = Agent(name="MyAgent", tools=tools)
    """
    tool_index = index or MCPToolIndex(base_dir=base_dir)
    
    def mcp_list_tools(server: Optional[str] = None) -> str:
        """
        List available MCP tools.
        
        Args:
            server: Server name (None for all servers)
            
        Returns:
            Formatted list of tools
        """
        if server:
            tools = tool_index.list_tools(server)
            if not tools:
                return f"No tools found for server: {server}"
            
            lines = [f"Tools for {server}:"]
            for tool in tools:
                lines.append(f"  - {tool.name}: {tool.hint}")
            return "\n".join(lines)
        else:
            return tool_index.get_static_context()
    
    def mcp_describe_tool(server: str, tool: str) -> str:
        """
        Get full schema for an MCP tool.
        
        Args:
            server: Server name
            tool: Tool name
            
        Returns:
            JSON schema for the tool
        """
        schema = tool_index.describe(server, tool)
        if not schema:
            return f"Tool not found: {server}/{tool}"
        
        return json.dumps(schema, indent=2)
    
    def mcp_search_tools(query: str) -> str:
        """
        Search MCP tools by name or description.
        
        Args:
            query: Search query
            
        Returns:
            Formatted list of matching tools
        """
        matches = tool_index.search_tools(query)
        if not matches:
            return f"No tools found matching: {query}"
        
        lines = [f"Found {len(matches)} tools matching '{query}':"]
        for tool in matches:
            lines.append(f"  - [{tool.server}] {tool.name}: {tool.hint}")
        return "\n".join(lines)
    
    return [mcp_list_tools, mcp_describe_tool, mcp_search_tools]
