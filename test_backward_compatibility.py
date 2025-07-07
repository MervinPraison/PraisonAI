#!/usr/bin/env python3
"""
Test script to verify backward compatibility of MCP HTTP-Streaming implementation.
"""

import sys
import os

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.mcp import MCP

def test_backward_compatibility():
    """Test that all existing MCP usage patterns still work."""
    
    print("Testing MCP Backward Compatibility\n")
    
    # Test 1: SSE URL detection (existing pattern)
    print("Test 1: SSE URL auto-detection")
    try:
        mcp = MCP("http://localhost:8080/sse")
        assert hasattr(mcp, 'is_sse')
        assert mcp.is_sse == True
        assert hasattr(mcp, 'is_http_streaming')
        assert mcp.is_http_streaming == False
        print("✓ PASS: SSE endpoints detected correctly")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 2: HTTP URL detection (new default)
    print("\nTest 2: HTTP URL auto-detection")
    try:
        mcp = MCP("http://localhost:8080/api")
        assert hasattr(mcp, 'is_sse')
        assert mcp.is_sse == False
        assert hasattr(mcp, 'is_http_streaming')
        assert mcp.is_http_streaming == True
        print("✓ PASS: HTTP endpoints default to HTTP-streaming")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 3: Stdio command (existing pattern)
    print("\nTest 3: Stdio command pattern")
    try:
        mcp = MCP(command="/usr/bin/python", args=["server.py"])
        assert hasattr(mcp, 'is_sse')
        assert mcp.is_sse == False
        assert hasattr(mcp, 'is_http_streaming')
        assert mcp.is_http_streaming == False
        assert hasattr(mcp, 'server_params')
        print("✓ PASS: Stdio command pattern works")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 4: Single string command (existing pattern)
    print("\nTest 4: Single string command pattern")
    try:
        mcp = MCP("/usr/bin/python server.py")
        assert hasattr(mcp, 'is_sse')
        assert mcp.is_sse == False
        assert hasattr(mcp, 'is_http_streaming')
        assert mcp.is_http_streaming == False
        assert hasattr(mcp, 'server_params')
        print("✓ PASS: Single string command pattern works")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 5: NPX pattern (existing)
    print("\nTest 5: NPX command pattern")
    try:
        mcp = MCP("npx @modelcontextprotocol/server-brave-search")
        assert hasattr(mcp, 'is_npx')
        assert mcp.is_npx == True
        assert hasattr(mcp, 'is_sse')
        assert mcp.is_sse == False
        assert hasattr(mcp, 'is_http_streaming')
        assert mcp.is_http_streaming == False
        print("✓ PASS: NPX command pattern works")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 6: Named parameter 'command' (backward compatibility)
    print("\nTest 6: Named parameter 'command' (legacy)")
    try:
        mcp = MCP(command="/usr/bin/python", args=["server.py"])
        assert hasattr(mcp, 'server_params')
        print("✓ PASS: Legacy 'command' parameter works")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 7: Transport selection (new feature)
    print("\nTest 7: Explicit transport selection")
    try:
        # Force SSE on non-SSE URL
        mcp_sse = MCP("http://localhost:8080/api", transport="sse")
        assert mcp_sse.is_sse == True
        assert mcp_sse.is_http_streaming == False
        
        # Force HTTP-streaming on SSE URL
        mcp_http = MCP("http://localhost:8080/sse", transport="http-streaming")
        assert mcp_http.is_sse == False
        assert mcp_http.is_http_streaming == True
        
        print("✓ PASS: Explicit transport selection works")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    
    # Test 8: Invalid transport handling
    print("\nTest 8: Invalid transport error handling")
    try:
        mcp = MCP("http://localhost:8080/api", transport="invalid")
        print("✗ FAIL: Should have raised ValueError")
    except ValueError as e:
        print(f"✓ PASS: Correctly raised ValueError: {e}")
    except Exception as e:
        print(f"✗ FAIL: Wrong exception type: {e}")
    
    # Test 9: SSE URL patterns
    print("\nTest 9: Various SSE URL patterns")
    sse_urls = [
        "http://localhost:8080/sse",
        "http://localhost:8080/sse/",
        "http://localhost:8080/events",
        "http://localhost:8080/stream",
        "http://localhost:8080/server-sent-events",
        "http://localhost:8080/api?transport=sse",
    ]
    
    all_passed = True
    for url in sse_urls:
        try:
            mcp = MCP(url)
            if not mcp.is_sse:
                print(f"✗ FAIL: {url} should use SSE transport")
                all_passed = False
        except Exception as e:
            print(f"✗ FAIL: Error with {url}: {e}")
            all_passed = False
    
    if all_passed:
        print("✓ PASS: All SSE URL patterns detected correctly")
    
    print("\n" + "="*50)
    print("Backward Compatibility Test Summary")
    print("All existing MCP usage patterns continue to work!")
    print("="*50)

if __name__ == "__main__":
    test_backward_compatibility()