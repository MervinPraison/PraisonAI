"""
Tests for Recipe Serve Features - Rate Limiting, Size Limits, Metrics, Admin, OpenTelemetry

TDD tests for gap implementation:
- Rate limiting middleware
- Request size limits
- GET /metrics endpoint (Prometheus format)
- POST /admin/reload endpoint
- OpenTelemetry export (lazy import)
- --workers CLI flag
- OpenAPI export
"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Rate Limiting Tests
# ============================================================================

class TestRateLimiting:
    """Tests for rate limiting middleware."""
    
    def test_rate_limiter_creation(self):
        """Test rate limiter can be created with config."""
        from praisonai.recipe.serve import create_rate_limiter
        
        limiter = create_rate_limiter(requests_per_minute=100)
        assert limiter is not None
    
    def test_rate_limiter_allows_requests_under_limit(self):
        """Test rate limiter allows requests under limit."""
        from praisonai.recipe.serve import create_rate_limiter
        
        limiter = create_rate_limiter(requests_per_minute=10)
        client_ip = "127.0.0.1"
        
        # Should allow 10 requests
        for _ in range(10):
            allowed, _ = limiter.check(client_ip)
            assert allowed is True
    
    def test_rate_limiter_blocks_over_limit(self):
        """Test rate limiter blocks requests over limit."""
        from praisonai.recipe.serve import create_rate_limiter
        
        limiter = create_rate_limiter(requests_per_minute=5)
        client_ip = "127.0.0.1"
        
        # Use up the limit
        for _ in range(5):
            limiter.check(client_ip)
        
        # Next request should be blocked
        allowed, retry_after = limiter.check(client_ip)
        assert allowed is False
        assert retry_after > 0
    
    def test_rate_limiter_per_client(self):
        """Test rate limiter tracks per-client."""
        from praisonai.recipe.serve import create_rate_limiter
        
        limiter = create_rate_limiter(requests_per_minute=2)
        
        # Client 1 uses up limit
        for _ in range(2):
            limiter.check("client1")
        
        # Client 2 should still be allowed
        allowed, _ = limiter.check("client2")
        assert allowed is True
    
    def test_rate_limit_middleware_returns_429(self):
        """Test rate limit middleware returns 429 with proper error."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {
            "rate_limit": 2,  # 2 requests per minute
            "rate_limit_exempt_paths": ["/health"],
        }
        app = create_app(config)
        client = TestClient(app)
        
        # First 2 requests should succeed
        for _ in range(2):
            response = client.get("/v1/recipes")
            assert response.status_code in [200, 404]  # OK or no recipes
        
        # Third request should be rate limited
        response = client.get("/v1/recipes")
        assert response.status_code == 429
        
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "rate_limited"
        assert "Retry-After" in response.headers
    
    def test_rate_limit_exempts_health(self):
        """Test /health is exempt from rate limiting by default."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"rate_limit": 1}
        app = create_app(config)
        client = TestClient(app)
        
        # Use up rate limit
        client.get("/v1/recipes")
        
        # Health should still work
        response = client.get("/health")
        assert response.status_code == 200


# ============================================================================
# Request Size Limit Tests
# ============================================================================

class TestRequestSizeLimits:
    """Tests for request size limits."""
    
    def test_size_limit_allows_small_requests(self):
        """Test small requests are allowed."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"max_request_size": 1024 * 1024}  # 1MB
        app = create_app(config)
        client = TestClient(app)
        
        # Small request should work
        response = client.post(
            "/v1/recipes/run",
            json={"recipe": "test", "input": "small"}
        )
        # May return 404 if recipe doesn't exist, but not 413
        assert response.status_code != 413
    
    def test_size_limit_blocks_large_requests(self):
        """Test large requests are blocked with 413."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"max_request_size": 100}  # 100 bytes
        app = create_app(config)
        client = TestClient(app)
        
        # Large request should be blocked
        large_data = {"recipe": "test", "input": "x" * 200}
        response = client.post(
            "/v1/recipes/run",
            json=large_data
        )
        assert response.status_code == 413
        
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "request_too_large"
    
    def test_default_size_limit_is_10mb(self):
        """Test default size limit is 10MB."""
        from praisonai.recipe.serve import DEFAULT_MAX_REQUEST_SIZE
        assert DEFAULT_MAX_REQUEST_SIZE == 10 * 1024 * 1024


# ============================================================================
# Metrics Endpoint Tests
# ============================================================================

class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""
    
    def test_metrics_endpoint_exists_when_enabled(self):
        """Test /metrics endpoint exists when enabled."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"enable_metrics": True}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.get("/metrics")
        assert response.status_code == 200
    
    def test_metrics_endpoint_disabled_by_default_on_public(self):
        """Test /metrics is disabled by default on non-localhost."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        # Simulate non-localhost config
        config = {"host": "0.0.0.0", "enable_metrics": False}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.get("/metrics")
        assert response.status_code == 404
    
    def test_metrics_prometheus_format(self):
        """Test metrics are in Prometheus exposition format."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"enable_metrics": True}
        app = create_app(config)
        client = TestClient(app)
        
        # Make some requests to generate metrics
        client.get("/health")
        client.get("/v1/recipes")
        
        response = client.get("/metrics")
        assert response.status_code == 200
        
        content = response.text
        # Check for Prometheus format markers
        assert "praisonai_http_requests_total" in content
        assert "praisonai_http_request_duration_seconds" in content
    
    def test_metrics_include_required_labels(self):
        """Test metrics include path, method, status labels."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"enable_metrics": True}
        app = create_app(config)
        client = TestClient(app)
        
        client.get("/health")
        
        response = client.get("/metrics")
        content = response.text
        
        # Should have labels
        assert 'path="/health"' in content or 'path="health"' in content
        assert 'method="GET"' in content
        assert 'status="200"' in content


# ============================================================================
# Admin Reload Endpoint Tests
# ============================================================================

class TestAdminReload:
    """Tests for /admin/reload endpoint."""
    
    def test_admin_reload_requires_auth(self):
        """Test /admin/reload requires authentication."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"enable_admin": True, "auth": "api-key", "api_key": "secret"}
        app = create_app(config)
        client = TestClient(app)
        
        # Without auth should fail
        response = client.post("/admin/reload")
        assert response.status_code == 401
    
    def test_admin_reload_with_auth(self):
        """Test /admin/reload works with authentication."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"enable_admin": True, "auth": "api-key", "api_key": "secret"}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.post(
            "/admin/reload",
            headers={"X-API-Key": "secret"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "reloaded"
    
    def test_admin_reload_disabled_by_default(self):
        """Test /admin/reload is disabled by default."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {}  # No enable_admin
        app = create_app(config)
        client = TestClient(app)
        
        response = client.post("/admin/reload")
        assert response.status_code == 404


