#!/usr/bin/env python3
"""
Real Agentic Test for Terminal-Bench Integration

This is a MANDATORY test per AGENTS.md §9.4.
The agent MUST call agent.start() with a real prompt and produce LLM output.
"""
import sys
import os

# Add the package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

def test_real_agentic():
    """Real agentic test - agent must call LLM end-to-end."""
    try:
        from praisonaiagents import Agent
    except ImportError as e:
        print(f"❌ Cannot import praisonaiagents: {e}")
        print("Make sure you're running from the correct directory")
        return False
    
    try:
        # Create agent that will call LLM
        agent = Agent(
            name='terminal-bench-test-agent',
            instructions='You are a helpful assistant that can help with terminal and coding tasks'
        )
        
        # MUST call agent.start() with real prompt - this calls the LLM
        print("🚀 Starting real agentic test (calling LLM)...")
        result = agent.start('Say hello and briefly mention you can help with terminal tasks. Keep it to one sentence.')
        
        # Verify we got actual LLM output
        assert result is not None, "Agent returned None"
        assert isinstance(result, str), f"Agent returned {type(result)}, expected str" 
        assert len(result) > 0, "Agent returned empty string"
        
        print("✅ Real agentic test PASSED!")
        print(f"📊 Result length: {len(result)} characters")
        print(f"🤖 Agent response: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Real agentic test FAILED: {e}")
        return False

def test_shell_tools():
    """Test that shell tools are available and importable."""
    try:
        from praisonaiagents.tools import execute_command
        print("✅ Shell tools imported successfully")
        
        # Test tool metadata
        print(f"📋 execute_command available: {callable(execute_command)}")
        return True
        
    except ImportError as e:
        print(f"❌ Cannot import shell tools: {e}")
        return False

def test_approval_system():
    """Test that approval system works for auto-approval."""
    try:
        from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
        
        # Test setting auto-approval backend
        registry = get_approval_registry()
        registry.set_backend(AutoApproveBackend())
        
        print("✅ Approval system works correctly")
        return True
        
    except ImportError as e:
        print(f"❌ Cannot import approval system: {e}")
        return False

if __name__ == "__main__":
    print("PraisonAI Terminal-Bench Integration - Real Agentic Test")
    print("=" * 60)
    
    all_passed = True
    
    # Test 1: Shell tools
    print("\n🧪 Test 1: Shell Tools Import")
    if not test_shell_tools():
        all_passed = False
    
    # Test 2: Approval system
    print("\n🧪 Test 2: Approval System")
    if not test_approval_system():
        all_passed = False
    
    # Test 3: Real agentic test (MANDATORY)
    print("\n🧪 Test 3: Real Agentic Test (MANDATORY)")
    if not test_real_agentic():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED - Terminal-Bench integration is ready!")
    else:
        print("❌ Some tests failed - check output above")
        sys.exit(1)