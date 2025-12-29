#!/usr/bin/env python3
"""
PraisonAI Recipe Server Advanced Features Example

Demonstrates:
1. Rate limiting
2. Request size limits
3. Metrics endpoint
4. Admin reload endpoint
5. OpenAPI specification
6. Workers configuration
7. OpenTelemetry tracing

Prerequisites:
- pip install praisonai[serve]
- Set OPENAI_API_KEY environment variable

Usage:
    # Run this example
    python recipe_serve_features.py
"""

import json
import os
import urllib.request
import urllib.error

# Configuration
SERVER_URL = os.environ.get("PRAISONAI_ENDPOINTS_URL", "http://localhost:8765")
API_KEY = os.environ.get("PRAISONAI_API_KEY", "test-api-key")


def make_request(method: str, path: str, data: dict = None, headers: dict = None) -> dict:
    """Make HTTP request to server."""
    url = f"{SERVER_URL}{path}"
    default_headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }
    if headers:
        default_headers.update(headers)
    
    body = json.dumps(data).encode() if data else None
    
    try:
        req = urllib.request.Request(url, data=body, headers=default_headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as response:
            return {
                "status": response.status,
                "data": json.loads(response.read().decode()),
                "headers": dict(response.headers)
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            error_data = json.loads(body)
        except json.JSONDecodeError:
            error_data = {"raw": body}
        return {
            "status": e.code,
            "error": error_data,
            "headers": dict(e.headers) if hasattr(e, 'headers') else {}
        }
    except urllib.error.URLError as e:
        return {"status": 0, "error": str(e.reason)}


def test_health():
    """Test health endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Health Check")
    print("=" * 60)
    
    result = make_request("GET", "/health")
    
    if result.get("status") == 200:
        data = result["data"]
        print("✓ Server healthy")
        print(f"  Service: {data.get('service')}")
        print(f"  Version: {data.get('version')}")
        return True
    else:
        print(f"✗ Server unhealthy: {result.get('error')}")
        return False


def test_openapi():
    """Test OpenAPI specification endpoint."""
    print("\n" + "=" * 60)
    print("TEST: OpenAPI Specification")
    print("=" * 60)
    
    result = make_request("GET", "/openapi.json")
    
    if result.get("status") == 200:
        spec = result["data"]
        print("✓ OpenAPI spec available")
        print(f"  Version: {spec.get('openapi')}")
        print(f"  Title: {spec.get('info', {}).get('title')}")
        print(f"  Paths: {list(spec.get('paths', {}).keys())[:5]}...")
        return True
    else:
        print(f"✗ OpenAPI not available: {result.get('error')}")
        return False


def test_metrics():
    """Test metrics endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Metrics Endpoint")
    print("=" * 60)
    
    result = make_request("GET", "/metrics")
    
    if result.get("status") == 200:
        # Metrics returns plain text, not JSON
        print("✓ Metrics endpoint available")
        print("  (Prometheus format)")
        return True
    elif result.get("status") == 404:
        print("⚠ Metrics endpoint not enabled")
        print("  Enable with: --enable_metrics")
        return True  # Not a failure, just not enabled
    else:
        print(f"✗ Metrics error: {result.get('error')}")
        return False


def test_admin_reload():
    """Test admin reload endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Admin Reload Endpoint")
    print("=" * 60)
    
    result = make_request("POST", "/admin/reload")
    
    if result.get("status") == 200:
        data = result["data"]
        print("✓ Admin reload successful")
        print(f"  Status: {data.get('status')}")
        print(f"  Timestamp: {data.get('timestamp')}")
        return True
    elif result.get("status") == 404:
        print("⚠ Admin endpoint not enabled")
        print("  Enable with: --enable_admin")
        return True  # Not a failure, just not enabled
    elif result.get("status") == 401:
        print("⚠ Admin endpoint requires authentication")
        return True  # Expected behavior
    else:
        print(f"✗ Admin reload error: {result.get('error')}")
        return False


def test_rate_limiting():
    """Test rate limiting."""
    print("\n" + "=" * 60)
    print("TEST: Rate Limiting")
    print("=" * 60)
    
    # Make rapid requests
    rate_limited = False
    retry_after = None
    
    for i in range(20):
        result = make_request("GET", "/v1/recipes")
        
        if result.get("status") == 429:
            rate_limited = True
            retry_after = result.get("headers", {}).get("Retry-After")
            error = result.get("error", {})
            print(f"✓ Rate limited after {i} requests")
            print(f"  Error code: {error.get('error', {}).get('code')}")
            print(f"  Retry-After: {retry_after}")
            break
    
    if not rate_limited:
        print("⚠ Rate limiting not triggered (may not be enabled)")
        print("  Enable with: --rate_limit 10")
    
    return True


def test_request_size_limit():
    """Test request size limit."""
    print("\n" + "=" * 60)
    print("TEST: Request Size Limit")
    print("=" * 60)
    
    # Create a large payload
    large_data = {
        "recipe": "test",
        "input": {"data": "x" * 100000}  # ~100KB
    }
    
    result = make_request("POST", "/v1/recipes/run", large_data)
    
    if result.get("status") == 413:
        error = result.get("error", {})
        print("✓ Request size limit enforced")
        print(f"  Error code: {error.get('error', {}).get('code')}")
        return True
    elif result.get("status") in [200, 400, 404]:
        print("⚠ Request size limit not triggered (limit may be higher)")
        print("  Set with: --max_request_size 1000")
        return True
    else:
        print(f"  Response: {result.get('status')} - {result.get('error')}")
        return True


def test_list_recipes():
    """Test listing recipes."""
    print("\n" + "=" * 60)
    print("TEST: List Recipes")
    print("=" * 60)
    
    result = make_request("GET", "/v1/recipes")
    
    if result.get("status") == 200:
        recipes = result["data"].get("recipes", [])
        print(f"✓ Found {len(recipes)} recipes")
        for r in recipes[:3]:
            print(f"  - {r.get('name')} ({r.get('version', 'unknown')})")
        if len(recipes) > 3:
            print(f"  ... and {len(recipes) - 3} more")
        return True
    elif result.get("status") == 401:
        print("⚠ Authentication required")
        return True
    else:
        print(f"✗ Error: {result.get('error')}")
        return False


def demonstrate_programmatic_usage():
    """Demonstrate programmatic server configuration."""
    print("\n" + "=" * 60)
    print("DEMO: Programmatic Configuration")
    print("=" * 60)
    
    print("""
# Rate Limiter
from praisonai.recipe.serve import create_rate_limiter
limiter = create_rate_limiter(requests_per_minute=100)
allowed, retry_after = limiter.check("client-id")

# Metrics Collector
from praisonai.recipe.serve import MetricsCollector
metrics = MetricsCollector()
metrics.record_request("/health", "GET", 200, 0.01)
print(metrics.get_prometheus_metrics())

# OpenAPI Spec
from praisonai.recipe.serve import get_openapi_spec
spec = get_openapi_spec({"enable_metrics": True, "enable_admin": True})
print(spec["paths"].keys())

# Template Search Paths
from praisonai.recipe.core import get_template_search_paths
paths = get_template_search_paths()
print(f"Searching {len(paths)} paths for recipes")

# Reload Registry
from praisonai.recipe.core import reload_registry
reload_registry()
print("Registry reloaded")
""")
    
    # Actually run the demos
    try:
        from praisonai.recipe.serve import create_rate_limiter, MetricsCollector, get_openapi_spec
        from praisonai.recipe.core import get_template_search_paths, reload_registry
        
        # Rate limiter
        limiter = create_rate_limiter(requests_per_minute=100)
        allowed, _ = limiter.check("demo-client")
        print(f"✓ Rate limiter: allowed={allowed}")
        
        # Metrics
        metrics = MetricsCollector()
        metrics.record_request("/demo", "GET", 200, 0.01)
        prom = metrics.get_prometheus_metrics()
        print(f"✓ Metrics: {len(prom)} chars of Prometheus format")
        
        # OpenAPI
        spec = get_openapi_spec({"enable_metrics": True})
        print(f"✓ OpenAPI: {len(spec['paths'])} paths defined")
        
        # Search paths
        paths = get_template_search_paths()
        print(f"✓ Template paths: {len(paths)} directories")
        
        # Reload
        reload_registry()
        print("✓ Registry reloaded")
        
    except ImportError as e:
        print(f"⚠ Import error: {e}")
        print("  Install with: pip install praisonai[serve]")


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Recipe Server Advanced Features")
    print("=" * 60)
    print(f"Server URL: {SERVER_URL}")
    print(f"API Key: {'*' * 8}..." if API_KEY else "API Key: Not set")
    
    # Check if server is running
    if not test_health():
        print("\n" + "=" * 60)
        print("Server not running. Start it with:")
        print("=" * 60)
        print(f"""
# Basic start
praisonai recipe serve

# With all features enabled
export PRAISONAI_API_KEY={API_KEY}
praisonai recipe serve \\
  --auth api-key \\
  --rate_limit 100 \\
  --enable_metrics \\
  --enable_admin \\
  --workers 2
""")
        # Still demonstrate programmatic usage
        demonstrate_programmatic_usage()
        return
    
    # Run all tests
    test_openapi()
    test_metrics()
    test_admin_reload()
    test_rate_limiting()
    test_request_size_limit()
    test_list_recipes()
    
    # Demonstrate programmatic usage
    demonstrate_programmatic_usage()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
