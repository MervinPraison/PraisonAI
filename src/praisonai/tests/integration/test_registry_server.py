"""
Integration tests for recipe registry HTTP server.

Tests the full HTTP server with real requests.
"""

import json
import tarfile
import pytest

from praisonai.recipe.server import RegistryServer, create_wsgi_app


class TestRegistryServer:
    """Test RegistryServer class."""
    
    @pytest.fixture
    def registry_path(self, tmp_path):
        """Create temporary registry path."""
        return tmp_path / "registry"
    
    @pytest.fixture
    def server(self, registry_path):
        """Create a RegistryServer instance."""
        return RegistryServer(registry_path=registry_path)
    
    @pytest.fixture
    def sample_bundle(self, tmp_path):
        """Create a sample .praison bundle."""
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        
        manifest = {
            "name": "test-recipe",
            "version": "1.0.0",
            "description": "A test recipe",
            "tags": ["test", "sample"],
            "author": "test",
            "files": ["recipe.yaml"],
        }
        
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest))
        (bundle_dir / "recipe.yaml").write_text("name: test")
        
        bundle_path = tmp_path / "test-recipe-1.0.0.praison"
        with tarfile.open(bundle_path, "w:gz") as tar:
            tar.add(bundle_dir / "manifest.json", arcname="manifest.json")
            tar.add(bundle_dir / "recipe.yaml", arcname="recipe.yaml")
        
        return bundle_path
    
    def test_health_endpoint(self, server):
        """Test GET /healthz."""
        status, headers, body = server.handle_request(
            method="GET",
            path="/healthz",
            headers={},
            body=b"",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["ok"] is True
        assert data["status"] == "healthy"
    
    def test_list_recipes_empty(self, server):
        """Test GET /v1/recipes with empty registry."""
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes",
            headers={},
            body=b"",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["ok"] is True
        assert data["recipes"] == []
        assert data["total"] == 0
    
    def test_list_recipes_with_data(self, server, sample_bundle):
        """Test GET /v1/recipes with recipes."""
        # First publish a recipe
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes",
            headers={},
            body=b"",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["total"] == 1
        assert data["recipes"][0]["name"] == "test-recipe"
    
    def test_get_recipe_info(self, server, sample_bundle):
        """Test GET /v1/recipes/{name}."""
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes/test-recipe",
            headers={},
            body=b"",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["name"] == "test-recipe"
        assert "1.0.0" in data["versions"]
    
    def test_get_recipe_not_found(self, server):
        """Test GET /v1/recipes/{name} for non-existent recipe."""
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes/nonexistent",
            headers={},
            body=b"",
        )
        
        assert status == 404
        data = json.loads(body)
        assert data["ok"] is False
    
    def test_get_version_info(self, server, sample_bundle):
        """Test GET /v1/recipes/{name}/{version}."""
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes/test-recipe/1.0.0",
            headers={},
            body=b"",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["name"] == "test-recipe"
        assert data["version"] == "1.0.0"
    
    def test_download_bundle(self, server, sample_bundle):
        """Test GET /v1/recipes/{name}/{version}/download."""
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes/test-recipe/1.0.0/download",
            headers={},
            body=b"",
        )
        
        assert status == 200
        assert headers["Content-Type"] == "application/gzip"
        assert "X-Checksum-SHA256" in headers
        assert len(body) > 0
    
    def test_download_with_etag(self, server, sample_bundle):
        """Test ETag caching for downloads."""
        server.registry.publish(sample_bundle)
        
        # First request
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes/test-recipe/1.0.0/download",
            headers={},
            body=b"",
        )
        
        assert status == 200
        etag = headers.get("ETag")
        assert etag is not None
        
        # Second request with If-None-Match
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/recipes/test-recipe/1.0.0/download",
            headers={"If-None-Match": etag},
            body=b"",
        )
        
        assert status == 304  # Not Modified
    
    def test_search_recipes(self, server, sample_bundle):
        """Test GET /v1/search."""
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/search",
            headers={},
            body=b"",
            query_string="q=test",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["ok"] is True
        assert len(data["results"]) == 1
    
    def test_search_no_query(self, server):
        """Test GET /v1/search without query."""
        status, headers, body = server.handle_request(
            method="GET",
            path="/v1/search",
            headers={},
            body=b"",
        )
        
        assert status == 400
        data = json.loads(body)
        assert data["ok"] is False
    
    def test_publish_requires_auth(self, registry_path, sample_bundle):
        """Test POST /v1/recipes/{name}/{version} requires auth when token set."""
        server = RegistryServer(registry_path=registry_path, token="secret")
        
        status, headers, body = server.handle_request(
            method="POST",
            path="/v1/recipes/test-recipe/1.0.0",
            headers={"Content-Type": "multipart/form-data; boundary=----test"},
            body=b"",
        )
        
        assert status == 401
    
    def test_publish_with_auth(self, registry_path, sample_bundle):
        """Test POST /v1/recipes/{name}/{version} with valid auth."""
        server = RegistryServer(registry_path=registry_path, token="secret")
        
        # Build multipart body
        boundary = "----test"
        bundle_content = sample_bundle.read_bytes()
        
        body_parts = [
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="force"',
            b"",
            b"false",
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="bundle"; filename="test.praison"'.encode(),
            b"Content-Type: application/gzip",
            b"",
            bundle_content,
            f"--{boundary}--".encode(),
            b"",
        ]
        body = b"\r\n".join(body_parts)
        
        status, headers, body_response = server.handle_request(
            method="POST",
            path="/v1/recipes/test-recipe/1.0.0",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": "Bearer secret",
            },
            body=body,
        )
        
        assert status == 201
        data = json.loads(body_response)
        assert data["ok"] is True
        assert data["name"] == "test-recipe"
    
    def test_delete_requires_auth(self, registry_path, sample_bundle):
        """Test DELETE /v1/recipes/{name}/{version} requires auth."""
        server = RegistryServer(registry_path=registry_path, token="secret")
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="DELETE",
            path="/v1/recipes/test-recipe/1.0.0",
            headers={},
            body=b"",
        )
        
        assert status == 401
    
    def test_delete_with_auth(self, registry_path, sample_bundle):
        """Test DELETE /v1/recipes/{name}/{version} with valid auth."""
        server = RegistryServer(registry_path=registry_path, token="secret")
        server.registry.publish(sample_bundle)
        
        status, headers, body = server.handle_request(
            method="DELETE",
            path="/v1/recipes/test-recipe/1.0.0",
            headers={"Authorization": "Bearer secret"},
            body=b"",
        )
        
        assert status == 200
        data = json.loads(body)
        assert data["ok"] is True
    
    def test_read_only_mode(self, registry_path, sample_bundle):
        """Test read-only mode blocks writes."""
        server = RegistryServer(registry_path=registry_path, read_only=True)
        
        status, headers, body = server.handle_request(
            method="POST",
            path="/v1/recipes/test-recipe/1.0.0",
            headers={"Content-Type": "multipart/form-data; boundary=----test"},
            body=b"",
        )
        
        assert status == 403
        data = json.loads(body)
        assert "read-only" in data["error"].lower()
    
    def test_not_found_route(self, server):
        """Test 404 for unknown routes."""
        status, headers, body = server.handle_request(
            method="GET",
            path="/unknown",
            headers={},
            body=b"",
        )
        
        assert status == 404


class TestWSGIApp:
    """Test WSGI application."""
    
    @pytest.fixture
    def app(self, tmp_path):
        """Create WSGI app."""
        return create_wsgi_app(registry_path=tmp_path / "registry")
    
    def test_wsgi_health(self, app):
        """Test WSGI app health endpoint."""
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/healthz",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": "0",
            "wsgi.input": MockInput(b""),
        }
        
        response_started = []
        def start_response(status, headers):
            response_started.append((status, headers))
        
        result = list(app(environ, start_response))
        
        assert len(response_started) == 1
        assert "200" in response_started[0][0]
        
        body = b"".join(result)
        data = json.loads(body)
        assert data["ok"] is True


class MockInput:
    """Mock WSGI input stream."""
    
    def __init__(self, data):
        self.data = data
        self.pos = 0
    
    def read(self, size=-1):
        if size < 0:
            result = self.data[self.pos:]
            self.pos = len(self.data)
        else:
            result = self.data[self.pos:self.pos + size]
            self.pos += size
        return result
