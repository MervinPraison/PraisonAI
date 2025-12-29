"""
MCP Provider

Provider adapter for MCP server endpoints (stdio, http, sse).
"""

from typing import Any, Dict, Iterator, List, Optional

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class MCPProvider(BaseProvider):
    """
    Provider adapter for MCP server endpoints.
    
    Supports multiple MCP transport types:
    - stdio: Standard input/output (requires subprocess)
    - http: HTTP-based MCP server
    - sse: Server-Sent Events MCP gateway
    """
    
    provider_type = "mcp"
    
    def __init__(
        self,
        base_url: str = "http://localhost:8765",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        transport: str = "http",
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize MCP provider.
        
        Args:
            base_url: Base URL for HTTP/SSE transport
            api_key: Optional API key
            timeout: Request timeout
            transport: Transport type (stdio, http, sse)
            command: Command for stdio transport
            args: Command arguments for stdio transport
            env: Environment variables for stdio transport
        """
        super().__init__(base_url, api_key, timeout)
        self.transport = transport
        self.command = command
        self.args = args or []
        self.env = env or {}
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="MCP Server",
            description=f"MCP server ({self.transport} transport)",
            capabilities=["list-tools", "call-tool", "list-resources"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available MCP tools as endpoints."""
        if self.transport == "stdio":
            return self._list_stdio_tools(tags)
        else:
            return self._list_http_tools(tags)
    
    def _list_stdio_tools(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List tools from stdio MCP server."""
        try:
            from praisonaiagents.mcp import MCP
            
            mcp = MCP(command=self.command, args=self.args, env=self.env)
            tools = mcp.get_tools()
            
            endpoints = []
            for tool in tools:
                tool_name = getattr(tool, 'name', str(tool))
                tool_desc = getattr(tool, 'description', '')
                
                endpoints.append(EndpointInfo(
                    name=tool_name,
                    description=tool_desc,
                    provider_type=self.provider_type,
                    streaming=["mcp-stream"],
                    auth_modes=["none"],
                    metadata={"transport": "stdio"},
                ))
            
            return endpoints
        except Exception:
            return []
    
    def _list_http_tools(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List tools from HTTP MCP server."""
        # Try unified discovery first
        result = self._make_request("GET", "/__praisonai__/discovery")
        
        if not result.get("error") and result.get("data"):
            data = result.get("data", {})
            endpoints = []
            for ep in data.get("endpoints", []):
                if ep.get("provider_type") == self.provider_type:
                    endpoints.append(EndpointInfo(
                        name=ep.get("name", ""),
                        description=ep.get("description", ""),
                        provider_type=self.provider_type,
                        tags=ep.get("tags", []),
                        streaming=ep.get("streaming", ["mcp-stream"]),
                        auth_modes=ep.get("auth_modes", ["none"]),
                    ))
            return endpoints
        
        # Fallback: try MCP tools endpoint
        result = self._make_request("GET", "/mcp/tools")
        
        if result.get("error"):
            return []
        
        tools = result.get("data", {}).get("tools", [])
        endpoints = []
        
        for tool in tools:
            endpoints.append(EndpointInfo(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                provider_type=self.provider_type,
                input_schema=tool.get("inputSchema"),
                streaming=["mcp-stream"],
                auth_modes=["none"],
            ))
        
        return endpoints
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about an MCP tool."""
        endpoints = self.list_endpoints()
        for ep in endpoints:
            if ep.name == name:
                return ep
        return None
    
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """Invoke an MCP tool."""
        if self.transport == "stdio":
            return self._invoke_stdio(name, input_data)
        else:
            return self._invoke_http(name, input_data)
    
    def _invoke_stdio(self, name: str, input_data: Optional[Dict[str, Any]] = None) -> InvokeResult:
        """Invoke tool via stdio MCP."""
        try:
            from praisonaiagents.mcp import MCP
            
            mcp = MCP(command=self.command, args=self.args, env=self.env)
            tools = mcp.get_tools()
            
            for tool in tools:
                tool_name = getattr(tool, 'name', str(tool))
                if tool_name == name:
                    if callable(tool):
                        result = tool(**(input_data or {}))
                        return InvokeResult(
                            ok=True,
                            status="success",
                            data=result,
                        )
            
            return InvokeResult(
                ok=False,
                status="not_found",
                error=f"Tool not found: {name}",
            )
        except Exception as e:
            return InvokeResult(
                ok=False,
                status="error",
                error=str(e),
            )
    
    def _invoke_http(self, name: str, input_data: Optional[Dict[str, Any]] = None) -> InvokeResult:
        """Invoke tool via HTTP MCP."""
        body = {
            "tool": name,
            "arguments": input_data or {},
        }
        
        result = self._make_request("POST", "/mcp/tools/call", json_data=body)
        
        if result.get("error"):
            return InvokeResult(
                ok=False,
                status="error",
                error=result["error"].get("message", str(result["error"])),
            )
        
        data = result.get("data", {})
        return InvokeResult(
            ok=True,
            status="success",
            data=data.get("result", data),
        )
    
    def invoke_stream(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Invoke MCP tool with streaming."""
        # MCP streaming is tool-specific; for now, wrap sync call
        result = self.invoke(name, input_data, config)
        if result.ok:
            yield {"event": "result", "data": result.data}
        else:
            yield {"event": "error", "data": {"error": result.error}}
    
    def health(self) -> HealthResult:
        """Check MCP server health."""
        if self.transport == "stdio":
            # For stdio, check if command exists
            import shutil
            if self.command and shutil.which(self.command):
                return HealthResult(
                    healthy=True,
                    status="available",
                    server_name=self.command,
                    provider_type=self.provider_type,
                    metadata={"transport": "stdio"},
                )
            return HealthResult(
                healthy=False,
                status="unavailable",
                provider_type=self.provider_type,
                metadata={"error": f"Command not found: {self.command}"},
            )
        
        # HTTP health check
        result = self._make_request("GET", "/health")
        
        if result.get("error"):
            return HealthResult(
                healthy=False,
                status="unhealthy",
                provider_type=self.provider_type,
                metadata={"error": result["error"].get("message", str(result["error"]))},
            )
        
        data = result.get("data", {})
        return HealthResult(
            healthy=True,
            status="healthy",
            server_name=data.get("server_name", "MCP Server"),
            server_version=data.get("version"),
            provider_type=self.provider_type,
        )
