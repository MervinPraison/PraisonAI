"""
Unified Server Utilities

Provides utilities for adding discovery endpoints to any server.
"""

from typing import Any, List, Optional

from .discovery import (
    DiscoveryDocument,
    EndpointInfo,
    ProviderInfo,
    SCHEMA_VERSION,
    create_discovery_document,
)


def add_discovery_routes(
    app: Any,
    discovery: DiscoveryDocument,
    path: str = "/__praisonai__/discovery",
) -> None:
    """
    Add unified discovery routes to a Starlette/FastAPI application.
    
    Args:
        app: Starlette or FastAPI application
        discovery: DiscoveryDocument to serve
        path: Path for discovery endpoint
    """
    try:
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError:
        # Try FastAPI
        try:
            from fastapi.responses import JSONResponse
        except ImportError:
            raise ImportError("Starlette or FastAPI required for discovery routes")
    
    async def discovery_handler(request):
        """Return discovery document."""
        return JSONResponse(discovery.to_dict())
    
    async def health_handler(request):
        """Return health status with discovery info."""
        return JSONResponse({
            "status": "healthy",
            "schema_version": SCHEMA_VERSION,
            "server_name": discovery.server_name,
            "server_version": discovery.server_version,
            "providers": [p.type for p in discovery.providers],
            "endpoint_count": len(discovery.endpoints),
        })
    
    # Add routes based on app type
    if hasattr(app, 'add_api_route'):
        # FastAPI
        app.add_api_route(path, discovery_handler, methods=["GET"])
        if not _has_route(app, "/health"):
            app.add_api_route("/health", health_handler, methods=["GET"])
    elif hasattr(app, 'routes'):
        # Starlette
        app.routes.append(Route(path, discovery_handler, methods=["GET"]))
        if not _has_route(app, "/health"):
            app.routes.append(Route("/health", health_handler, methods=["GET"]))


def _has_route(app: Any, path: str) -> bool:
    """Check if app already has a route at path."""
    if hasattr(app, 'routes'):
        for route in app.routes:
            if hasattr(route, 'path') and route.path == path:
                return True
    return False


def create_unified_app(
    providers: Optional[List[str]] = None,
    server_name: str = "praisonai",
    host: str = "127.0.0.1",
    port: int = 8765,
    cors_origins: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Any:
    """
    Create a unified server application with discovery support.
    
    Args:
        providers: List of provider types to enable
        server_name: Server name for discovery
        host: Server host
        port: Server port
        cors_origins: CORS allowed origins
        api_key: Optional API key for authentication
        
    Returns:
        FastAPI application
    """
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError("FastAPI required. Install with: pip install fastapi")
    
    # Create discovery document
    discovery = create_discovery_document(server_name=server_name)
    
    # Create FastAPI app
    app = FastAPI(
        title=f"{server_name} Unified API",
        description="Unified PraisonAI endpoints server",
        version=discovery.server_version,
    )
    
    # Add CORS if configured
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # Add discovery routes
    add_discovery_routes(app, discovery)
    
    # Store discovery document for later modification
    app.state.discovery = discovery
    
    return app


def register_endpoint_to_discovery(
    app: Any,
    endpoint: EndpointInfo,
) -> None:
    """
    Register an endpoint to the app's discovery document.
    
    Args:
        app: FastAPI/Starlette app with discovery
        endpoint: EndpointInfo to register
    """
    if hasattr(app, 'state') and hasattr(app.state, 'discovery'):
        app.state.discovery.add_endpoint(endpoint)


def register_provider_to_discovery(
    app: Any,
    provider: ProviderInfo,
) -> None:
    """
    Register a provider to the app's discovery document.
    
    Args:
        app: FastAPI/Starlette app with discovery
        provider: ProviderInfo to register
    """
    if hasattr(app, 'state') and hasattr(app.state, 'discovery'):
        app.state.discovery.add_provider(provider)
