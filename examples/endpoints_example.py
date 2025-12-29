#!/usr/bin/env python3
"""
PraisonAI Endpoints Example

This example demonstrates how to:
1. Start the recipe server
2. Use the endpoints CLI to interact with it
3. Invoke recipes via HTTP

Prerequisites:
- pip install praisonai[serve]
- Set OPENAI_API_KEY environment variable

Usage:
    # Terminal 1: Start server
    praisonai recipe serve --port 8765

    # Terminal 2: Run this example
    python endpoints_example.py
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

# Configuration
SERVER_URL = os.environ.get("PRAISONAI_ENDPOINTS_URL", "http://localhost:8765")


def check_server_health():
    """Check if the server is running."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get("status") == "healthy"
    except Exception:
        return False


def list_endpoints():
    """List available endpoints using CLI."""
    print("\n=== Listing Endpoints (CLI) ===")
    result = subprocess.run(
        ["python", "-m", "praisonai.cli.main", "endpoints", "list", "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        recipes = json.loads(result.stdout)
        print(f"Found {len(recipes)} endpoints:")
        for r in recipes:
            print(f"  - {r['name']} ({r['version']}): {r.get('description', '')[:50]}")
        return recipes
    else:
        print(f"Error: {result.stderr}")
        return []


def describe_endpoint(name: str):
    """Describe an endpoint using CLI."""
    print(f"\n=== Describing Endpoint: {name} ===")
    result = subprocess.run(
        ["python", "-m", "praisonai.cli.main", "endpoints", "describe", name, "--url", SERVER_URL],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info = json.loads(result.stdout)
        print(f"Name: {info.get('name')}")
        print(f"Version: {info.get('version')}")
        print(f"Description: {info.get('description')}")
        return info
    else:
        print(f"Error: {result.stderr}")
        return None


def invoke_endpoint_cli(name: str, input_data: dict):
    """Invoke an endpoint using CLI."""
    print(f"\n=== Invoking Endpoint (CLI): {name} ===")
    result = subprocess.run(
        [
            "python", "-m", "praisonai.cli.main", "endpoints", "invoke", name,
            "--url", SERVER_URL,
            "--input-json", json.dumps(input_data),
            "--json",
            "--dry-run",  # Use dry-run for example
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        response = json.loads(result.stdout)
        print(f"Run ID: {response.get('run_id')}")
        print(f"Status: {response.get('status')}")
        return response
    else:
        print(f"Error: {result.stderr}")
        return None


def invoke_endpoint_http(name: str, input_data: dict):
    """Invoke an endpoint using HTTP directly."""
    print(f"\n=== Invoking Endpoint (HTTP): {name} ===")
    
    body = json.dumps({
        "recipe": name,
        "input": input_data,
        "options": {"dry_run": True},
    }).encode()
    
    req = urllib.request.Request(
        f"{SERVER_URL}/v1/recipes/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            print(f"Run ID: {data.get('run_id')}")
            print(f"Status: {data.get('status')}")
            print(f"Output: {data.get('output')}")
            return data
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode()}")
        return None


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Endpoints Example")
    print("=" * 60)
    
    # Check if server is running
    print("\n=== Checking Server Health ===")
    if not check_server_health():
        print(f"Server not running at {SERVER_URL}")
        print("\nPlease start the server first:")
        print("  praisonai recipe serve --port 8765")
        sys.exit(1)
    print("✓ Server is healthy")
    
    # List endpoints
    recipes = list_endpoints()
    if not recipes:
        print("No recipes available")
        sys.exit(1)
    
    # Use first available recipe
    recipe_name = recipes[0]["name"]
    
    # Describe endpoint
    describe_endpoint(recipe_name)
    
    # Invoke via CLI
    invoke_endpoint_cli(recipe_name, {"query": "Hello from CLI"})
    
    # Invoke via HTTP
    invoke_endpoint_http(recipe_name, {"query": "Hello from HTTP"})
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