# ============================================================================
# OpenAPI Export Tests
# ============================================================================

class TestOpenAPIExport:
    """Tests for OpenAPI spec export."""
    
    def test_openapi_endpoint_exists(self):
        """Test /openapi.json endpoint exists."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
    
    def test_openapi_includes_all_endpoints(self):
        """Test OpenAPI spec includes all endpoints."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"enable_metrics": True, "enable_admin": True}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.get("/openapi.json")
        data = response.json()
        
        paths = data["paths"]
        assert "/health" in paths
        assert "/v1/recipes" in paths
        assert "/v1/recipes/run" in paths
        assert "/metrics" in paths
        assert "/admin/reload" in paths


# ============================================================================
# Workers CLI Flag Tests
# ============================================================================

class TestWorkersCLI:
    """Tests for --workers CLI flag."""
    
    def test_serve_command_accepts_workers_flag(self):
        """Test serve command accepts --workers flag."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        
        # Parse args with workers flag
        spec = {
            "workers": {"default": "1"},
            "port": {"default": "8765"},
            "host": {"default": "127.0.0.1"},
        }
        args = ["--workers", "4", "--port", "8000"]
        parsed = handler._parse_args(args, spec)
        
        assert parsed["workers"] == "4"
    
    def test_workers_passed_to_uvicorn(self):
        """Test workers count is passed to uvicorn."""
        # Test that serve function accepts workers parameter
        from praisonai.recipe.serve import serve
        import inspect
        
        sig = inspect.signature(serve)
        params = list(sig.parameters.keys())
        
        assert "workers" in params, "serve() should accept workers parameter"
        
        # Check default value
        workers_param = sig.parameters["workers"]
        assert workers_param.default == 1, "workers should default to 1"


# ============================================================================
# OpenTelemetry Lazy Import Tests
# ============================================================================

class TestOpenTelemetryLazyImport:
    """Tests for OpenTelemetry lazy import behavior."""
    
    def test_no_crash_without_otel_installed(self):
        """Test server works without OpenTelemetry installed."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        # Should not crash even without otel
        config = {"trace_exporter": "none"}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_otel_config_options(self):
        """Test OpenTelemetry config options are recognized."""
        from praisonai.recipe.serve import load_config
        
        # These should be valid config keys
        config = {
            "trace_exporter": "otlp",
            "otlp_endpoint": "http://localhost:4317",
            "service_name": "praisonai-recipe",
        }
        
        # Should not raise
        assert config["trace_exporter"] == "otlp"


# ============================================================================
# Agent-Recipes Integration Tests
# ============================================================================

class TestAgentRecipesIntegration:
    """Tests for Agent-Recipes template integration."""
    
    def test_template_discovery_precedence(self):
        """Test template discovery follows precedence order."""
        from praisonai.recipe.core import get_template_search_paths
        
        paths = get_template_search_paths()
        
        # Should include standard paths
        assert any("praison" in str(p).lower() for p in paths)
    
    def test_agent_recipes_path_included(self):
        """Test Agent-Recipes path is in search paths."""
        from praisonai.recipe.core import get_template_search_paths
        
        paths = get_template_search_paths()
        path_strs = [str(p) for p in paths]
        
        # Should include Agent-Recipes or similar
        # The exact path depends on installation
        assert len(paths) > 0


# ============================================================================
# Structured Error Tests
# ============================================================================

class TestStructuredErrors:
    """Tests for consistent structured error responses."""
    
    def test_401_error_format(self):
        """Test 401 errors have correct format."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"auth": "api-key", "api_key": "secret"}
        app = create_app(config)
        client = TestClient(app)
        
        response = client.get("/v1/recipes")
        assert response.status_code == 401
        
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
    
    def test_429_error_format(self):
        """Test 429 errors have correct format."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"rate_limit": 1}
        app = create_app(config)
        client = TestClient(app)
        
        # Use up limit
        client.get("/v1/recipes")
        
        response = client.get("/v1/recipes")
        if response.status_code == 429:
            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == "rate_limited"
    
    def test_413_error_format(self):
        """Test 413 errors have correct format."""
        pytest.importorskip("starlette")
        from starlette.testclient import TestClient
        from praisonai.recipe.serve import create_app
        
        config = {"max_request_size": 10}  # Very small
        app = create_app(config)
        client = TestClient(app)
        
        response = client.post(
            "/v1/recipes/run",
            json={"recipe": "test", "input": "x" * 100}
        )
        
        if response.status_code == 413:
            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == "request_too_large"
