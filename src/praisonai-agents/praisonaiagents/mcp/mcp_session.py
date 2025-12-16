"""
MCP Session Management Module.

This module provides session management utilities for MCP transports,
implementing the session management requirements from MCP Protocol
Revision 2025-11-25.

Features:
- Session ID validation (visible ASCII 0x21-0x7E)
- Session lifecycle management
- Protocol version header handling
- Session expiration detection
"""

import re
from typing import Optional, Dict, Any


# Valid protocol versions
VALID_PROTOCOL_VERSIONS = {
    '2024-11-05',  # Original HTTP+SSE
    '2025-03-26',  # Streamable HTTP introduction
    '2025-06-18',  # Updates
    '2025-11-25',  # Current revision
}

# Default protocol version for backward compatibility
DEFAULT_PROTOCOL_VERSION = '2025-03-26'


def is_valid_session_id(session_id: Optional[str]) -> bool:
    """
    Validate MCP session ID per specification.
    
    Session IDs MUST only contain visible ASCII characters (0x21 to 0x7E).
    This excludes space (0x20), control characters (0x00-0x1F), and DEL (0x7F).
    
    Args:
        session_id: The session ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if session_id is None or session_id == "":
        return False
    
    # Check each character is in visible ASCII range (0x21-0x7E)
    for char in session_id:
        code = ord(char)
        if code < 0x21 or code > 0x7E:
            return False
    
    return True


def is_valid_protocol_version(version: Optional[str]) -> bool:
    """
    Validate MCP protocol version string.
    
    Args:
        version: Protocol version string (e.g., '2025-11-25')
        
    Returns:
        True if valid, False otherwise
    """
    if not version:
        return False
    
    # Check format: YYYY-MM-DD
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', version):
        return False
    
    return True


def is_session_expired(status_code: int) -> bool:
    """
    Check if HTTP status code indicates session expiration.
    
    Per MCP spec, HTTP 404 indicates the session has been terminated.
    
    Args:
        status_code: HTTP response status code
        
    Returns:
        True if session is expired, False otherwise
    """
    return status_code == 404


def extract_session_id(headers: Dict[str, str]) -> Optional[str]:
    """
    Extract session ID from HTTP response headers.
    
    The header name is case-insensitive per HTTP spec.
    
    Args:
        headers: HTTP response headers dictionary
        
    Returns:
        Session ID if present, None otherwise
    """
    # Check various case combinations
    for key in headers:
        if key.lower() == 'mcp-session-id':
            return headers[key]
    return None


class SessionManager:
    """
    Manages MCP session state for HTTP transports.
    
    This class handles:
    - Session ID storage and validation
    - Protocol version negotiation
    - Session lifecycle (active, expired, terminated)
    - Header generation for requests
    
    Example:
        ```python
        manager = SessionManager()
        
        # After receiving InitializeResult with session ID
        manager.set_session_id("abc123")
        
        # Get headers for subsequent requests
        headers = manager.get_headers()
        # {'Mcp-Session-Id': 'abc123', 'Mcp-Protocol-Version': '2025-03-26'}
        ```
    """
    
    def __init__(self, protocol_version: Optional[str] = None):
        """
        Initialize session manager.
        
        Args:
            protocol_version: Initial protocol version (defaults to 2025-03-26)
        """
        self._session_id: Optional[str] = None
        self._protocol_version: str = protocol_version or DEFAULT_PROTOCOL_VERSION
        self._is_expired: bool = False
        self._metadata: Dict[str, Any] = {}
    
    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID."""
        return self._session_id
    
    @property
    def protocol_version(self) -> str:
        """Get current protocol version."""
        return self._protocol_version
    
    @property
    def is_active(self) -> bool:
        """Check if session is active (has ID and not expired)."""
        return self._session_id is not None and not self._is_expired
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return self._is_expired
    
    def set_session_id(self, session_id: str) -> None:
        """
        Set the session ID.
        
        Args:
            session_id: The session ID from server
            
        Raises:
            ValueError: If session ID is invalid
        """
        if not is_valid_session_id(session_id):
            raise ValueError("Invalid session ID: must contain only visible ASCII (0x21-0x7E)")
        
        self._session_id = session_id
        self._is_expired = False
    
    def set_protocol_version(self, version: str) -> None:
        """
        Set the negotiated protocol version.
        
        Args:
            version: Protocol version string
            
        Raises:
            ValueError: If version format is invalid
        """
        if not is_valid_protocol_version(version):
            raise ValueError(f"Invalid protocol version format: {version}")
        
        self._protocol_version = version
    
    def clear(self) -> None:
        """Clear the session (logout/disconnect)."""
        self._session_id = None
        self._is_expired = False
        self._metadata = {}
    
    def mark_expired(self) -> None:
        """Mark the session as expired (received HTTP 404)."""
        self._is_expired = True
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for MCP requests.
        
        Returns:
            Dictionary of headers to include in requests
        """
        headers = {
            'Mcp-Protocol-Version': self._protocol_version
        }
        
        if self._session_id:
            headers['Mcp-Session-Id'] = self._session_id
        
        return headers
    
    def update_from_response(self, headers: Dict[str, str], status_code: int = 200) -> None:
        """
        Update session state from HTTP response.
        
        Args:
            headers: Response headers
            status_code: HTTP status code
        """
        # Check for session expiration
        if is_session_expired(status_code):
            self.mark_expired()
            return
        
        # Extract and update session ID if present
        new_session_id = extract_session_id(headers)
        if new_session_id:
            self.set_session_id(new_session_id)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Store arbitrary metadata with the session."""
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieve metadata from the session."""
        return self._metadata.get(key, default)


class ResumabilityManager:
    """
    Manages SSE stream resumability for MCP transports.
    
    This class handles:
    - Event ID tracking per stream
    - Last-Event-ID header generation
    - Retry delay handling
    
    Per MCP spec, event IDs should be assigned per-stream to act as
    a cursor within that particular stream.
    """
    
    def __init__(self):
        """Initialize resumability manager."""
        self._last_event_ids: Dict[str, str] = {}  # stream_id -> last_event_id
        self._retry_delay: int = 3000  # Default retry delay in ms
    
    def set_last_event_id(self, stream_id: str, event_id: str) -> None:
        """
        Store the last received event ID for a stream.
        
        Args:
            stream_id: Identifier for the SSE stream
            event_id: The event ID from the SSE event
        """
        self._last_event_ids[stream_id] = event_id
    
    def get_last_event_id(self, stream_id: str) -> Optional[str]:
        """
        Get the last received event ID for a stream.
        
        Args:
            stream_id: Identifier for the SSE stream
            
        Returns:
            Last event ID if available, None otherwise
        """
        return self._last_event_ids.get(stream_id)
    
    def set_retry_delay(self, delay_ms: int) -> None:
        """
        Set the retry delay from SSE retry field.
        
        Args:
            delay_ms: Delay in milliseconds
        """
        self._retry_delay = delay_ms
    
    def get_retry_delay(self) -> int:
        """Get current retry delay in milliseconds."""
        return self._retry_delay
    
    def get_resume_headers(self, stream_id: str) -> Dict[str, str]:
        """
        Get headers for resuming a stream.
        
        Args:
            stream_id: Identifier for the SSE stream
            
        Returns:
            Headers dict with Last-Event-ID if available
        """
        headers = {}
        last_event_id = self.get_last_event_id(stream_id)
        if last_event_id:
            headers['Last-Event-ID'] = last_event_id
        return headers
    
    def clear_stream(self, stream_id: str) -> None:
        """Clear tracking for a specific stream."""
        self._last_event_ids.pop(stream_id, None)
    
    def clear_all(self) -> None:
        """Clear all stream tracking."""
        self._last_event_ids.clear()


def parse_sse_event(event_text: str) -> Dict[str, Any]:
    """
    Parse an SSE event into its components.
    
    SSE events have the format:
        id: <event-id>
        retry: <milliseconds>
        data: <data-line>
        data: <data-line-2>
        
        (blank line ends event)
    
    Args:
        event_text: Raw SSE event text
        
    Returns:
        Dictionary with 'id', 'retry', 'data', 'event' fields as available
    """
    result: Dict[str, Any] = {}
    data_lines = []
    
    for line in event_text.strip().split('\n'):
        if line.startswith('id:'):
            result['id'] = line[3:].strip()
        elif line.startswith('retry:'):
            try:
                result['retry'] = int(line[6:].strip())
            except ValueError:
                pass
        elif line.startswith('data:'):
            data_lines.append(line[5:].strip())
        elif line.startswith('event:'):
            result['event'] = line[6:].strip()
    
    # Join multiple data lines with newlines
    if data_lines:
        result['data'] = '\n'.join(data_lines)
    
    return result


class EventStore:
    """
    Optional event store for message redelivery support.
    
    This class stores events per stream to enable replay when
    clients reconnect with Last-Event-ID header.
    
    Note: This is an in-memory store suitable for single-server
    deployments. For multi-node deployments, use an external
    store (Redis, database, etc.).
    """
    
    def __init__(self, max_events: int = 1000):
        """
        Initialize event store.
        
        Args:
            max_events: Maximum events to store per stream
        """
        self.max_events = max_events
        self._streams: Dict[str, list] = {}  # stream_id -> [(event_id, data), ...]
    
    def store(self, stream_id: str, event_id: str, data: Any) -> None:
        """
        Store an event for potential replay.
        
        Args:
            stream_id: Identifier for the SSE stream
            event_id: The event ID
            data: The event data
        """
        if stream_id not in self._streams:
            self._streams[stream_id] = []
        
        self._streams[stream_id].append((event_id, data))
        
        # Trim to max_events
        if len(self._streams[stream_id]) > self.max_events:
            self._streams[stream_id] = self._streams[stream_id][-self.max_events:]
    
    def get_events_after(self, stream_id: str, after_event_id: str) -> list:
        """
        Get events after a specific event ID.
        
        Args:
            stream_id: Identifier for the SSE stream
            after_event_id: The Last-Event-ID from client
            
        Returns:
            List of event data after the specified event
        """
        if stream_id not in self._streams:
            return []
        
        events = self._streams[stream_id]
        
        # Find the index of the after_event_id
        start_index = None
        for i, (event_id, _) in enumerate(events):
            if event_id == after_event_id:
                start_index = i + 1
                break
        
        if start_index is None:
            return []
        
        return [data for _, data in events[start_index:]]
    
    def get_all_events(self, stream_id: str) -> list:
        """
        Get all stored events for a stream.
        
        Args:
            stream_id: Identifier for the SSE stream
            
        Returns:
            List of all event data
        """
        if stream_id not in self._streams:
            return []
        
        return [data for _, data in self._streams[stream_id]]
    
    def clear_stream(self, stream_id: str) -> None:
        """Clear events for a specific stream."""
        self._streams.pop(stream_id, None)
    
    def clear_all(self) -> None:
        """Clear all stored events."""
        self._streams.clear()
