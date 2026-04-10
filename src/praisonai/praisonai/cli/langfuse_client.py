"""
Langfuse API Client for PraisonAI CLI.

Provides a simple HTTP client for fetching traces, sessions, and observations
from the Langfuse API. Used by the `praisonai langfuse` CLI commands to enable
trace and session viewing without opening the web UI.

The client reads configuration from:
1. Explicit parameters passed to constructor
2. Environment variables (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST)
3. ~/.praisonai/langfuse.env file (created by `praisonai langfuse config`)

Example:
    from praisonai.cli.langfuse_client import LangfuseClient
    
    # Load from config file automatically
    client = LangfuseClient.from_config_file()
    
    # Fetch traces
    traces = client.get_traces(limit=10)
    
    # Fetch sessions
    sessions = client.get_sessions()
    
    # Get trace details
    trace = client.get_trace("trace-id-123")
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth


class LangfuseAPIError(Exception):
    """Raised when Langfuse API returns an error."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class LangfuseClient:
    """
    HTTP client for Langfuse API.
    
    Provides methods to fetch traces, sessions, and detailed trace information
    from a Langfuse instance (local Docker or cloud).
    
    Authentication uses HTTP Basic Auth with public_key as username and
    secret_key as password (standard Langfuse API authentication).
    
    Attributes:
        public_key: Langfuse public API key
        secret_key: Langfuse secret API key
        host: Langfuse host URL (default: http://localhost:3000)
    """
    
    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "http://localhost:3000"
    ):
        """
        Initialize Langfuse API client.
        
        Args:
            public_key: Langfuse public API key
            secret_key: Langfuse secret API key
            host: Langfuse host URL (default: http://localhost:3000)
        
        Raises:
            ValueError: If public_key or secret_key is empty
        """
        if not public_key or not secret_key:
            raise ValueError("Both public_key and secret_key are required")
        
        self.public_key = public_key
        self.secret_key = secret_key
        self.host = host.rstrip("/")  # Remove trailing slash
        self._auth = HTTPBasicAuth(public_key, secret_key)
    
    @classmethod
    def from_config_file(cls, config_path: Optional[Path] = None) -> "LangfuseClient":
        """
        Create client from praisonai config file.
        
        Reads configuration from ~/.praisonai/langfuse.env file which is
        created by `praisonai langfuse config` command.
        
        Args:
            config_path: Path to config file (default: ~/.praisonai/langfuse.env)
        
        Returns:
            Configured LangfuseClient instance
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is missing required credentials
        """
        if config_path is None:
            config_path = Path.home() / ".praisonai" / "langfuse.env"
        
        if not config_path.exists():
            raise FileNotFoundError(
                f"Langfuse config not found at {config_path}. "
                f"Run 'praisonai langfuse config --public-key ... --secret-key ...' to set up."
            )
        
        # Load env vars from file
        env_vars = {}
        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
        
        public_key = env_vars.get("LANGFUSE_PUBLIC_KEY") or os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = env_vars.get("LANGFUSE_SECRET_KEY") or os.getenv("LANGFUSE_SECRET_KEY")
        host = env_vars.get("LANGFUSE_HOST") or env_vars.get("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")
        
        if not public_key or not secret_key:
            raise ValueError(
                f"Missing Langfuse credentials in {config_path}. "
                f"Ensure LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set."
            )
        
        return cls(public_key=public_key, secret_key=secret_key, host=host)
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make authenticated GET request to Langfuse API.
        
        Args:
            endpoint: API endpoint path (e.g., "/api/public/traces")
            params: Optional query parameters
        
        Returns:
            JSON response as dictionary
        
        Raises:
            LangfuseAPIError: If API request fails
        """
        url = f"{self.host}{endpoint}"
        
        try:
            response = requests.get(url, auth=self._auth, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise LangfuseAPIError(
                    "Authentication failed. Check your LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.",
                    status_code=401
                )
            elif response.status_code == 404:
                raise LangfuseAPIError(
                    f"Resource not found: {endpoint}",
                    status_code=404
                )
            else:
                raise LangfuseAPIError(
                    f"API error: {e}",
                    status_code=response.status_code
                )
        except requests.exceptions.ConnectionError:
            raise LangfuseAPIError(
                f"Cannot connect to Langfuse at {self.host}. "
                f"Ensure the server is running (try 'praisonai langfuse status')."
            )
        except requests.exceptions.Timeout:
            raise LangfuseAPIError("Request timed out. Langfuse server may be slow or unavailable.")
        except Exception as e:
            raise LangfuseAPIError(f"Unexpected error: {e}")
    
    def get_traces(
        self,
        limit: int = 20,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        name: Optional[str] = None,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch traces from Langfuse API.
        
        Args:
            limit: Maximum number of traces to return (default: 20, max: 100)
            session_id: Filter by session ID
            user_id: Filter by user ID
            name: Filter by trace name (e.g., agent name)
            from_timestamp: Filter traces after this time
            to_timestamp: Filter traces before this time
        
        Returns:
            List of trace dictionaries
        
        Example:
            traces = client.get_traces(limit=10, session_id="abc-123")
            for trace in traces:
                print(f"Trace {trace['id']}: {trace['name']}")
        """
        params: Dict[str, Any] = {"limit": min(limit, 100)}
        
        if session_id:
            params["sessionId"] = session_id
        if user_id:
            params["userId"] = user_id
        if name:
            params["name"] = name
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp.isoformat()
        if to_timestamp:
            params["toTimestamp"] = to_timestamp.isoformat()
        
        response = self._make_request("/api/public/traces", params)
        return response.get("data", [])
    
    def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """
        Fetch detailed information about a specific trace.
        
        Args:
            trace_id: Unique trace identifier
        
        Returns:
            Trace detail dictionary including observations and scores
        
        Raises:
            LangfuseAPIError: If trace not found or API error
        
        Example:
            trace = client.get_trace("trace-123")
            print(f"Name: {trace['name']}")
            print(f"Observations: {len(trace['observations'])}")
        """
        return self._make_request(f"/api/public/traces/{trace_id}")
    
    def get_sessions(
        self,
        limit: int = 20,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch sessions from Langfuse API.
        
        Args:
            limit: Maximum number of sessions to return (default: 20, max: 100)
            from_timestamp: Filter sessions after this time
            to_timestamp: Filter sessions before this time
        
        Returns:
            List of session dictionaries with trace counts
        
        Example:
            sessions = client.get_sessions(limit=10)
            for session in sessions:
                print(f"Session {session['id']}: {session['traceCount']} traces")
        """
        params: Dict[str, Any] = {"limit": min(limit, 100)}
        
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp.isoformat()
        if to_timestamp:
            params["toTimestamp"] = to_timestamp.isoformat()
        
        response = self._make_request("/api/public/sessions", params)
        return response.get("data", [])
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Fetch detailed information about a specific session.
        
        Args:
            session_id: Unique session identifier
        
        Returns:
            Session detail dictionary with traces
        
        Raises:
            LangfuseAPIError: If session not found or API error
        """
        return self._make_request(f"/api/public/sessions/{session_id}")
    
    def get_observations(
        self,
        trace_id: Optional[str] = None,
        type: Optional[str] = None,  # "SPAN", "EVENT", "GENERATION"
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch observations from Langfuse API.
        
        Args:
            trace_id: Filter by trace ID
            type: Filter by observation type (SPAN, EVENT, GENERATION)
            limit: Maximum number of observations (default: 100)
        
        Returns:
            List of observation dictionaries
        """
        params: Dict[str, Any] = {"limit": min(limit, 100)}
        
        if trace_id:
            params["traceId"] = trace_id
        if type:
            params["type"] = type
        
        response = self._make_request("/api/public/observations", params)
        return response.get("data", [])
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get basic statistics about the Langfuse project.
        
        Returns:
            Dictionary with trace count, session count, and time range
        """
        # Fetch traces with limit=1 to get total count from meta
        response = self._make_request("/api/public/traces", {"limit": 1})
        
        total_traces = response.get("meta", {}).get("totalCount", 0)
        
        # Fetch sessions with limit=1 to get total count
        sessions_response = self._make_request("/api/public/sessions", {"limit": 1})
        total_sessions = sessions_response.get("meta", {}).get("totalCount", 0)
        
        return {
            "total_traces": total_traces,
            "total_sessions": total_sessions,
            "host": self.host
        }


def load_env_from_file(file_path: Path) -> Dict[str, str]:
    """
    Load environment variables from a .env file.
    
    Args:
        file_path: Path to the .env file
    
    Returns:
        Dictionary of environment variables
    """
    env_vars = {}
    if file_path.exists():
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars
