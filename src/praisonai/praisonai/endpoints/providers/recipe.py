"""
Recipe Provider

Provider adapter for recipe runner endpoints.
"""

from typing import Any, Dict, Iterator, List, Optional

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class RecipeProvider(BaseProvider):
    """
    Provider adapter for recipe runner endpoints.
    
    Connects to recipe runner server (Starlette-based) and provides
    unified discovery and invocation interface.
    """
    
    provider_type = "recipe"
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="Recipe Runner",
            description="Recipe execution endpoints",
            capabilities=["list", "describe", "invoke", "stream", "validate"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available recipe endpoints."""
        path = "/v1/recipes"
        if tags:
            path += f"?tags={','.join(tags)}"
        
        result = self._make_request("GET", path)
        
        if result.get("error"):
            return []
        
        recipes = result.get("data", {}).get("recipes", [])
        endpoints = []
        
        for r in recipes:
            endpoints.append(EndpointInfo(
                name=r.get("name", ""),
                description=r.get("description", ""),
                provider_type=self.provider_type,
                tags=r.get("tags", []),
                version=r.get("version", "1.0.0"),
                streaming=["none", "sse"],
                auth_modes=["none", "api-key"],
            ))
        
        return endpoints
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about a recipe endpoint."""
        result = self._make_request("GET", f"/v1/recipes/{name}")
        
        if result.get("status") == 404 or result.get("error"):
            return None
        
        data = result.get("data", {})
        
        # Get schema
        schema_result = self._make_request("GET", f"/v1/recipes/{name}/schema")
        schema_data = schema_result.get("data", {}) if not schema_result.get("error") else {}
        
        return EndpointInfo(
            name=data.get("name", name),
            description=data.get("description", ""),
            provider_type=self.provider_type,
            tags=data.get("tags", []),
            version=data.get("version", "1.0.0"),
            input_schema=schema_data.get("input_schema"),
            output_schema=schema_data.get("output_schema"),
            streaming=["none", "sse"],
            auth_modes=["none", "api-key"],
            metadata=data.get("metadata", {}),
        )
    
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """Invoke a recipe endpoint."""
        body = {
            "recipe": name,
            "input": input_data or {},
            "config": config or {},
        }
        
        result = self._make_request("POST", "/v1/recipes/run", json_data=body)
        
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
                error=f"Recipe not found: {name}",
            )
        
        if result.get("error"):
            return InvokeResult(
                ok=False,
                status="error",
                error=result["error"].get("message", str(result["error"])),
            )
        
        data = result.get("data", {})
        return InvokeResult(
            ok=data.get("ok", True),
            status=data.get("status", "success"),
            data=data.get("output"),
            metadata={"run_id": data.get("run_id")},
        )
    
    def invoke_stream(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Invoke a recipe endpoint with streaming."""
        import json
        import urllib.request
        
        body = {
            "recipe": name,
            "input": input_data or {},
            "config": config or {},
        }
        
        full_url = f"{self.base_url}/v1/recipes/stream"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        data = json.dumps(body).encode("utf-8")
        
        try:
            req = urllib.request.Request(full_url, data=data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=300) as response:
                buffer = ""
                for line in response:
                    line = line.decode("utf-8")
                    buffer += line
                    
                    if buffer.endswith("\n\n"):
                        event_type = "message"
                        event_data = ""
                        
                        for part in buffer.strip().split("\n"):
                            if part.startswith("event:"):
                                event_type = part[6:].strip()
                            elif part.startswith("data:"):
                                event_data = part[5:].strip()
                        
                        if event_data:
                            try:
                                yield {"event": event_type, "data": json.loads(event_data)}
                            except json.JSONDecodeError:
                                yield {"event": event_type, "data": event_data}
                        
                        buffer = ""
                        
        except Exception as e:
            yield {"event": "error", "data": {"error": str(e)}}
    
    def health(self) -> HealthResult:
        """Check recipe server health."""
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
            healthy=data.get("status") == "healthy",
            status=data.get("status", "unknown"),
            server_name=data.get("service"),
            server_version=data.get("version"),
            provider_type=self.provider_type,
        )
