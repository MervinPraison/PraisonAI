#!/usr/bin/env python3
"""Basic test for CLI Backend Protocol implementation."""

import asyncio
import sys
import os
from pathlib import Path

# Add src paths to Python path for testing
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root / "src" / "praisonai-agents"))
sys.path.insert(0, str(repo_root / "src" / "praisonai"))

def test_protocols_import():
    """Test that CLI backend protocols can be imported."""
    print("Testing CLI backend protocols import...")
    try:
        from praisonaiagents import CliBackendProtocol, CliBackendConfig
        print("✓ Protocols imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Protocol import failed: {e}")
        return False

def test_registry_import():
    """Test that CLI backend registry can be imported."""
    print("Testing CLI backend registry import...")
    try:
        from praisonai.cli_backends import resolve_cli_backend, list_cli_backends
        backends = list_cli_backends()
        print(f"✓ Registry imported successfully, available backends: {backends}")
        return True
    except ImportError as e:
        print(f"✗ Registry import failed: {e}")
        return False

def test_claude_backend():
    """Test that Claude backend can be resolved."""
    print("Testing Claude backend resolution...")
    try:
        from praisonai.cli_backends import resolve_cli_backend
        backend = resolve_cli_backend("claude-code")
        print(f"✓ Claude backend resolved: {type(backend)}")
        print(f"  Config command: {backend.config.command}")
        print(f"  Config args: {backend.config.args}")
        return True
    except Exception as e:
        print(f"✗ Claude backend resolution failed: {e}")
        return False

def test_agent_with_cli_backend():
    """Test that Agent can be created with CLI backend."""
    print("Testing Agent with CLI backend...")
    try:
        from praisonaiagents import Agent
        
        # Test with string backend ID
        agent = Agent(
            name="test_agent",
            role="Test Assistant", 
            cli_backend="claude-code"
        )
        
        print("✓ Agent created with CLI backend")
        print(f"  Agent name: {agent.name}")
        print(f"  CLI backend configured: {agent._cli_backend is not None}")
        return True
    except Exception as e:
        print(f"✗ Agent creation with CLI backend failed: {e}")
        return False

async def test_basic_execution():
    """Test basic CLI backend execution (mock)."""
    print("Testing basic CLI backend execution...")
    
    # Check if Claude CLI is available
    import shutil
    if shutil.which("claude") is None:
        print("⚠ Claude CLI not installed; skipping execution test")
        return True

    try:
        from praisonai.cli_backends import resolve_cli_backend
        from praisonaiagents import CliSessionBinding
        
        backend = resolve_cli_backend("claude-code")
        
        # Test basic structure
        result = await backend.execute("Hello, test!", session=CliSessionBinding(session_id="test"))
        if result.error:
            print(f"✗ CLI backend returned error: {result.error}")
            return False

        print("✓ CLI backend execution completed")
        print(f"  Result type: {type(result)}")
        return True
        
    except Exception as e:
        print(f"✗ CLI backend execution failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=== CLI Backend Protocol Implementation Test ===\n")
    
    tests = [
        test_protocols_import,
        test_registry_import,
        test_claude_backend,
        test_agent_with_cli_backend,
    ]
    
    async_tests = [
        test_basic_execution,
    ]
    
    results = []
    
    # Run sync tests
    for test in tests:
        try:
            result = test()
            results.append(result)
            print()
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
            results.append(False)
            print()
    
    # Run async tests
    for test in async_tests:
        try:
            result = asyncio.run(test())
            results.append(result)
            print()
        except Exception as e:
            print(f"✗ Async test {test.__name__} crashed: {e}")
            results.append(False)
            print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    print("=== Test Summary ===")
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    exit(main())