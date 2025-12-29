"""
Recipe Registry HTTP Server

Provides a local HTTP server for recipe registry operations.
Supports:
- GET /healthz - Health check
- GET /v1/recipes - List recipes (pagination)
- GET /v1/recipes/{name} - Get recipe info (all versions)
- GET /v1/recipes/{name}/{version} - Get specific version info
- GET /v1/recipes/{name}/{version}/download - Download bundle
- POST /v1/recipes/{name}/{version} - Publish bundle (multipart)
- DELETE /v1/recipes/{name}/{version} - Delete version
- GET /v1/search?q=... - Search recipes

Usage:
    from praisonai.recipe.server import create_app, run_server
    
    # Run server
    run_server(host="127.0.0.1", port=7777)
    
    # Or get ASGI app for custom deployment
    app = create_app(registry_path="~/.praison/registry")
"""

import json
import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote

from .registry import (
    LocalRegistry,
    RegistryError,
    RecipeNotFoundError,
    RecipeExistsError,
    RegistryAuthError,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_REGISTRY_PORT,
    _calculate_checksum,
    _get_timestamp,
)


class RegistryServer:
    """
    Simple HTTP server for recipe registry.
    
    Uses only stdlib for minimal dependencies.
    For production, consider using with uvicorn/gunicorn.
    """
    
    def __init__(
        self,
        registry_path: Optional[Path] = None,
        token: Optional[str] = None,
        read_only: bool = False,
    ):
        """
        Initialize registry server.
        
        Args:
            registry_path: Path to registry directory
            token: Required token for write operations (optional)
            read_only: If True, disable all write operations
        """
        self.registry = LocalRegistry(registry_path)
        self.token = token or os.environ.get("PRAISONAI_REGISTRY_TOKEN")
        self.read_only = read_only
        self._routes: List[Tuple[str, str, Callable]] = []
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup URL routes."""
        self._routes = [
            ("GET", r"^/healthz$", self._handle_health),
            ("GET", r"^/v1/recipes$", self._handle_list_recipes),
            ("GET", r"^/v1/recipes/([^/]+)$", self._handle_get_recipe),
            ("GET", r"^/v1/recipes/([^/]+)/([^/]+)$", self._handle_get_version),
            ("GET", r"^/v1/recipes/([^/]+)/([^/]+)/download$", self._handle_download),
            ("POST", r"^/v1/recipes/([^/]+)/([^/]+)$", self._handle_publish),
            ("DELETE", r"^/v1/recipes/([^/]+)/([^/]+)$", self._handle_delete_version),
            ("DELETE", r"^/v1/recipes/([^/]+)$", self._handle_delete_recipe),
            ("GET", r"^/v1/search$", self._handle_search),
        ]
    
    def _check_auth(self, headers: Dict[str, str]) -> bool:
        """Check if request is authorized for write operations."""
        if not self.token:
            return True
        
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == self.token
        return False
    
    def _json_response(
        self,
        data: Any,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Create JSON response."""
        resp_headers = {
            "Content-Type": "application/json",
            "X-Registry-Version": "1.0",
        }
        if headers:
            resp_headers.update(headers)
        
        body = json.dumps(data, indent=2).encode("utf-8")
        return status, resp_headers, body
    
    def _error_response(
        self,
        message: str,
        status: int = 400,
        code: Optional[str] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Create error response."""
        return self._json_response({
            "ok": False,
            "error": message,
            "code": code or "error",
        }, status=status)
    
    def _file_response(
        self,
        file_path: Path,
        filename: str,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Create file download response."""
        with open(file_path, "rb") as f:
            content = f.read()
        
        checksum = hashlib.sha256(content).hexdigest()
        
        headers = {
            "Content-Type": "application/gzip",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
            "ETag": f'"{checksum[:16]}"',
            "X-Checksum-SHA256": checksum,
        }
        
        return 200, headers, content
    
    def _parse_multipart(
        self,
        body: bytes,
        content_type: str,
    ) -> Dict[str, Any]:
        """Parse multipart form data."""
        # Extract boundary
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[9:].strip('"')
                break
        
        if not boundary:
            raise ValueError("Missing boundary in multipart data")
        
        result = {"fields": {}, "files": {}}
        boundary_bytes = f"--{boundary}".encode()
        
        parts = body.split(boundary_bytes)
        for part in parts[1:]:  # Skip preamble
            if part.startswith(b"--"):
                break  # End marker
            
            # Split headers and content
            if b"\r\n\r\n" in part:
                header_section, content = part.split(b"\r\n\r\n", 1)
            else:
                continue
            
            # Parse headers
            headers = {}
            for line in header_section.decode("utf-8", errors="ignore").split("\r\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            
            # Get field name and filename
            disposition = headers.get("content-disposition", "")
            name = None
            filename = None
            
            for item in disposition.split(";"):
                item = item.strip()
                if item.startswith("name="):
                    name = item[5:].strip('"')
                elif item.startswith("filename="):
                    filename = item[9:].strip('"')
            
            if not name:
                continue
            
            # Remove trailing \r\n
            content = content.rstrip(b"\r\n")
            
            if filename:
                result["files"][name] = {
                    "filename": filename,
                    "content": content,
                    "content_type": headers.get("content-type", "application/octet-stream"),
                }
            else:
                result["fields"][name] = content.decode("utf-8", errors="ignore")
        
        return result
    
    def handle_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: bytes,
        query_string: str = "",
    ) -> Tuple[int, Dict[str, str], bytes]:
        """
        Handle HTTP request.
        
        Args:
            method: HTTP method
            path: URL path
            headers: Request headers
            body: Request body
            query_string: Query string
            
        Returns:
            Tuple of (status_code, headers, body)
        """
        # Parse query string
        query = parse_qs(query_string)
        
        # Find matching route
        for route_method, pattern, handler in self._routes:
            if method != route_method:
                continue
            
            match = re.match(pattern, path)
            if match:
                try:
                    return handler(
                        headers=headers,
                        body=body,
                        query=query,
                        path_params=match.groups(),
                    )
                except RecipeNotFoundError as e:
                    return self._error_response(str(e), status=404, code="not_found")
                except RecipeExistsError as e:
                    return self._error_response(str(e), status=409, code="conflict")
                except RegistryAuthError as e:
                    return self._error_response(str(e), status=401, code="auth_error")
                except RegistryError as e:
                    return self._error_response(str(e), status=400, code="registry_error")
                except Exception as e:
                    return self._error_response(f"Internal error: {e}", status=500, code="internal_error")
        
        return self._error_response("Not found", status=404, code="not_found")
    
    def _handle_health(self, **kwargs) -> Tuple[int, Dict[str, str], bytes]:
        """Handle GET /healthz."""
        return self._json_response({
            "ok": True,
            "status": "healthy",
            "timestamp": _get_timestamp(),
            "read_only": self.read_only,
            "auth_required": bool(self.token),
        })
    
    def _handle_list_recipes(
        self,
        query: Dict[str, List[str]],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle GET /v1/recipes."""
        page = int(query.get("page", ["1"])[0])
        per_page = min(int(query.get("per_page", ["50"])[0]), 100)
        tags = query.get("tags", [""])[0].split(",") if query.get("tags") else None
        
        if tags and tags[0] == "":
            tags = None
        
        recipes = self.registry.list_recipes(tags=tags)
        
        # Paginate
        start = (page - 1) * per_page
        end = start + per_page
        paginated = recipes[start:end]
        
        return self._json_response({
            "ok": True,
            "recipes": paginated,
            "total": len(recipes),
            "page": page,
            "per_page": per_page,
            "has_more": end < len(recipes),
        })
    
    def _handle_get_recipe(
        self,
        path_params: Tuple[str, ...],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle GET /v1/recipes/{name}."""
        name = unquote(path_params[0])
        
        versions = self.registry.get_versions(name)
        info = self.registry.get_info(name)
        
        return self._json_response({
            "ok": True,
            "name": name,
            "versions": versions,
            "latest": info.get("version"),
            "description": info.get("description", ""),
            "tags": info.get("tags", []),
        })
    
    def _handle_get_version(
        self,
        path_params: Tuple[str, ...],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle GET /v1/recipes/{name}/{version}."""
        name = unquote(path_params[0])
        version = unquote(path_params[1])
        
        info = self.registry.get_info(name, version)
        
        return self._json_response({
            "ok": True,
            **info,
        })
    
    def _handle_download(
        self,
        path_params: Tuple[str, ...],
        headers: Dict[str, str],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle GET /v1/recipes/{name}/{version}/download."""
        name = unquote(path_params[0])
        version = unquote(path_params[1])
        
        # Get bundle path
        bundle_name = f"{name}-{version}.praison"
        bundle_path = self.registry.recipes_path / name / version / bundle_name
        
        if not bundle_path.exists():
            raise RecipeNotFoundError(f"Bundle not found: {name}@{version}")
        
        # Check ETag for caching
        checksum = _calculate_checksum(bundle_path)
        etag = f'"{checksum[:16]}"'
        
        if_none_match = headers.get("If-None-Match", "")
        if if_none_match == etag:
            return 304, {"ETag": etag}, b""
        
        return self._file_response(bundle_path, bundle_name)
    
    def _handle_publish(
        self,
        path_params: Tuple[str, ...],
        headers: Dict[str, str],
        body: bytes,
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle POST /v1/recipes/{name}/{version}."""
        if self.read_only:
            return self._error_response("Registry is read-only", status=403, code="read_only")
        
        if not self._check_auth(headers):
            return self._error_response("Authentication required", status=401, code="auth_required")
        
        name = unquote(path_params[0])
        version = unquote(path_params[1])
        
        # Parse multipart data
        content_type = headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return self._error_response("Expected multipart/form-data", status=400)
        
        try:
            data = self._parse_multipart(body, content_type)
        except ValueError as e:
            return self._error_response(f"Invalid multipart data: {e}", status=400)
        
        if "bundle" not in data["files"]:
            return self._error_response("Missing bundle file", status=400)
        
        force = data["fields"].get("force", "false").lower() == "true"
        bundle_content = data["files"]["bundle"]["content"]
        
        # Save to temp file and publish
        with tempfile.NamedTemporaryFile(suffix=".praison", delete=False) as tmp:
            tmp.write(bundle_content)
            tmp_path = Path(tmp.name)
        
        try:
            result = self.registry.publish(tmp_path, force=force)
            
            # Verify name/version match
            if result["name"] != name or result["version"] != version:
                # Rollback
                self.registry.delete(result["name"], result["version"])
                return self._error_response(
                    f"Bundle name/version ({result['name']}@{result['version']}) "
                    f"doesn't match URL ({name}@{version})",
                    status=400,
                )
            
            return self._json_response({
                "ok": True,
                **result,
            }, status=201)
        finally:
            tmp_path.unlink(missing_ok=True)
    
    def _handle_delete_version(
        self,
        path_params: Tuple[str, ...],
        headers: Dict[str, str],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle DELETE /v1/recipes/{name}/{version}."""
        if self.read_only:
            return self._error_response("Registry is read-only", status=403, code="read_only")
        
        if not self._check_auth(headers):
            return self._error_response("Authentication required", status=401, code="auth_required")
        
        name = unquote(path_params[0])
        version = unquote(path_params[1])
        
        self.registry.delete(name, version)
        
        return self._json_response({
            "ok": True,
            "deleted": f"{name}@{version}",
        })
    
    def _handle_delete_recipe(
        self,
        path_params: Tuple[str, ...],
        headers: Dict[str, str],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle DELETE /v1/recipes/{name}."""
        if self.read_only:
            return self._error_response("Registry is read-only", status=403, code="read_only")
        
        if not self._check_auth(headers):
            return self._error_response("Authentication required", status=401, code="auth_required")
        
        name = unquote(path_params[0])
        
        self.registry.delete(name)
        
        return self._json_response({
            "ok": True,
            "deleted": name,
        })
    
    def _handle_search(
        self,
        query: Dict[str, List[str]],
        **kwargs,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Handle GET /v1/search."""
        q = query.get("q", [""])[0]
        tags = query.get("tags", [""])[0].split(",") if query.get("tags") else None
        
        if tags and tags[0] == "":
            tags = None
        
        if not q:
            return self._error_response("Query parameter 'q' required", status=400)
        
        results = self.registry.search(q, tags=tags)
        
        return self._json_response({
            "ok": True,
            "query": q,
            "results": results,
            "count": len(results),
        })


def create_wsgi_app(
    registry_path: Optional[Path] = None,
    token: Optional[str] = None,
    read_only: bool = False,
) -> Callable:
    """
    Create WSGI application for the registry server.
    
    Args:
        registry_path: Path to registry directory
        token: Required token for write operations
        read_only: If True, disable write operations
        
    Returns:
        WSGI application callable
    """
    server = RegistryServer(
        registry_path=registry_path,
        token=token,
        read_only=read_only,
    )
    
    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        query_string = environ.get("QUERY_STRING", "")
        
        # Read headers
        headers = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                headers[header_name] = value
        headers["Content-Type"] = environ.get("CONTENT_TYPE", "")
        
        # Read body
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0
        
        body = environ["wsgi.input"].read(content_length) if content_length > 0 else b""
        
        # Handle request
        status_code, resp_headers, resp_body = server.handle_request(
            method=method,
            path=path,
            headers=headers,
            body=body,
            query_string=query_string,
        )
        
        # Send response
        status = f"{status_code} {'OK' if status_code < 400 else 'Error'}"
        response_headers = [(k, v) for k, v in resp_headers.items()]
        start_response(status, response_headers)
        
        return [resp_body]
    
    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = DEFAULT_REGISTRY_PORT,
    registry_path: Optional[Path] = None,
    token: Optional[str] = None,
    read_only: bool = False,
):
    """
    Run the registry server using stdlib wsgiref.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        registry_path: Path to registry directory
        token: Required token for write operations
        read_only: If True, disable write operations
    """
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    
    # Custom handler to suppress logs unless verbose
    class QuietHandler(WSGIRequestHandler):
        def log_message(self, format, *args):
            pass  # Suppress default logging
    
    app = create_wsgi_app(
        registry_path=registry_path,
        token=token,
        read_only=read_only,
    )
    
    server = make_server(host, port, app, handler_class=QuietHandler)
    
    print(f"Recipe Registry Server running on http://{host}:{port}")
    print(f"Registry path: {registry_path or DEFAULT_REGISTRY_PATH}")
    if token:
        print("Authentication: enabled (token required for writes)")
    if read_only:
        print("Mode: read-only")
    print("\nEndpoints:")
    print("  GET  /healthz                         - Health check")
    print("  GET  /v1/recipes                      - List recipes")
    print("  GET  /v1/recipes/{name}               - Get recipe info")
    print("  GET  /v1/recipes/{name}/{version}     - Get version info")
    print("  GET  /v1/recipes/{name}/{version}/download - Download bundle")
    print("  POST /v1/recipes/{name}/{version}     - Publish bundle")
    print("  DELETE /v1/recipes/{name}/{version}   - Delete version")
    print("  GET  /v1/search?q=...                 - Search recipes")
    print("\nPress Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
