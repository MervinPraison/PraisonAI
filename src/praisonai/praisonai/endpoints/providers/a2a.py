"""
A2A Provider

Provider adapter for Agent-to-Agent protocol endpoints.
"""

from typing import Any, Dict, Iterator, List, Optional

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class A2AProvider(BaseProvider):
    """
    Provider adapter for A2A (Agent-to-Agent) protocol endpoints.
    
    A2A enables agent-to-agent communication following the A2A protocol spec.
    Supports discovery via /.well-known/agent.json and message passing.
    """
    
    provider_type = "a2a"
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="A2A Protocol",
            description="Agent-to-Agent communication protocol",
            capabilities=["agent-card", "message-send", "task-management"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available A2A agents."""
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
        
        # Fallback: try agent card
        result = self._make_request("GET", "/.well-known/agent.json")
        
        if result.get("error"):
            return []
        
        agent_card = result.get("data", {})
        
        return [EndpointInfo(
            name=agent_card.get("name", "a2a-agent"),
            description=agent_card.get("description", "A2A Agent"),
            provider_type=self.provider_type,
            version=agent_card.get("version", "1.0.0"),
            streaming=["sse"] if agent_card.get("capabilities", {}).get("streaming") else ["none"],
            auth_modes=["none"],
            metadata={"agent_card": agent_card},
        )]
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about an A2A agent."""
        # Get agent card
        result = self._make_request("GET", "/.well-known/agent.json")
        
        if result.get("error"):
            return None
        
        agent_card = result.get("data", {})
        
        return EndpointInfo(
            name=agent_card.get("name", name),
            description=agent_card.get("description", ""),
            provider_type=self.provider_type,
            version=agent_card.get("version", "1.0.0"),
            streaming=["sse"] if agent_card.get("capabilities", {}).get("streaming") else ["none"],
            auth_modes=["none"],
            metadata={
                "agent_card": agent_card,
                "skills": agent_card.get("skills", []),
                "capabilities": agent_card.get("capabilities", {}),
            },
        )
    
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """Send a message to an A2A agent."""
        import uuid
        
        # Build A2A message
        message = input_data.get("message", "") if input_data else ""
        if not message and config:
            message = config.get("message", config.get("query", ""))
        
        body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(uuid.uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }
        
        result = self._make_request("POST", "/a2a", json_data=body)
        
        if result.get("error"):
            return InvokeResult(
                ok=False,
                status="error",
                error=result["error"].get("message", str(result["error"])),
            )
        
        data = result.get("data", {})
        
        # Handle JSON-RPC response
        if "result" in data:
            return InvokeResult(
                ok=True,
                status="success",
                data=data["result"],
            )
        elif "error" in data:
            return InvokeResult(
                ok=False,
                status="error",
                error=data["error"].get("message", str(data["error"])),
            )
        
        return InvokeResult(
            ok=True,
            status="success",
            data=data,
        )
    
    def invoke_stream(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Send a streaming message to an A2A agent."""
        import json
        import urllib.request
        import uuid
        
        message = input_data.get("message", "") if input_data else ""
        if not message and config:
            message = config.get("message", config.get("query", ""))
        
        body = {
            "jsonrpc": "2.0",
            "method": "message/stream",
            "id": str(uuid.uuid4()),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                },
            },
        }
        
        full_url = f"{self.base_url}/a2a"
        
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
        """Check A2A server health."""
        # Try status endpoint first
        result = self._make_request("GET", "/status")
        
        if not result.get("error"):
            data = result.get("data", {})
            return HealthResult(
                healthy=data.get("status") == "ok",
                status=data.get("status", "unknown"),
                server_name=data.get("name", "A2A Agent"),
                server_version=data.get("version"),
                provider_type=self.provider_type,
            )
        
        # Fallback: try agent card
        result = self._make_request("GET", "/.well-known/agent.json")
        
        if result.get("error"):
            return HealthResult(
                healthy=False,
                status="unhealthy",
                provider_type=self.provider_type,
                metadata={"error": result["error"].get("message", str(result["error"]))},
            )
        
        agent_card = result.get("data", {})
        return HealthResult(
            healthy=True,
            status="healthy",
            server_name=agent_card.get("name", "A2A Agent"),
            server_version=agent_card.get("version"),
            provider_type=self.provider_type,
        )
