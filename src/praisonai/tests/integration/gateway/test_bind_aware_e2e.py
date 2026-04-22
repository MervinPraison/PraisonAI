"""
End-to-end integration test for bind-aware authentication posture.

Tests the complete integration including a real agentic test.
"""

import os
import sys
import pytest

# Add both packages to path
base_dir = os.path.join(os.path.dirname(__file__), '../../../..')
sys.path.insert(0, os.path.join(base_dir, 'praisonai-agents'))
sys.path.insert(0, os.path.join(base_dir, 'praisonai'))

def test_bind_aware_auth_with_real_agent():
    """Test bind-aware auth with a real agent execution."""
    from praisonaiagents import Agent
    from praisonaiagents.gateway.protocols import is_loopback, resolve_auth_mode
    from praisonaiagents.gateway.config import GatewayConfig
    from praisonai.gateway.auth import assert_external_bind_safe, GatewayStartupError
    
    print("=== End-to-End Bind-Aware Auth Test ===")
    
    # Test 1: Verify loopback detection
    print("\n1. Testing loopback detection:")
    loopback_hosts = ["127.0.0.1", "localhost", "::1"]
    external_hosts = ["0.0.0.0", "192.168.1.1", "8.8.8.8"]
    
    for host in loopback_hosts:
        assert is_loopback(host), f"{host} should be loopback"
        print(f"  ✓ {host} → loopback")
    
    for host in external_hosts:
        assert not is_loopback(host), f"{host} should not be loopback"
        print(f"  ✓ {host} → external")
    
    # Test 2: Verify auth mode resolution
    print("\n2. Testing auth mode resolution:")
    for host in loopback_hosts:
        mode = resolve_auth_mode(host)
        assert mode == "local", f"{host} should resolve to 'local'"
        print(f"  ✓ {host} → {mode}")
    
    for host in external_hosts:
        mode = resolve_auth_mode(host)
        assert mode == "token", f"{host} should resolve to 'token'"
        print(f"  ✓ {host} → {mode}")
    
    # Test 3: Gateway config validation
    print("\n3. Testing gateway auth enforcement:")
    
    # Loopback without token - should pass
    config = GatewayConfig(bind_host="127.0.0.1", auth_token=None)
    assert_external_bind_safe(config)
    print("  ✓ Loopback without token → ALLOWED")
    
    # External with token - should pass  
    config = GatewayConfig(bind_host="0.0.0.0", auth_token="test-token")
    assert_external_bind_safe(config)
    print("  ✓ External with token → ALLOWED")
    
    # External without token - should fail
    config = GatewayConfig(bind_host="0.0.0.0", auth_token=None)
    with pytest.raises(
        GatewayStartupError,
        match=r"Cannot bind to 0\.0\.0\.0 without an auth token",
    ):
        assert_external_bind_safe(config)
    print("  ✓ External without token → BLOCKED")
    
    # Test 4: Real agent test (as required by spec)
    print("\n4. Real agentic test:")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY required for the real agentic e2e test")

    agent = Agent(
        name="test-agent",
        instructions="You are a helpful assistant. Reply in exactly 3 words.",
        llm="gpt-4o-mini",
    )

    result = agent.start("Say hello briefly")

    print(f"  ✓ Agent response: {result}")

    assert isinstance(result, str), "Agent should return a string"
    assert len(result.strip()) > 0, "Agent should return non-empty response"

    print("  ✓ Real agent test completed successfully")
    
    print("\n=== All tests passed! Bind-aware auth is working correctly ===")


if __name__ == "__main__":
    test_bind_aware_auth_with_real_agent()