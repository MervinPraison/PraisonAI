#!/usr/bin/env python3
"""
Test script for architectural gap fixes.

Tests the three main fixes:
1. AsyncSafeState for dual-lock protection 
2. GuardrailProtocol and fail-closed LLM guardrail
3. AsyncMemoryMixin for async-safe memory operations

This is a basic smoke test to ensure imports and basic functionality work.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_async_safety():
    """Test Gap 1: AsyncSafeState dual-lock abstraction."""
    print("=== Testing Gap 1: AsyncSafeState ===")
    
    from praisonaiagents.agent.async_safety import AsyncSafeState, DualLock
    
    # Test AsyncSafeState
    state = AsyncSafeState([])
    
    # Test sync access
    with state.lock() as history:
        history.append("sync message")
        
    assert state.get() == ["sync message"]
    print("✓ Sync access works")
    
    # Test async context detection
    lock = DualLock()
    is_async = lock.is_async_context()
    assert not is_async  # Should be False in sync context
    print("✓ Async context detection works")
    
    print("Gap 1 tests passed!\n")

def test_guardrails():
    """Test Gap 2: GuardrailProtocol and fail-closed behavior."""
    print("=== Testing Gap 2: Guardrails ===")
    
    from praisonaiagents.guardrails import GuardrailProtocol, GuardrailChain, LLMGuardrail
    
    # Test protocol implementation check
    class SimpleFilter:
        def validate_input(self, content: str, **kwargs):
            if "bad" in content.lower():
                return False, "Contains bad word"
            return True, content
            
        def validate_output(self, content: str, **kwargs):
            return self.validate_input(content, **kwargs)
            
        def validate_tool_call(self, tool_name: str, arguments: dict, **kwargs):
            return True, arguments
    
    filter_guard = SimpleFilter()
    
    # Test direct validation
    is_valid, result = filter_guard.validate_input("Hello world")
    assert is_valid == True
    print("✓ Valid input passes")
    
    is_valid, result = filter_guard.validate_input("This is bad")
    assert is_valid == False
    print("✓ Invalid input fails")
    
    # Test guardrail chain with fail-closed behavior
    chain = GuardrailChain([filter_guard], fail_open=False)
    
    is_valid, result = chain.validate_input("Good content")
    assert is_valid == True
    print("✓ Chain validation works")
    
    # Test LLM guardrail fail-closed (without actual LLM)
    llm_guard = LLMGuardrail("Test guardrail", llm=None)
    is_valid, result = llm_guard.validate_input("test")
    assert is_valid == False  # Should fail-closed with no LLM
    print("✓ LLM guardrail fails closed without LLM")
    
    print("Gap 2 tests passed!\n")

async def test_async_memory():
    """Test Gap 3: AsyncMemoryMixin."""
    print("=== Testing Gap 3: Async Memory ===")
    
    from praisonaiagents.agent.async_memory_mixin import AsyncMemoryMixin
    
    # Create a simple mock agent with AsyncMemoryMixin
    class MockAgent(AsyncMemoryMixin):
        def __init__(self):
            self._memory = None  # No memory adapter for this test
    
    agent = MockAgent()
    
    # Test async memory operations (should handle gracefully with no memory)
    memory_id = await agent.astore_memory("test content")
    assert memory_id is None  # Should return None with no memory
    print("✓ Async store handles missing memory gracefully")
    
    memories = await agent.asearch_memory("test query")
    assert memories == []  # Should return empty list
    print("✓ Async search handles missing memory gracefully")
    
    # Test context building
    context = await agent._async_build_memory_context("test")
    assert context == ""  # Should return empty string with no memories
    print("✓ Async context building works")
    
    print("Gap 3 tests passed!\n")

def test_agent_import():
    """Test that Agent can be imported with new mixins."""
    print("=== Testing Agent Import ===")
    
    try:
        from praisonaiagents.agent.agent import Agent
        print("✓ Agent imports successfully with new mixins")
        
        # Test basic agent creation (smoke test)
        agent = Agent(name="test_agent", instructions="Test")
        assert agent.name == "test_agent"
        print("✓ Agent creates successfully")
        
        # Test async-safe chat history
        assert hasattr(agent, '_Agent__chat_history_state')
        print("✓ Agent has async-safe chat history")
        
        # Test async memory methods exist
        assert hasattr(agent, 'astore_memory')
        assert hasattr(agent, 'asearch_memory')
        print("✓ Agent has async memory methods")
        
    except Exception as e:
        print(f"✗ Agent import failed: {e}")
        raise
    
    print("Agent import tests passed!\n")

def main():
    """Run all tests."""
    print("Testing PraisonAI Architectural Gap Fixes\n")
    
    try:
        # Test individual components
        test_async_safety()
        test_guardrails()
        
        # Test async functionality
        asyncio.run(test_async_memory())
        
        # Test integration
        test_agent_import()
        
        print("🎉 All tests passed! Architectural gaps have been addressed.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())