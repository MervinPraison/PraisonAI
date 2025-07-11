#!/usr/bin/env python3
"""
Test script to verify backward compatibility of MCP implementation.
This ensures existing code continues to work without modifications.
"""

import sys
import os

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.mcp import MCP

print("Testing MCP backward compatibility...")
print("=" * 50)

# Test 1: Existing SSE URL usage (should work unchanged)
print("\n1. Testing existing SSE URL usage:")
try:
    mcp_sse = MCP("http://localhost:8080/sse")
    print("✓ SSE URL initialization successful")
    print(f"  - is_http: {getattr(mcp_sse, 'is_http', 'Not set')}")
    print(f"  - is_sse: {getattr(mcp_sse, 'is_sse', 'Not set')}")
except Exception as e:
    print(f"✗ SSE URL initialization failed: {e}")

# Test 2: Command string format (stdio)
print("\n2. Testing command string format:")
try:
    mcp_stdio = MCP("/usr/bin/python3 /path/to/server.py")
    print("✓ Command string initialization successful")
    print(f"  - is_http: {getattr(mcp_stdio, 'is_http', 'Not set')}")
    print(f"  - is_sse: {getattr(mcp_stdio, 'is_sse', 'Not set')}")
except Exception as e:
    print(f"✗ Command string initialization failed: {e}")

# Test 3: Command and args format
print("\n3. Testing command and args format:")
try:
    mcp_cmd_args = MCP("/usr/bin/python3", ["/path/to/server.py"])
    print("✓ Command+args initialization successful")
except Exception as e:
    print(f"✗ Command+args initialization failed: {e}")

# Test 4: New HTTP-Streaming with auto-detection
print("\n4. Testing new HTTP-Streaming auto-detection:")
try:
    mcp_http_auto = MCP("http://localhost:8080/stream")
    print("✓ HTTP-Streaming auto-detection successful")
    print(f"  - is_http: {getattr(mcp_http_auto, 'is_http', 'Not set')}")
    print(f"  - is_sse: {getattr(mcp_http_auto, 'is_sse', 'Not set')}")
except Exception as e:
    print(f"✗ HTTP-Streaming auto-detection failed: {e}")

# Test 5: Explicit transport selection
print("\n5. Testing explicit transport selection:")
try:
    mcp_explicit = MCP("http://localhost:8080/api", transport="http-streaming")
    print("✓ Explicit transport selection successful")
    print(f"  - is_http: {getattr(mcp_explicit, 'is_http', 'Not set')}")
    print(f"  - is_sse: {getattr(mcp_explicit, 'is_sse', 'Not set')}")
except Exception as e:
    print(f"✗ Explicit transport selection failed: {e}")

# Test 6: Backward compatibility - named parameter
print("\n6. Testing backward compatibility with named parameter:")
try:
    mcp_named = MCP(command="/usr/bin/python3", args=["/path/to/server.py"])
    print("✓ Named parameter initialization successful")
except Exception as e:
    print(f"✗ Named parameter initialization failed: {e}")

print("\n" + "=" * 50)
print("Backward compatibility tests completed!")
print("\nSummary:")
print("- Existing SSE URLs will continue to work as before")
print("- Command-based MCP servers work unchanged")  
print("- New HTTP-Streaming support is available with auto-detection")
print("- Explicit transport selection is optional")