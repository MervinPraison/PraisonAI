"""
Recipe HTTP Server

Provides HTTP endpoints for recipe execution.
Optional dependency - requires: pip install praisonai[serve]

Endpoints:
- GET  /health              - Health check
- GET  /v1/recipes          - List recipes
- GET  /v1/recipes/{name}   - Describe recipe
- GET  /v1/recipes/{name}/schema - Get recipe schema
- POST /v1/recipes/run      - Run recipe (sync)
- POST /v1/recipes/stream   - Run recipe (SSE)
- POST /v1/recipes/validate - Validate recipe
- GET  /metrics             - Prometheus metrics (optional)
- GET  /openapi.json        - OpenAPI specification
- POST /admin/reload        - Hot reload registry (auth required)

Auth modes:
- none: No authentication (localhost only)
- api-key: X-API-Key header required
- jwt: Bearer token required

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
rate_limit: 100           # requests per minute (0 = disabled)
max_request_size: 10485760  # 10MB default
enable_metrics: false     # Enable /metrics endpoint
enable_admin: false       # Enable /admin/* endpoints
trace_exporter: none      # none, otlp, jaeger, zipkin
```
"""

import json
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


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


# Default constants
DEFAULT_MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_RATE_LIMIT = 100  # requests per minute
DEFAULT_RATE_LIMIT_EXEMPT_PATHS = ["/health", "/metrics"]


