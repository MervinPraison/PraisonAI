"""
MCP Backward Compatibility Module.

This module provides utilities for maintaining backward compatibility
with older MCP servers and the deprecated HTTP+SSE transport from
protocol version 2024-11-05.

Per MCP specification, clients wanting to support older servers should:
1. Attempt POST to server URL with InitializeRequest
2. If it fails with 400, 404, or 405, fall back to legacy SSE
3. Issue GET to server URL expecting SSE stream with endpoint event
"""

from typing import Optional


def detect_transport_support(
    response_status: int,
    content_type: Optional[str] = None
) -> str:
    """
    Detect which transport a server supports based on response.
    
    Per MCP spec backward compatibility guide:
    - Success (200) with JSON indicates Streamable HTTP
    - 400, 404, 405 indicates need for legacy SSE fallback
    
    Args:
        response_status: HTTP response status code
        content_type: Response Content-Type header
        
    Returns:
        Transport type: "http_stream" or "sse"
    """
    # Check for fallback indicators
    if response_status in (400, 404, 405):
        return "sse"
    
    # Successful response indicates Streamable HTTP support
    if response_status == 200:
        return "http_stream"
    
    # Default to SSE for unknown cases
    return "sse"


def is_legacy_sse_url(url: str) -> bool:
    """
    Check if URL indicates legacy SSE transport.
    
    Legacy SSE URLs typically end with /sse.
    
    Args:
        url: Server URL
        
    Returns:
        True if URL indicates legacy SSE
    """
    return url.rstrip('/').endswith('/sse')


def get_legacy_sse_endpoint(base_url: str) -> str:
    """
    Get the legacy SSE endpoint URL.
    
    Args:
        base_url: Base server URL
        
    Returns:
        SSE endpoint URL
    """
    base = base_url.rstrip('/')
    if not base.endswith('/sse'):
        return f"{base}/sse"
    return base


def get_streamable_http_endpoint(base_url: str) -> str:
    """
    Get the Streamable HTTP endpoint URL.
    
    Args:
        base_url: Base server URL
        
    Returns:
        MCP endpoint URL
    """
    base = base_url.rstrip('/')
    # Remove /sse suffix if present
    if base.endswith('/sse'):
        base = base[:-4]
    if not base.endswith('/mcp'):
        return f"{base}/mcp"
    return base


class TransportNegotiator:
    """
    Handles automatic transport negotiation with MCP servers.
    
    This class implements the backward compatibility algorithm
    from the MCP specification for detecting server capabilities.
    """
    
    def __init__(self, base_url: str):
        """
        Initialize negotiator.
        
        Args:
            base_url: Server base URL
        """
        self.base_url = base_url
        self._detected_transport: Optional[str] = None
    
    @property
    def detected_transport(self) -> Optional[str]:
        """Get the detected transport type."""
        return self._detected_transport
    
    def set_detected_transport(self, transport: str) -> None:
        """
        Set the detected transport type.
        
        Args:
            transport: Transport type ("http_stream" or "sse")
        """
        self._detected_transport = transport
    
    def get_endpoint_url(self) -> str:
        """
        Get the appropriate endpoint URL based on detected transport.
        
        Returns:
            Endpoint URL for the detected transport
        """
        if self._detected_transport == "sse":
            return get_legacy_sse_endpoint(self.base_url)
        return get_streamable_http_endpoint(self.base_url)
    
    def should_try_streamable_first(self) -> bool:
        """
        Determine if Streamable HTTP should be tried first.
        
        Per MCP spec, clients should try Streamable HTTP first
        unless the URL explicitly indicates legacy SSE.
        
        Returns:
            True if should try Streamable HTTP first
        """
        return not is_legacy_sse_url(self.base_url)
