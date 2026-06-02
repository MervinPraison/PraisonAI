#!/usr/bin/env python3
"""
Validate subscription auth fixes without pytest dependency.
"""
import sys
import os

# Add current directory to Python path
sys.path.insert(0, '.')
sys.path.insert(0, os.path.join(os.getcwd()))

def test_imports():
    """Test that imports work correctly."""
    print("Testing imports...")
    try:
        from praisonaiagents.auth.subscription.protocols import SubscriptionCredentials, AuthError
        print("✅ Protocol imports work")
        
        from praisonaiagents.auth.subscription.claude_code import ClaudeCodeAuth
        print("✅ Claude Code auth imports work")
        
        from praisonaiagents.auth.subscription.registry import resolve_subscription_credentials
        print("✅ Registry imports work")
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False
    return True


def test_codex_experimental():
    """Test that Codex raises experimental error."""
    print("\nTesting Codex experimental error...")
    try:
        from praisonaiagents.auth.subscription.codex import CodexAuth
        auth = CodexAuth()
        try:
            auth.resolve_credentials()
            print("❌ Codex should have raised experimental error")
            return False
        except Exception as e:
            if "experimental" in str(e).lower():
                print("✅ Codex correctly raises experimental error")
                return True
            else:
                print(f"❌ Codex raised wrong error: {e}")
                return False
    except Exception as e:
        print(f"❌ Codex test failed: {e}")
        return False


def test_gemini_experimental():
    """Test that Gemini CLI raises experimental error."""
    print("\nTesting Gemini CLI experimental error...")
    try:
        from praisonaiagents.auth.subscription.gemini_cli import GeminiCliAuth
        auth = GeminiCliAuth()
        try:
            auth.resolve_credentials()
            print("❌ Gemini CLI should have raised experimental error")
            return False
        except Exception as e:
            if "experimental" in str(e).lower():
                print("✅ Gemini CLI correctly raises experimental error")
                return True
            else:
                print(f"❌ Gemini CLI raised wrong error: {e}")
                return False
    except Exception as e:
        print(f"❌ Gemini CLI test failed: {e}")
        return False


def test_header_simplification():
    """Test that Claude Code headers are simplified."""
    print("\nTesting Claude Code header simplification...")
    try:
        from praisonaiagents.auth.subscription.claude_code import ClaudeCodeAuth
        auth = ClaudeCodeAuth()
        headers = auth.headers_for("https://api.anthropic.com", "claude-3-haiku")
        
        # Should only have interleaved-thinking, not oauth header (litellm handles that)
        if "anthropic-beta" in headers:
            beta_header = headers["anthropic-beta"]
            if beta_header == "interleaved-thinking-2025-05-14":
                print("✅ Claude Code headers correctly simplified")
                return True
            else:
                print(f"❌ Unexpected beta header value: {beta_header}")
                return False
        else:
            print("❌ anthropic-beta header missing")
            return False
            
    except Exception as e:
        print(f"❌ Header test failed: {e}")
        return False


def test_agent_construction():
    """Test basic agent construction with auth parameter."""
    print("\nTesting Agent construction with auth...")
    try:
        from praisonaiagents import Agent
        
        # This should work (though credential resolution will fail without actual creds)
        agent = Agent(name="test", auth="claude-code")
        print("✅ Agent construction with auth parameter works")
        
        # Test invalid provider
        try:
            agent = Agent(name="test", auth="invalid-provider")
            print("⚠️ Invalid provider didn't fail at construction (will fail at runtime)")
        except Exception:
            print("✅ Invalid provider handling works")
            
        return True
        
    except Exception as e:
        print(f"❌ Agent construction test failed: {e}")
        return False


def main():
    """Run all validation tests."""
    print("=== Validating Subscription Auth Fixes ===\n")
    
    tests = [
        test_imports,
        test_codex_experimental, 
        test_gemini_experimental,
        test_header_simplification,
        test_agent_construction,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print()
    
    print(f"\n=== Results: {passed}/{total} tests passed ===")
    
    if passed == total:
        print("🎉 All validation tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)