class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""
    
    def __init__(self, requests_per_minute: int = DEFAULT_RATE_LIMIT):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        self._requests: Dict[str, List[float]] = defaultdict(list)
    
    def check(self, client_id: str) -> Tuple[bool, int]:
        """
        Check if request is allowed.
        
        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        if self.requests_per_minute <= 0:
            return True, 0
        
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self._requests[client_id] = [
            t for t in self._requests[client_id] if t > window_start
        ]
        
        if len(self._requests[client_id]) >= self.requests_per_minute:
            # Calculate retry-after
            oldest = min(self._requests[client_id])
            retry_after = int(oldest + self.window_seconds - now) + 1
            return False, max(1, retry_after)
        
        self._requests[client_id].append(now)
        return True, 0


def create_rate_limiter(requests_per_minute: int = DEFAULT_RATE_LIMIT) -> RateLimiter:
    """Create a rate limiter instance."""
    return RateLimiter(requests_per_minute=requests_per_minute)


class MetricsCollector:
    """Simple in-memory metrics collector for Prometheus format."""
    
    def __init__(self):
        self._requests_total: Dict[str, int] = defaultdict(int)
        self._request_durations: Dict[str, List[float]] = defaultdict(list)
        self._errors_total: Dict[str, int] = defaultdict(int)
    
    def record_request(self, path: str, method: str, status: int, duration: float):
        """Record a request."""
        # Normalize path to avoid label explosion
        normalized_path = self._normalize_path(path)
        key = f'{normalized_path}|{method}|{status}'
        self._requests_total[key] += 1
        self._request_durations[f'{normalized_path}|{method}'].append(duration)
        
        if status >= 400:
            error_type = "client_error" if status < 500 else "server_error"
            error_key = f'{normalized_path}|{method}|{error_type}'
            self._errors_total[error_key] += 1
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path to avoid label explosion."""
        # Replace dynamic segments
        parts = path.split("/")
        normalized = []
        for i, part in enumerate(parts):
            if i > 0 and parts[i-1] == "recipes" and part not in ["run", "stream", "validate"]:
                normalized.append("{name}")
            else:
                normalized.append(part)
        return "/".join(normalized)
    
    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus exposition format."""
        lines = []
        
        # Requests total
        lines.append("# HELP praisonai_http_requests_total Total HTTP requests")
        lines.append("# TYPE praisonai_http_requests_total counter")
        for key, count in self._requests_total.items():
            path, method, status = key.split("|")
            lines.append(f'praisonai_http_requests_total{{path="{path}",method="{method}",status="{status}"}} {count}')
        
        # Request duration histogram (simplified - just sum and count)
        lines.append("# HELP praisonai_http_request_duration_seconds HTTP request duration")
        lines.append("# TYPE praisonai_http_request_duration_seconds histogram")
        for key, durations in self._request_durations.items():
            path, method = key.split("|")
            if durations:
                total = sum(durations)
                count = len(durations)
                lines.append(f'praisonai_http_request_duration_seconds_sum{{path="{path}",method="{method}"}} {total:.6f}')
                lines.append(f'praisonai_http_request_duration_seconds_count{{path="{path}",method="{method}"}} {count}')
                # Add buckets
                buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
                for bucket in buckets:
                    bucket_count = sum(1 for d in durations if d <= bucket)
                    lines.append(f'praisonai_http_request_duration_seconds_bucket{{path="{path}",method="{method}",le="{bucket}"}} {bucket_count}')
                lines.append(f'praisonai_http_request_duration_seconds_bucket{{path="{path}",method="{method}",le="+Inf"}} {count}')
        
        # Errors total
        lines.append("# HELP praisonai_http_errors_total Total HTTP errors")
        lines.append("# TYPE praisonai_http_errors_total counter")
        for key, count in self._errors_total.items():
            path, method, error_type = key.split("|")
            lines.append(f'praisonai_http_errors_total{{path="{path}",method="{method}",error_type="{error_type}"}} {count}')
        
        return "\n".join(lines)


# Global metrics collector (created per app instance)
_metrics_collector: Optional[MetricsCollector] = None


def get_openapi_spec(config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate OpenAPI specification."""
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "PraisonAI Recipe Runner API",
            "description": "HTTP API for running PraisonAI recipes",
            "version": _get_version(),
        },
        "servers": [
            {"url": f"http://{config.get('host', '127.0.0.1')}:{config.get('port', 8765)}"}
        ],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "responses": {"200": {"description": "Server is healthy"}}
                }
            },
            "/v1/recipes": {
                "get": {
                    "summary": "List available recipes",
                    "parameters": [
                        {"name": "source", "in": "query", "schema": {"type": "string"}},
                        {"name": "tags", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "List of recipes"}}
                }
            },
            "/v1/recipes/{name}": {
                "get": {
                    "summary": "Describe a recipe",
                    "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Recipe details"}, "404": {"description": "Recipe not found"}}
                }
            },
            "/v1/recipes/{name}/schema": {
                "get": {
                    "summary": "Get recipe JSON schema",
                    "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Recipe schema"}}
                }
            },
            "/v1/recipes/run": {
                "post": {
                    "summary": "Run a recipe",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["recipe"],
                                    "properties": {
                                        "recipe": {"type": "string"},
                                        "input": {"type": "object"},
                                        "config": {"type": "object"},
                                        "session_id": {"type": "string"},
                                        "options": {"type": "object"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Recipe result"}}
                }
            },
            "/v1/recipes/stream": {
                "post": {
                    "summary": "Stream recipe execution (SSE)",
                    "responses": {"200": {"description": "SSE event stream"}}
                }
            },
            "/v1/recipes/validate": {
                "post": {
                    "summary": "Validate a recipe",
                    "responses": {"200": {"description": "Validation result"}}
                }
            },
        }
    }
    
    # Add optional endpoints
    if config.get("enable_metrics"):
        spec["paths"]["/metrics"] = {
            "get": {
                "summary": "Prometheus metrics",
                "responses": {"200": {"description": "Metrics in Prometheus format"}}
            }
        }
    
    if config.get("enable_admin"):
        spec["paths"]["/admin/reload"] = {
            "post": {
                "summary": "Hot reload recipe registry",
                "security": [{"apiKey": []}],
                "responses": {"200": {"description": "Reload successful"}, "401": {"description": "Unauthorized"}}
            }
        }
    
    spec["paths"]["/openapi.json"] = {
        "get": {
            "summary": "OpenAPI specification",
            "responses": {"200": {"description": "OpenAPI JSON"}}
        }
    }
    
    return spec


