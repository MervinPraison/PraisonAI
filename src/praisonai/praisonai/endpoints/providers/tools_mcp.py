"""
Tools MCP Provider

Provider adapter for tools exposed as MCP server.
"""

from typing import Any, Dict, Iterator, List, Optional

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class ToolsMCPProvider(BaseProvider):
    """
    Provider adapter for tools exposed as MCP server.
    
    This provider connects to a ToolsMCPServer that exposes Python functions
    as MCP tools.
    """
    
    provider_type = "tools-mcp"
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="Tools MCP Server",
            description="Python tools exposed as MCP server",
            capabilities=["list-tools", "call-tool"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available tools as endpoints."""
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
                        input_schema=ep.get("input_schema"),
                        streaming=ep.get("streaming", ["none"]),
                        auth_modes=ep.get("auth_modes", ["none"]),
                    ))
            return endpoints
        
        # Fallback: try tools endpoint
        result = self._make_request("GET", "/tools")
        
        if result.get("error"):
            return []
        
        tools = result.get("data", {}).get("tools", [])
        endpoints = []
        
        for tool in tools:
            endpoints.append(EndpointInfo(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                provider_type=self.provider_type,
                input_schema=tool.get("input_schema"),
                streaming=["none"],
                auth_modes=["none"],
            ))
        
        return endpoints
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about a tool."""
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
        """Invoke a tool."""
        body = {
            "tool": name,
            "arguments": input_data or {},
        }
        
        result = self._make_request("POST", "/tools/call", json_data=body)
        
        if result.get("status") == 404:
            return InvokeResult(
                ok=False,
                status="not_found",
                error=f"Tool not found: {name}",
            )
        
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
        """Invoke tool with streaming (wraps sync call)."""
        result = self.invoke(name, input_data, config)
        if result.ok:
            yield {"event": "result", "data": result.data}
        else:
            yield {"event": "error", "data": {"error": result.error}}
    
    def health(self) -> HealthResult:
        """Check tools server health."""
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
            server_name=data.get("server_name", "Tools MCP Server"),
            server_version=data.get("version"),
            provider_type=self.provider_type,
        )
