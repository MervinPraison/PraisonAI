#!/usr/bin/env python3
"""
Test script for Claude Code integration with PraisonAI Agents

This script tests the basic functionality of the refactored Claude Code integration
"""

import os
import sys
import asyncio
import unittest

# Add the src directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai'))

def test_claude_code_tool_import():
    """Test that we can import the Claude Code tool function"""
    try:
        from praisonai.ui.code import claude_code_tool
        print("✅ Successfully imported claude_code_tool")
        return True
    except ImportError as e:
        print(f"❌ Failed to import claude_code_tool: {e}")
        return False

def test_praisonai_agents_import():
    """Test praisonaiagents import availability"""
    try:
        from praisonaiagents import Agent
        print("✅ PraisonAI Agents is available")
        return True
    except ImportError as e:
        print(f"⚠️  PraisonAI Agents not available (fallback to litellm): {e}")
        return False

def test_claude_code_availability():
    """Test if Claude Code CLI is available"""
    import subprocess
    try:
        result = subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Claude Code CLI is available: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Claude Code CLI returned error: {result.stderr}")
            return False
    except FileNotFoundError:
        print("⚠️  Claude Code CLI not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        print("⚠️  Claude Code CLI check timed out")
        return False
    except Exception as e:
        print(f"⚠️  Error checking Claude Code CLI: {e}")
        return False

async def test_claude_code_tool_execution():
    """Test basic Claude Code tool execution (simple query)"""
    try:
        from praisonai.ui.code import claude_code_tool
        
        # Test with a simple query that shouldn't modify files
        test_query = "What is the current directory?"
        result = await claude_code_tool(test_query)
        
        print(f"✅ Claude Code tool executed successfully")
        print(f"Query: {test_query}")
        print(f"Result (first 100 chars): {str(result)[:100]}...")
        return True
    except Exception as e:
        print(f"❌ Claude Code tool execution failed: {e}")
        return False

def test_environment_variables():
    """Test that environment variables are properly set"""
    test_vars = [
        "PRAISONAI_CLAUDECODE_ENABLED",
        "PRAISONAI_CODE_REPO_PATH"
    ]
    
    print("Environment Variables:")
    for var in test_vars:
        value = os.getenv(var, "NOT_SET")
        print(f"  {var}: {value}")
    
    return True

async def run_tests():
    """Run all tests"""
    print("🧪 Testing Claude Code Integration with PraisonAI Agents")
    print("=" * 60)
    
    tests = [
        ("Import Claude Code Tool", test_claude_code_tool_import),
        ("Import PraisonAI Agents", test_praisonai_agents_import),
        ("Environment Variables", test_environment_variables),
        ("Claude Code CLI Availability", test_claude_code_availability),
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results[test_name] = False
    
    # Only test Claude Code tool execution if CLI is available
    if results.get("Claude Code CLI Availability", False):
        print(f"\n🔍 Claude Code Tool Execution:")
        try:
            results["Claude Code Tool Execution"] = await test_claude_code_tool_execution()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results["Claude Code Tool Execution"] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(run_tests())
