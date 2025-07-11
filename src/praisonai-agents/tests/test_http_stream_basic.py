#!/usr/bin/env python
"""
Basic test to verify HTTP Stream implementation is working correctly.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents.mcp import MCP

def test_transport_selection():
    """Test that URLs are correctly routed to appropriate transports."""
    
    print("Testing transport selection logic...")
    
    # Test 1: SSE URL should use SSE transport
    try:
        mcp_sse = MCP("http://localhost:8080/sse")
        assert mcp_sse.is_sse == True
        assert mcp_sse.is_http_stream == False
        print("✓ SSE URL correctly uses SSE transport")
    except Exception as e:
        print(f"✗ SSE URL test failed: {e}")
    
    # Test 2: Regular HTTP URL should use HTTP Stream transport
    try:
        mcp_http = MCP("http://localhost:8080")
        assert mcp_http.is_sse == False
        assert mcp_http.is_http_stream == True
        print("✓ HTTP URL correctly uses HTTP Stream transport")
    except Exception as e:
        print(f"✗ HTTP URL test failed: {e}")
    
    # Test 3: Custom endpoint should use HTTP Stream transport
    try:
        mcp_custom = MCP("http://localhost:8080/custom")
        assert mcp_custom.is_sse == False
        assert mcp_custom.is_http_stream == True
        print("✓ Custom endpoint correctly uses HTTP Stream transport")
    except Exception as e:
        print(f"✗ Custom endpoint test failed: {e}")
    
    # Test 4: Stdio transport should still work
    try:
        mcp_stdio = MCP("/Users/praison/miniconda3/envs/mcp/bin/python /Users/praison/stockprice/app.py")
        assert mcp_stdio.is_sse == False
        assert mcp_stdio.is_http_stream == False
        print("✓ Stdio transport still works")
    except Exception as e:
        print(f"✗ Stdio transport test failed: {e}")
    
    print("\nAll transport selection tests completed!")

if __name__ == "__main__":
    test_transport_selection()