def create_auth_middleware(auth_type: str, api_key: Optional[str] = None, jwt_secret: Optional[str] = None):
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
    
    class JWTAuthMiddleware(BaseHTTPMiddleware):
        """JWT authentication middleware."""
        
        async def dispatch(self, request, call_next):
            # Skip auth for health endpoint
            if request.url.path == "/health":
                return await call_next(request)
            
            # Get JWT secret
            secret = jwt_secret or os.environ.get("PRAISONAI_JWT_SECRET")
            if not secret:
                return await call_next(request)
            
            # Check Authorization header
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    {"error": {"code": "unauthorized", "message": "Missing or invalid Authorization header"}},
                    status_code=401
                )
            
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            try:
                # Lazy import jwt
                import jwt as pyjwt
                payload = pyjwt.decode(token, secret, algorithms=["HS256"])
                # Store user info in request state
                request.state.user = payload
            except ImportError:
                return JSONResponse(
                    {"error": {"code": "server_error", "message": "JWT support not installed. Run: pip install PyJWT"}},
                    status_code=500
                )
            except pyjwt.ExpiredSignatureError:
                return JSONResponse(
                    {"error": {"code": "unauthorized", "message": "Token expired"}},
                    status_code=401
                )
            except pyjwt.InvalidTokenError as e:
                return JSONResponse(
                    {"error": {"code": "unauthorized", "message": f"Invalid token: {e}"}},
                    status_code=401
                )
            
            return await call_next(request)
    
    if auth_type == "api-key":
        return APIKeyAuthMiddleware
    elif auth_type == "jwt":
        return JWTAuthMiddleware
    
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
    
    async def get_metrics(request: Request) -> Response:
        """GET /metrics - Prometheus metrics."""
        global _metrics_collector
        if _metrics_collector is None:
            _metrics_collector = MetricsCollector()
        
        content = _metrics_collector.get_prometheus_metrics()
        return Response(
            content=content,
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )
    
    async def admin_reload(request: Request) -> JSONResponse:
        """POST /admin/reload - Hot reload recipe registry."""
        try:
            from praisonai import recipe
            # Clear any cached recipes and reload
            if hasattr(recipe, '_recipe_cache'):
                recipe._recipe_cache.clear()
            if hasattr(recipe, 'reload_registry'):
                recipe.reload_registry()
            
            return JSONResponse({
                "status": "reloaded",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return JSONResponse(
                {"error": {"code": "reload_failed", "message": str(e)}},
                status_code=500
            )
    
    async def get_openapi(request: Request) -> JSONResponse:
        """GET /openapi.json - OpenAPI specification."""
        spec = get_openapi_spec(config)
        return JSONResponse(spec)
    
    # Build routes
    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/v1/recipes", list_recipes, methods=["GET"]),
        Route("/v1/recipes/run", run_recipe, methods=["POST"]),
        Route("/v1/recipes/stream", stream_recipe, methods=["POST"]),
        Route("/v1/recipes/validate", validate_recipe, methods=["POST"]),
        Route("/v1/recipes/{name}", describe_recipe, methods=["GET"]),
        Route("/v1/recipes/{name}/schema", get_schema, methods=["GET"]),
        Route("/openapi.json", get_openapi, methods=["GET"]),
    ]
    
    # Add optional endpoints
    if config.get("enable_metrics"):
        routes.append(Route("/metrics", get_metrics, methods=["GET"]))
    
    if config.get("enable_admin"):
        routes.append(Route("/admin/reload", admin_reload, methods=["POST"]))
    
    # Initialize metrics collector if enabled
    global _metrics_collector
    if config.get("enable_metrics"):
        _metrics_collector = MetricsCollector()
    
    # Create rate limiter if configured
    rate_limit = config.get("rate_limit", 0)
    rate_limiter = None
    if rate_limit > 0:
        rate_limiter = create_rate_limiter(rate_limit)
    
    # Get max request size
    max_request_size = config.get("max_request_size", DEFAULT_MAX_REQUEST_SIZE)
    
    # Exempt paths for rate limiting
    rate_limit_exempt = config.get("rate_limit_exempt_paths", DEFAULT_RATE_LIMIT_EXEMPT_PATHS)
    
    # Add CORS middleware if configured
    middleware = []
    cors_origins = config.get("cors_origins")
    if cors_origins:
        # Parse CORS configuration
        if isinstance(cors_origins, str):
            origins = [o.strip() for o in cors_origins.split(",")]
        else:
            origins = cors_origins
        
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_methods=config.get("cors_methods", ["*"]),
                allow_headers=config.get("cors_headers", ["*"]),
                allow_credentials=config.get("cors_credentials", False),
                max_age=config.get("cors_max_age", 600),
            )
        )
    
    # Add auth middleware if configured
    auth_type = config.get("auth")
    if auth_type and auth_type != "none":
        auth_middleware = create_auth_middleware(
            auth_type,
            api_key=config.get("api_key"),
            jwt_secret=config.get("jwt_secret"),
        )
        if auth_middleware:
            middleware.append(Middleware(auth_middleware))
    
    # Create rate limit and size limit middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    
    class RateLimitMiddleware(BaseHTTPMiddleware):
        """Rate limiting middleware."""
        
        async def dispatch(self, request, call_next):
            if rate_limiter is None:
                return await call_next(request)
            
            # Skip exempt paths
            if request.url.path in rate_limit_exempt:
                return await call_next(request)
            
            # Get client identifier (IP or API key)
            client_id = request.headers.get("X-API-Key") or request.client.host if request.client else "unknown"
            
            allowed, retry_after = rate_limiter.check(client_id)
            if not allowed:
                return JSONResponse(
                    {"error": {"code": "rate_limited", "message": "Too many requests"}},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)}
                )
            
            return await call_next(request)
    
    class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
        """Request size limit middleware."""
        
        async def dispatch(self, request, call_next):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > max_request_size:
                return JSONResponse(
                    {"error": {"code": "request_too_large", "message": f"Request body too large. Max: {max_request_size} bytes"}},
                    status_code=413
                )
            return await call_next(request)
    
    class MetricsMiddleware(BaseHTTPMiddleware):
        """Metrics collection middleware."""
        
        async def dispatch(self, request, call_next):
            if _metrics_collector is None:
                return await call_next(request)
            
            start_time = time.time()
            response = await call_next(request)
            duration = time.time() - start_time
            
            _metrics_collector.record_request(
                path=request.url.path,
                method=request.method,
                status=response.status_code,
                duration=duration
            )
            
            return response
    
    # Add custom middleware (order matters - first added = outermost)
    if config.get("enable_metrics"):
        middleware.append(Middleware(MetricsMiddleware))
    
    if max_request_size > 0:
        middleware.append(Middleware(RequestSizeLimitMiddleware))
    
    if rate_limiter is not None:
        middleware.append(Middleware(RateLimitMiddleware))
    
    return Starlette(routes=routes, middleware=middleware)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    reload: bool = False,
    config: Optional[Dict[str, Any]] = None,
    workers: int = 1,
):
    """
    Start the recipe runner server.
    
    Args:
        host: Server host (default: 127.0.0.1)
        port: Server port (default: 8765)
        reload: Enable hot reload (default: False)
        config: Optional configuration dict
        workers: Number of worker processes (default: 1)
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "Serve dependencies not installed. Run: pip install praisonai[serve]"
        )
    
    # Initialize OpenTelemetry tracing if configured
    trace_exporter = (config or {}).get("trace_exporter", "none")
    if trace_exporter and trace_exporter != "none":
        _init_tracing(trace_exporter, config or {})
    
    app = create_app(config)
    
    # Workers > 1 requires reload=False
    if workers > 1 and reload:
        import warnings
        warnings.warn("Cannot use reload with multiple workers. Disabling reload.")
        reload = False
    
    uvicorn.run(app, host=host, port=port, reload=reload, workers=workers if workers > 1 else None)


def _init_tracing(exporter: str, config: Dict[str, Any]):
    """Initialize OpenTelemetry tracing (lazy import)."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        
        resource = Resource.create({
            "service.name": config.get("service_name", "praisonai-recipe"),
            "service.version": _get_version(),
        })
        
        provider = TracerProvider(resource=resource)
        
        if exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            endpoint = config.get("otlp_endpoint", "http://localhost:4317")
            span_exporter = OTLPSpanExporter(endpoint=endpoint)
        elif exporter == "jaeger":
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter
            span_exporter = JaegerExporter(
                agent_host_name=config.get("jaeger_host", "localhost"),
                agent_port=config.get("jaeger_port", 6831),
            )
        elif exporter == "zipkin":
            from opentelemetry.exporter.zipkin.json import ZipkinExporter
            span_exporter = ZipkinExporter(
                endpoint=config.get("zipkin_endpoint", "http://localhost:9411/api/v2/spans")
            )
        else:
            return  # Unknown exporter
        
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(provider)
        
    except ImportError:
        import warnings
        warnings.warn(
            f"OpenTelemetry exporter '{exporter}' requested but dependencies not installed. "
            "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp"
        )


def _get_version() -> str:
    """Get PraisonAI version."""
    try:
        from praisonai.version import __version__
        return __version__
    except ImportError:
        return "unknown"
