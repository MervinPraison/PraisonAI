"""
Recipe HTTP Server

Provides HTTP endpoints for recipe execution.
Optional dependency - requires: pip install praisonai[serve]

Endpoints:
- GET  /health           - Health check
- GET  /v1/recipes       - List recipes
- GET  /v1/recipes/{name} - Describe recipe
- GET  /v1/recipes/{name}/schema - Get recipe schema
- POST /v1/recipes/run   - Run recipe (sync)
- POST /v1/recipes/stream - Run recipe (SSE)

Auth modes:
- none: No authentication (localhost only)
- api-key: X-API-Key header required
- jwt: Bearer token required (future)

Config file (serve.yaml):
```yaml
host: 127.0.0.1
port: 8765
auth: api-key
api_key: your-secret-key  # or use PRAISONAI_API_KEY env var
recipes:
  - my-recipe
  - another-recipe
preload: true
cors_origins: "*"
```
"""

import json
import os
from typing import Any, Dict, Optional


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from file.
    
    Precedence: CLI flags > env vars > config file > defaults
    """
    config = {}
    
    if config_path and os.path.exists(config_path):
        try:
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except ImportError:
            # Fall back to JSON if yaml not available
            with open(config_path) as f:
                config = json.load(f)
    
    # Apply env var overrides
    if os.environ.get("PRAISONAI_API_KEY"):
        config["api_key"] = os.environ["PRAISONAI_API_KEY"]
    if os.environ.get("PRAISONAI_SERVE_HOST"):
        config["host"] = os.environ["PRAISONAI_SERVE_HOST"]
    if os.environ.get("PRAISONAI_SERVE_PORT"):
        config["port"] = int(os.environ["PRAISONAI_SERVE_PORT"])
    
    return config


def create_auth_middleware(auth_type: str, api_key: Optional[str] = None):
    """Create authentication middleware."""
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
    except ImportError:
        return None
    
    class APIKeyAuthMiddleware(BaseHTTPMiddleware):
        """API Key authentication middleware."""
        
        async def dispatch(self, request, call_next):
            # Skip auth for health endpoint
            if request.url.path == "/health":
                return await call_next(request)
            
            # Check X-API-Key header
            provided_key = request.headers.get("X-API-Key")
            expected_key = api_key or os.environ.get("PRAISONAI_API_KEY")
            
            if not expected_key:
                # No key configured, allow request
                return await call_next(request)
            
            if provided_key != expected_key:
                return JSONResponse(
                    {"error": {"code": "unauthorized", "message": "Invalid or missing API key"}},
                    status_code=401
                )
            
            return await call_next(request)
    
    if auth_type == "api-key":
        return APIKeyAuthMiddleware
    
    return None


def create_app(config: Optional[Dict[str, Any]] = None) -> Any:
    """
    Create ASGI application for recipe runner.
    
    Args:
        config: Optional configuration dict
        
    Returns:
        Starlette ASGI application
    """
    try:
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse, Response
        from starlette.requests import Request
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError(
            "Serve dependencies not installed. Run: pip install praisonai[serve]"
        )
    
    config = config or {}
    
    async def health(request: Request) -> JSONResponse:
        """GET /health - Health check."""
        return JSONResponse({
            "status": "healthy",
            "service": "praisonai-recipe-runner",
            "version": _get_version(),
        })
    
    async def list_recipes(request: Request) -> JSONResponse:
        """GET /v1/recipes - List available recipes."""
        from praisonai import recipe
        
        source_filter = request.query_params.get("source")
        tags = request.query_params.get("tags")
        tags_list = tags.split(",") if tags else None
        
        recipes = recipe.list_recipes(
            source_filter=source_filter,
            tags=tags_list,
        )
        
        return JSONResponse({
            "recipes": [r.to_dict() for r in recipes]
        })
    
    async def describe_recipe(request: Request) -> JSONResponse:
        """GET /v1/recipes/{name} - Describe a recipe."""
        name = request.path_params["name"]
        
        from praisonai import recipe
        info = recipe.describe(name)
        
        if info is None:
            return JSONResponse(
                {"error": {"code": "not_found", "message": f"Recipe not found: {name}"}},
                status_code=404
            )
        
        return JSONResponse(info.to_dict())
    
    async def get_schema(request: Request) -> JSONResponse:
        """GET /v1/recipes/{name}/schema - Get recipe JSON schema."""
        name = request.path_params["name"]
        
        from praisonai import recipe
        info = recipe.describe(name)
        
        if info is None:
            return JSONResponse(
                {"error": {"code": "not_found", "message": f"Recipe not found: {name}"}},
                status_code=404
            )
        
        return JSONResponse({
            "name": info.name,
            "version": info.version,
            "input_schema": info.config_schema,
            "output_schema": info.outputs,
        })
    
    async def run_recipe(request: Request) -> JSONResponse:
        """POST /v1/recipes/run - Run a recipe."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": {"code": "invalid_json", "message": "Invalid JSON body"}},
                status_code=400
            )
        
        recipe_name = body.get("recipe")
        if not recipe_name:
            return JSONResponse(
                {"error": {"code": "missing_recipe", "message": "Recipe name required"}},
                status_code=400
            )
        
        input_data = body.get("input", {})
        config_data = body.get("config", {})
        options = body.get("options", {})
        session_id = body.get("session_id")
        
        from praisonai import recipe
        result = recipe.run(
            recipe_name,
            input=input_data,
            config=config_data,
            session_id=session_id,
            options=options,
        )
        
        status_code = 200 if result.ok else 500
        if result.status == "policy_denied":
            status_code = 403
        elif result.status == "missing_deps":
            status_code = 424  # Failed Dependency
        elif result.status == "validation_error":
            status_code = 400
        
        return JSONResponse(result.to_dict(), status_code=status_code)
    
    async def stream_recipe(request: Request) -> Response:
        """POST /v1/recipes/stream - Stream recipe execution."""
        try:
            from sse_starlette.sse import EventSourceResponse
        except ImportError:
            return JSONResponse(
                {"error": {"code": "sse_unavailable", "message": "SSE not available"}},
                status_code=501
            )
        
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": {"code": "invalid_json", "message": "Invalid JSON body"}},
                status_code=400
            )
        
        recipe_name = body.get("recipe")
        if not recipe_name:
            return JSONResponse(
                {"error": {"code": "missing_recipe", "message": "Recipe name required"}},
                status_code=400
            )
        
        input_data = body.get("input", {})
        config_data = body.get("config", {})
        options = body.get("options", {})
        session_id = body.get("session_id")
        
        async def event_generator():
            from praisonai import recipe
            for event in recipe.run_stream(
                recipe_name,
                input=input_data,
                config=config_data,
                session_id=session_id,
                options=options,
            ):
                yield {
                    "event": event.event_type,
                    "data": json.dumps(event.data),
                }
        
        return EventSourceResponse(event_generator())
    
    async def validate_recipe(request: Request) -> JSONResponse:
        """POST /v1/recipes/validate - Validate a recipe."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": {"code": "invalid_json", "message": "Invalid JSON body"}},
                status_code=400
            )
        
        recipe_name = body.get("recipe")
        if not recipe_name:
            return JSONResponse(
                {"error": {"code": "missing_recipe", "message": "Recipe name required"}},
                status_code=400
            )
        
        from praisonai import recipe
        result = recipe.validate(recipe_name)
        
        status_code = 200 if result.valid else 400
        return JSONResponse(result.to_dict(), status_code=status_code)
    
    # Build routes
    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/v1/recipes", list_recipes, methods=["GET"]),
        Route("/v1/recipes/run", run_recipe, methods=["POST"]),
        Route("/v1/recipes/stream", stream_recipe, methods=["POST"]),
        Route("/v1/recipes/validate", validate_recipe, methods=["POST"]),
        Route("/v1/recipes/{name}", describe_recipe, methods=["GET"]),
        Route("/v1/recipes/{name}/schema", get_schema, methods=["GET"]),
    ]
    
    # Add CORS middleware if configured
    middleware = []
    cors_origins = config.get("cors_origins")
    if cors_origins:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=cors_origins.split(",") if isinstance(cors_origins, str) else cors_origins,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )
    
    # Add auth middleware if configured
    auth_type = config.get("auth")
    if auth_type and auth_type != "none":
        auth_middleware = create_auth_middleware(auth_type, config.get("api_key"))
        if auth_middleware:
            middleware.append(Middleware(auth_middleware))
    
    return Starlette(routes=routes, middleware=middleware)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    reload: bool = False,
    config: Optional[Dict[str, Any]] = None,
):
    """
    Start the recipe runner server.
    
    Args:
        host: Server host (default: 127.0.0.1)
        port: Server port (default: 8765)
        reload: Enable hot reload (default: False)
        config: Optional configuration dict
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "Serve dependencies not installed. Run: pip install praisonai[serve]"
        )
    
    app = create_app(config)
    uvicorn.run(app, host=host, port=port, reload=reload)


def _get_version() -> str:
    """Get PraisonAI version."""
    try:
        from praisonai.version import __version__
        return __version__
    except ImportError:
        return "unknown"
