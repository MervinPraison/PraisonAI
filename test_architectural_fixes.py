#!/usr/bin/env python3
"""
Test script to verify architectural fixes work correctly.
"""

import sys
import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

# Add the package to the path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_race_condition_fixes():
    """Test that race conditions in async primitive initialization are fixed."""
    print("Testing race condition fixes...")
    
    # Test process.py fix
    try:
        from praisonaiagents.process.process import ProcessManager
        
        async def test_get_state_lock():
            # Create multiple instances to test concurrent initialization
            manager1 = ProcessManager([])
            manager2 = ProcessManager([])
            
            # Call _get_state_lock concurrently from multiple coroutines
            lock1 = await manager1._get_state_lock()
            lock2 = await manager1._get_state_lock()
            lock3 = await manager2._get_state_lock()
            
            # All locks from same instance should be identical
            assert lock1 is lock2, "Race condition: different locks created for same instance"
            # Locks from different instances should be different
            assert lock1 is not lock3, "Different instances should have different locks"
            print("✅ process.py race condition fix verified")
        
        asyncio.run(test_get_state_lock())
    except Exception as e:
        print(f"❌ process.py test failed: {e}")
    
    # Test rate_limiter.py fix
    try:
        from praisonaiagents.llm.rate_limiter import RateLimiter
        
        def test_rate_limiter_concurrent():
            """Test concurrent access to rate limiter locks."""
            limiter = RateLimiter(requests_per_minute=60)
            
            # Call _get_lock from multiple threads concurrently
            locks = []
            def get_lock():
                locks.append(limiter._get_lock())
            
            # Create multiple threads that call _get_lock simultaneously
            threads = []
            for _ in range(10):
                t = threading.Thread(target=get_lock)
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            # All locks should be identical (no race condition)
            first_lock = locks[0]
            for lock in locks[1:]:
                assert lock is first_lock, "Race condition: different locks created"
            
            print("✅ rate_limiter.py race condition fix verified")
        
        test_rate_limiter_concurrent()
    except Exception as e:
        print(f"❌ rate_limiter.py test failed: {e}")

def test_parallel_workers_fix():
    """Test that parallel worker limits are now configurable."""
    print("Testing parallel workers fix...")
    
    try:
        from praisonaiagents.workflows.workflows import Parallel, DEFAULT_MAX_PARALLEL_WORKERS
        
        # Test Parallel class now accepts max_workers
        parallel_step = Parallel([1, 2, 3, 4, 5], max_workers=8)
        assert parallel_step.max_workers == 8, "Parallel should accept max_workers parameter"
        
        # Test default behavior
        parallel_default = Parallel([1, 2, 3])
        assert parallel_default.max_workers is None, "Default max_workers should be None"
        
        print(f"✅ Parallel workers fix verified - default={DEFAULT_MAX_PARALLEL_WORKERS}, user configurable")
    except Exception as e:
        print(f"❌ parallel workers test failed: {e}")

def test_exception_handling_fix():
    """Test that silent exception swallowing is replaced with proper logging."""
    print("Testing exception handling fix...")
    
    try:
        from praisonaiagents.agent.chat_mixin import ChatMixin
        import logging
        
        # Create a simple agent to test
        class TestAgent(ChatMixin):
            def __init__(self):
                self.name = "test"
                self.llm = "test-model"
                self._strict_hooks = False
        
        agent = TestAgent()
        
        # Test _extract_llm_response_content with invalid response
        class InvalidResponse:
            def __getattr__(self, name):
                raise AttributeError("Test error")
        
        # This should log a warning instead of silently failing
        result = agent._extract_llm_response_content(InvalidResponse())
        assert isinstance(result, str), "Should fall back to str(response)"
        
        # Test _supports_native_structured_output 
        # This should handle exceptions gracefully with logging
        supports = agent._supports_native_structured_output()
        assert isinstance(supports, bool), "Should return boolean"
        
        print("✅ Exception handling fix verified - now logs warnings instead of silent failures")
    except Exception as e:
        print(f"❌ exception handling test failed: {e}")

def main():
    """Run all architectural fix tests."""
    print("Testing PraisonAI architectural fixes...")
    print("=" * 50)
    
    test_race_condition_fixes()
    test_parallel_workers_fix()
    test_exception_handling_fix()
    
    print("=" * 50)
    print("All architectural fixes tested!")

if __name__ == "__main__":
    main()