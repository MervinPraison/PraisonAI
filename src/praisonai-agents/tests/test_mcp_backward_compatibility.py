"""
Test script to verify backward compatibility of MCP HTTP-Streaming implementation.

This test ensures that all existing MCP usage patterns continue to work
without any modifications.
"""

import sys
import traceback
from praisonaiagents.mcp import MCP

def test_backward_compatibility():
    """Test that all existing MCP usage patterns still work."""
    
    print("Testing MCP Backward Compatibility")
    print("==================================\n")
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: SSE URL (should auto-detect SSE)
    print("Test 1: SSE URL auto-detection")
    try:
        mcp = MCP("http://localhost:8080/sse")
        assert hasattr(mcp, 'is_http') and mcp.is_http == True
        assert hasattr(mcp, 'transport_type') and mcp.transport_type == "sse"
        print("✓ SSE URL correctly detected")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Failed: {e}")
        tests_failed += 1
        traceback.print_exc()
    
    # Test 2: Stream URL (should auto-detect HTTP-Streaming)
    print("\nTest 2: Stream URL auto-detection")
    try:
        mcp = MCP("http://localhost:8080/stream")
        assert hasattr(mcp, 'is_http') and mcp.is_http == True
        assert hasattr(mcp, 'transport_type') and mcp.transport_type == "http-streaming"
        print("✓ Stream URL correctly detected")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Failed: {e}")
        tests_failed += 1
        traceback.print_exc()
    
    # Test 3: Stdio command (should work as before)
    print("\nTest 3: Stdio command")
    try:
        mcp = MCP("python /path/to/server.py")
        assert hasattr(mcp, 'is_http') and mcp.is_http == False
        print("✓ Stdio command works as before")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Failed: {e}")
        tests_failed += 1
        traceback.print_exc()
    
    # Test 4: Explicit transport selection
    print("\nTest 4: Explicit transport selection")
    try:
        mcp_sse = MCP("http://localhost:8080/api", transport="sse")
        assert mcp_sse.transport_type == "sse"
        
        mcp_http = MCP("http://localhost:8080/api", transport="http-streaming")
        assert mcp_http.transport_type == "http-streaming"
        
        print("✓ Explicit transport selection works")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Failed: {e}")
        tests_failed += 1
        traceback.print_exc()
    
    # Test 5: Legacy parameters still work
    print("\nTest 5: Legacy parameters")
    try:
        # Test with command parameter
        mcp = MCP(command="python /path/to/server.py")
        assert hasattr(mcp, 'is_http') and mcp.is_http == False
        
        # Test with debug and timeout
        mcp2 = MCP("http://localhost:8080/sse", debug=False, timeout=30)
        assert mcp2.timeout == 30
        
        print("✓ Legacy parameters work")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Failed: {e}")
        tests_failed += 1
        traceback.print_exc()
    
    # Test 6: Iterator interface
    print("\nTest 6: Iterator interface")
    try:
        mcp = MCP("python -m mcp_server")
        # Should be iterable (even if no tools available)
        tools = list(mcp)
        assert isinstance(tools, list)
        print("✓ Iterator interface works")
        tests_passed += 1
    except Exception as e:
        print(f"✗ Failed: {e}")
        tests_failed += 1
        traceback.print_exc()
    
    # Summary
    print("\n" + "="*50)
    print(f"Tests Passed: {tests_passed}")
    print(f"Tests Failed: {tests_failed}")
    print("="*50)
    
    if tests_failed == 0:
        print("\n✓ All backward compatibility tests passed!")
        print("Existing code will continue to work without modifications.")
    else:
        print("\n✗ Some tests failed. Please check the implementation.")
        sys.exit(1)

if __name__ == "__main__":
    test_backward_compatibility()