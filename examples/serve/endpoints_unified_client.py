#!/usr/bin/env python3
"""
Unified Endpoints Client Example

Demonstrates using the praisonai endpoints CLI to interact with any PraisonAI server.
Works with recipe, agents-api, mcp, a2a, a2u, and tools-mcp servers.

Usage:
    # Start any server first (e.g., unified server)
    praisonai serve unified --port 8765
    
    # Then run this example
    python endpoints_unified_client.py
    
    # Or use CLI directly:
    praisonai endpoints list
    praisonai endpoints types
    praisonai endpoints health
    praisonai endpoints discovery
"""

import json
import os
import subprocess
import sys


def run_cli(args: list) -> tuple:
    """Run praisonai endpoints CLI command."""
    cmd = ["python3", "-m", "praisonai.cli.main", "endpoints"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def main():
    print("=" * 60)
    print("PraisonAI Unified Endpoints Client Example")
    print("=" * 60)
    
    server_url = os.environ.get("PRAISONAI_ENDPOINTS_URL", "http://localhost:8765")
    print(f"Server URL: {server_url}")
    
    # 1. List provider types
    print("\n--- Provider Types ---")
    code, out, err = run_cli(["types", "--format", "json"])
    if code == 0:
        types = json.loads(out)
        print(f"Supported types: {[t['type'] for t in types]}")
    else:
        print(f"Error: {err}")
    
    # 2. Health check
    print("\n--- Health Check ---")
    code, out, err = run_cli(["health", "--url", server_url])
    if code == 0:
        print("✓ Server is healthy")
        print(out.strip())
    elif code == 8:
        print("✗ Connection error - server not running")
        print("\nStart a server first:")
        print("  praisonai serve unified --port 8765")
        print("  praisonai serve agents --file agents.yaml --port 8765")
        print("  praisonai serve a2a --port 8765")
        return 1
    else:
        print(f"✗ Health check failed: {err}")
        return 1
    
    # 3. Discovery document
    print("\n--- Discovery Document ---")
    code, out, err = run_cli(["discovery", "--url", server_url])
    if code == 0:
        try:
            discovery = json.loads(out)
            print(f"Server: {discovery.get('server_name', 'unknown')}")
            print(f"Schema version: {discovery.get('schema_version', 'unknown')}")
            providers = discovery.get('providers', [])
            print(f"Providers: {[p.get('type') for p in providers]}")
            endpoints = discovery.get('endpoints', [])
            print(f"Endpoints: {[e.get('name') for e in endpoints]}")
        except json.JSONDecodeError:
            print(out.strip())
    else:
        print(f"Discovery not available: {err}")
    
    # 4. List endpoints
    print("\n--- List Endpoints ---")
    code, out, err = run_cli(["list", "--url", server_url, "--format", "json"])
    if code == 0:
        try:
            endpoints = json.loads(out)
            if isinstance(endpoints, list):
                for ep in endpoints[:5]:  # Show first 5
                    print(f"  - {ep.get('name')}: {ep.get('description', '')[:50]}")
            else:
                print(out.strip()[:200])
        except json.JSONDecodeError:
            print(out.strip()[:200])
    else:
        print(f"List failed: {err}")
    
    # 5. Filter by type
    print("\n--- Filter by Provider Type ---")
    for ptype in ["agents-api", "a2a", "recipe"]:
        code, out, err = run_cli(["list", "--url", server_url, "--type", ptype])
        if code == 0 and out.strip():
            print(f"  {ptype}: {len(out.strip().split(chr(10)))} endpoints")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
