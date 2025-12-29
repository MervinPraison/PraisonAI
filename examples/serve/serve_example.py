#!/usr/bin/env python3
"""
PraisonAI Recipe Server Example

This example demonstrates how to:
1. Start the recipe server with configuration
2. Use API key authentication
3. Make authenticated requests

Prerequisites:
- pip install praisonai[serve]
- Set OPENAI_API_KEY environment variable
- Set PRAISONAI_API_KEY for authentication

Usage:
    # Terminal 1: Start server with config
    praisonai recipe serve --config serve.yaml

    # Terminal 2: Run this example
    python serve_example.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

# Configuration
SERVER_URL = os.environ.get("PRAISONAI_ENDPOINTS_URL", "http://localhost:8765")
API_KEY = os.environ.get("PRAISONAI_API_KEY", "test-api-key")


def make_request(method: str, path: str, data: dict = None) -> dict:
    """Make authenticated HTTP request to server."""
    url = f"{SERVER_URL}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }
    
    body = json.dumps(data).encode() if data else None
    
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as response:
            return {"status": response.status, "data": json.loads(response.read().decode())}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"status": e.code, "error": body}
    except urllib.error.URLError as e:
        return {"status": 0, "error": str(e.reason)}


def check_health():
    """Check server health."""
    print("\n=== Health Check ===")
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


def list_recipes():
    """List available recipes."""
    print("\n=== List Recipes ===")
    result = make_request("GET", "/v1/recipes")
    
    if result.get("status") == 200:
        recipes = result["data"].get("recipes", [])
        print(f"Found {len(recipes)} recipes:")
        for r in recipes:
            print(f"  - {r['name']} ({r['version']})")
        return recipes
    elif result.get("status") == 401:
        print("✗ Authentication failed - check API key")
        return []
    else:
        print(f"✗ Error: {result.get('error')}")
        return []


def describe_recipe(name: str):
    """Get recipe details."""
    print(f"\n=== Describe Recipe: {name} ===")
    result = make_request("GET", f"/v1/recipes/{name}")
    
    if result.get("status") == 200:
        info = result["data"]
        print(f"Name: {info.get('name')}")
        print(f"Version: {info.get('version')}")
        print(f"Description: {info.get('description')}")
        return info
    else:
        print(f"✗ Error: {result.get('error')}")
        return None


def invoke_recipe(name: str, input_data: dict, dry_run: bool = True):
    """Invoke a recipe."""
    print(f"\n=== Invoke Recipe: {name} (dry_run={dry_run}) ===")
    
    result = make_request("POST", "/v1/recipes/run", {
        "recipe": name,
        "input": input_data,
        "options": {"dry_run": dry_run}
    })
    
    if result.get("status") == 200:
        data = result["data"]
        print("✓ Success")
        print(f"  Run ID: {data.get('run_id')}")
        print(f"  Status: {data.get('status')}")
        if data.get("output"):
            print(f"  Output: {json.dumps(data.get('output'), indent=2)[:200]}...")
        return data
    elif result.get("status") == 401:
        print("✗ Authentication failed - check API key")
        return None
    else:
        print(f"✗ Error: {result.get('error')}")
        return None


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Recipe Server Example")
    print("=" * 60)
    print(f"Server URL: {SERVER_URL}")
    print(f"API Key: {API_KEY[:8]}..." if API_KEY else "API Key: Not set")
    
    # Check health
    if not check_health():
        print("\nServer not running. Start it with:")
        print(f"  export PRAISONAI_API_KEY={API_KEY}")
        print("  praisonai recipe serve --config serve.yaml")
        sys.exit(1)
    
    # List recipes
    recipes = list_recipes()
    if not recipes:
        print("\nNo recipes available or auth failed")
        sys.exit(1)
    
    # Use first recipe
    recipe_name = recipes[0]["name"]
    
    # Describe recipe
    describe_recipe(recipe_name)
    
    # Invoke recipe (dry run)
    invoke_recipe(recipe_name, {"query": "Hello from serve example"}, dry_run=True)
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
