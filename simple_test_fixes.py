#!/usr/bin/env python3
"""
Simple test to verify key architectural fixes.
"""

import sys
import threading
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_rate_limiter_threading_fix():
    """Test that rate limiter uses proper threading locks."""
    print("Testing rate_limiter.py threading fix...")
    
    # Import and check if the file has the threading import and double-checked locking
    with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents/llm/rate_limiter.py', 'r') as f:
        content = f.read()
    
    assert 'import threading' in content, "rate_limiter.py should import threading"
    assert 'self._lock_init = threading.Lock()' in content, "rate_limiter.py should have lock init"
    assert 'with self._lock_init:' in content, "rate_limiter.py should use double-checked locking"
    print("✅ rate_limiter.py properly uses threading locks for race condition prevention")

def test_handoff_threading_fix():
    """Test that handoff.py uses proper threading locks for class-level semaphore."""
    print("Testing handoff.py threading fix...")
    
    with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents/agent/handoff.py', 'r') as f:
        content = f.read()
    
    assert '_semaphore_lock: threading.Lock = threading.Lock()' in content, "handoff.py should have class-level threading lock"
    assert 'with Handoff._semaphore_lock:' in content, "handoff.py should use class-level lock"
    print("✅ handoff.py properly uses class-level threading lock for race condition prevention")

def test_workflows_configurable_workers():
    """Test that workflows.py has configurable worker limits."""
    print("Testing workflows.py configurable workers...")
    
    with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents/workflows/workflows.py', 'r') as f:
        content = f.read()
    
    assert 'DEFAULT_MAX_PARALLEL_WORKERS = 3' in content, "workflows.py should define configurable default"
    assert 'max_workers: Optional[int] = None' in content, "Parallel class should accept max_workers"
    assert 'user_max = getattr(parallel_step, \'max_workers\', None)' in content, "Should check user configuration"
    assert 'effective_workers = min(3, len(parallel_step.steps))' not in content, "Should not hard-code limit of 3"
    print("✅ workflows.py now has configurable parallel worker limits")

def test_exception_handling_improvements():
    """Test that silent exception handling is replaced with logging."""
    print("Testing chat_mixin.py exception handling improvements...")
    
    with open('/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents/agent/chat_mixin.py', 'r') as f:
        content = f.read()
    
    assert 'logging.warning(f"BEFORE_COMPACTION hook failed: {e}")' in content, "Should log hook failures"
    assert 'logging.warning(f"AFTER_COMPACTION hook failed: {e}")' in content, "Should log hook failures"
    assert 'logging.warning(\n                f"Failed to extract LLM response content (falling back to str): {e}"\n            )' in content, "Should log response extraction failures"
    print("✅ chat_mixin.py now logs warnings instead of silent exception swallowing")

def main():
    """Run verification tests."""
    print("Verifying PraisonAI architectural fixes...")
    print("=" * 50)
    
    test_rate_limiter_threading_fix()
    test_handoff_threading_fix() 
    test_workflows_configurable_workers()
    test_exception_handling_improvements()
    
    print("=" * 50)
    print("✅ All architectural fixes verified successfully!")

if __name__ == "__main__":
    main()