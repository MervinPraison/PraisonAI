"""
AgentApp configuration.

This module defines the configuration dataclass for AgentApp.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentAppConfig:
    """
    Configuration for AgentApp.
    
    This dataclass holds all configuration options for an AgentApp instance.
    It follows the PraisonAI principle of sensible defaults with explicit overrides.
    
    Attributes:
        name: Name of the application (default: "PraisonAI App")
        host: Host address to bind to (default: "0.0.0.0")
        port: Port number to listen on (default: 8000)
        reload: Enable auto-reload for development (default: False)
        cors_origins: List of allowed CORS origins (default: ["*"])
        api_prefix: API route prefix (default: "/api")
        docs_url: URL for API documentation (default: "/docs")
        openapi_url: URL for OpenAPI schema (default: "/openapi.json")
        debug: Enable debug mode (default: False)
        log_level: Logging level (default: "info")
        workers: Number of worker processes (default: 1)
        timeout: Request timeout in seconds (default: 60)
        metadata: Additional metadata for the app
    
    Example:
        config = AgentAppConfig(
            name="My AI App",
            port=9000,
            reload=True,
            debug=True
        )
    """
    
    name: str = "PraisonAI App"
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    api_prefix: str = "/api"
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    debug: bool = False
    log_level: str = "info"
    workers: int = 1
    timeout: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)
