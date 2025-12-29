"""
Base Provider Interface

Abstract base class for all provider adapters.
Each provider implements discovery, invocation, and health check methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from ..discovery import EndpointInfo, ProviderInfo


@dataclass
class InvokeResult:
    """Result from invoking an endpoint."""
    ok: bool
    status: str = "success"
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ok": self.ok,
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class HealthResult:
    """Result from health check."""
    healthy: bool
    status: str = "healthy"
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    provider_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "status": self.status,
            "server_name": self.server_name,
            "server_version": self.server_version,
            "provider_type": self.provider_type,
            "metadata": self.metadata,
        }


class BaseProvider(ABC):
    """
    Abstract base class for provider adapters.
    
    Each provider type (recipe, agents-api, mcp, etc.) implements this interface
    to provide consistent discovery and invocation behavior.
    """
    
    # Provider type identifier
    provider_type: str = "base"
    
    def __init__(
        self,
        base_url: str = "http://localhost:8765",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the provider.
        
        Args:
            base_url: Base URL of the server
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
    
    @abstractmethod
    def get_provider_info(self) -> ProviderInfo:
        """
        Get provider information.
        
        Returns:
            ProviderInfo with provider details
        """
        pass
    
    @abstractmethod
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """
        List available endpoints.
        
        Args:
            tags: Optional list of tags to filter by
            
        Returns:
            List of EndpointInfo objects
        """
        pass
    
    @abstractmethod
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """
        Get detailed information about an endpoint.
        
        Args:
            name: Endpoint name
            
        Returns:
            EndpointInfo or None if not found
        """
        pass
    
    @abstractmethod
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """
        Invoke an endpoint.
        
        Args:
            name: Endpoint name
            input_data: Input data for the endpoint
            config: Optional configuration overrides
            stream: Whether to stream the response
            
        Returns:
            InvokeResult with response data
        """
        pass
    
    def invoke_stream(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Invoke an endpoint with streaming.
        
        Args:
            name: Endpoint name
            input_data: Input data for the endpoint
            config: Optional configuration overrides
            
        Yields:
            Stream events as dictionaries
        """
        # Default implementation - subclasses can override
        result = self.invoke(name, input_data, config, stream=True)
        if result.ok:
            yield {"event": "complete", "data": result.data}
        else:
            yield {"event": "error", "data": {"error": result.error}}
    
    @abstractmethod
    def health(self) -> HealthResult:
        """
        Check server health.
        
        Returns:
            HealthResult with health status
        """
        pass
    
    def _make_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to server.
        
        Args:
            method: HTTP method
            path: URL path
            json_data: Optional JSON body
            
        Returns:
            Response data dictionary
        """
        import json
        import urllib.request
        import urllib.error
        
        full_url = f"{self.base_url}{path}"
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        data = None
        if json_data:
            data = json.dumps(json_data).encode("utf-8")
        
        try:
            req = urllib.request.Request(
                full_url,
                data=data,
                headers=headers,
                method=method,
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return {"status": response.status, "data": json.loads(body) if body else {}}
                
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            try:
                error_data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                error_data = {"message": body}
            return {"status": e.code, "error": error_data}
        except urllib.error.URLError as e:
            return {"status": 0, "error": {"message": f"Connection error: {e.reason}"}}
        except Exception as e:
            return {"status": 0, "error": {"message": str(e)}}
