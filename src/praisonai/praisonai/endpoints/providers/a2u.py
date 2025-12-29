"""
A2U Provider

Provider adapter for Agent-to-User event stream endpoints.
"""

from typing import Any, Dict, Iterator, List, Optional

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class A2UProvider(BaseProvider):
    """
    Provider adapter for A2U (Agent-to-User) event stream endpoints.
    
    A2U provides a protocol surface for streaming agent events to users,
    typically via SSE or WebSocket. This enables real-time UI updates.
    """
    
    provider_type = "a2u"
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="A2U Event Stream",
            description="Agent-to-User event streaming protocol",
            capabilities=["event-stream", "subscribe", "unsubscribe"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available A2U event streams."""
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
                        streaming=ep.get("streaming", ["sse"]),
                        auth_modes=ep.get("auth_modes", ["none"]),
                    ))
            return endpoints
        
        # Fallback: check for events endpoint
        result = self._make_request("GET", "/a2u/info")
        
        if result.get("error"):
            # Return default event stream endpoint
            return [EndpointInfo(
                name="events",
                description="Agent event stream",
                provider_type=self.provider_type,
                streaming=["sse"],
                auth_modes=["none"],
            )]
        
        data = result.get("data", {})
        streams = data.get("streams", [{"name": "events", "description": "Agent event stream"}])
        
        endpoints = []
        for stream in streams:
            endpoints.append(EndpointInfo(
                name=stream.get("name", "events"),
                description=stream.get("description", "Event stream"),
                provider_type=self.provider_type,
                streaming=["sse", "websocket"],
                auth_modes=["none"],
            ))
        
        return endpoints
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about an A2U event stream."""
        endpoints = self.list_endpoints()
        for ep in endpoints:
            if ep.name == name:
                return ep
        
        # Return default info
        return EndpointInfo(
            name=name,
            description=f"Event stream: {name}",
            provider_type=self.provider_type,
            streaming=["sse"],
            auth_modes=["none"],
            metadata={
                "event_types": [
                    "agent.started",
                    "agent.thinking",
                    "agent.tool_call",
                    "agent.response",
                    "agent.completed",
                    "agent.error",
                ],
            },
        )
    
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """Subscribe to an A2U event stream (returns subscription info)."""
        body = {
            "stream": name,
            "filters": input_data.get("filters", []) if input_data else [],
        }
        
        result = self._make_request("POST", "/a2u/subscribe", json_data=body)
        
        if result.get("error"):
            return InvokeResult(
                ok=False,
                status="error",
                error=result["error"].get("message", str(result["error"])),
            )
        
        data = result.get("data", {})
        return InvokeResult(
            ok=True,
            status="subscribed",
            data={
                "subscription_id": data.get("subscription_id"),
                "stream_url": data.get("stream_url", f"{self.base_url}/a2u/events/{name}"),
            },
        )
    
    def invoke_stream(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Stream events from an A2U endpoint."""
        import json
        import urllib.request
        
        stream_path = f"/a2u/events/{name}"
        full_url = f"{self.base_url}{stream_path}"
        
        headers = {"Accept": "text/event-stream"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        try:
            req = urllib.request.Request(full_url, headers=headers, method="GET")
            
            with urllib.request.urlopen(req, timeout=300) as response:
                buffer = ""
                for line in response:
                    line = line.decode("utf-8")
                    buffer += line
                    
                    if buffer.endswith("\n\n"):
                        event_type = "event"
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
        """Check A2U server health."""
        result = self._make_request("GET", "/health")
        
        if result.get("error"):
            # Try a2u-specific health
            result = self._make_request("GET", "/a2u/health")
        
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
            server_name=data.get("server_name", "A2U Server"),
            server_version=data.get("version"),
            provider_type=self.provider_type,
        )
