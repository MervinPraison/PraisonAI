"""
Agents API Provider

Provider adapter for agents-as-API endpoints (single agent or multi-agent router).
"""

from typing import Any, Dict, List, Optional

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class AgentsAPIProvider(BaseProvider):
    """
    Provider adapter for agents-as-API endpoints.
    
    Connects to FastAPI-based agent servers launched via Agent.launch() or Agents.launch()
    and provides unified discovery and invocation interface.
    """
    
    provider_type = "agents-api"
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="Agents API",
            description="Agent HTTP API endpoints",
            capabilities=["list", "describe", "invoke", "health"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available agent endpoints."""
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
                        version=ep.get("version", "1.0.0"),
                        streaming=ep.get("streaming", ["none"]),
                        auth_modes=ep.get("auth_modes", ["none"]),
                    ))
            return endpoints
        
        # Fallback: try root endpoint for endpoint list
        result = self._make_request("GET", "/")
        
        if result.get("error"):
            return []
        
        data = result.get("data", {})
        endpoint_paths = data.get("endpoints", [])
        
        endpoints = []
        for path in endpoint_paths:
            endpoints.append(EndpointInfo(
                name=path.lstrip("/"),
                description=f"Agent endpoint at {path}",
                provider_type=self.provider_type,
                streaming=["none"],
                auth_modes=["none"],
            ))
        
        return endpoints
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about an agent endpoint."""
        # Try unified discovery first
        result = self._make_request("GET", "/__praisonai__/discovery")
        
        if not result.get("error") and result.get("data"):
            data = result.get("data", {})
            for ep in data.get("endpoints", []):
                if ep.get("name") == name:
                    return EndpointInfo(
                        name=ep.get("name", name),
                        description=ep.get("description", ""),
                        provider_type=self.provider_type,
                        tags=ep.get("tags", []),
                        version=ep.get("version", "1.0.0"),
                        input_schema=ep.get("input_schema"),
                        output_schema=ep.get("output_schema"),
                        streaming=ep.get("streaming", ["none"]),
                        auth_modes=ep.get("auth_modes", ["none"]),
                        metadata=ep.get("metadata", {}),
                    )
        
        # Fallback: return basic info
        return EndpointInfo(
            name=name,
            description=f"Agent endpoint: {name}",
            provider_type=self.provider_type,
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            streaming=["none"],
            auth_modes=["none"],
        )
    
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """Invoke an agent endpoint."""
        # Normalize endpoint path
        path = name if name.startswith("/") else f"/{name}"
        
        # Build request body
        body = input_data or {}
        if "query" not in body and config and "query" in config:
            body["query"] = config["query"]
        
        result = self._make_request("POST", path, json_data=body)
        
        if result.get("status") == 401:
            return InvokeResult(
                ok=False,
                status="auth_error",
                error="Authentication required",
            )
        
        if result.get("status") == 404:
            return InvokeResult(
                ok=False,
                status="not_found",
                error=f"Endpoint not found: {name}",
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
            data=data.get("response", data),
        )
    
    def health(self) -> HealthResult:
        """Check agent server health."""
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
            healthy=data.get("status") == "ok",
            status=data.get("status", "unknown"),
            server_name="PraisonAI Agents API",
            provider_type=self.provider_type,
            metadata={"endpoints": data.get("endpoints", [])},
        )
