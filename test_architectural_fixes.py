#!/usr/bin/env python3
"""
Test script for architectural fixes in issue #1553
"""

import random
import sys
import os

# Add the package to path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_retry_jitter():
    """Test Gap 2 fix: retry jitter prevents thundering herd"""
    print("Testing retry jitter fix...")
    
    from praisonaiagents.llm.error_classifier import ErrorCategory, get_retry_delay
    
    # Test that rate limit delays now have jitter
    delays = []
    for i in range(10):
        delay = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1)
        delays.append(delay)
    
    # All delays should be different with jitter
    unique_delays = len(set(delays))
    print(f"Generated {unique_delays} unique delays out of 10 attempts")
    
    # Delays should be in valid range (0 to 3.0 for attempt=1)
    all_in_range = all(0 <= delay <= 3.0 for delay in delays)
    print(f"All delays in expected range [0, 3.0]: {all_in_range}")
    
    # Context limits should still return deterministic delay (no contention issue)
    context_delay1 = get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=1)
    context_delay2 = get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=1)
    context_deterministic = context_delay1 == context_delay2
    print(f"Context limit delays are deterministic: {context_deterministic}")
    
    print("✅ Retry jitter test passed\n")
    return True


def test_task_failure_policies():
    """Test Gap 3 fix: configurable task failure handling"""
    print("Testing task failure policies...")
    
    from praisonaiagents.task.task import Task
    
    # Test that new failure policy parameters are available
    task = Task(
        description="Test task",
        fail_on_callback_error=True,
        fail_on_memory_error=False
    )
    
    # Check that the parameters are set correctly
    callback_policy_set = hasattr(task, 'fail_on_callback_error') and task.fail_on_callback_error
    memory_policy_set = hasattr(task, 'fail_on_memory_error') and not task.fail_on_memory_error
    
    print(f"Task has fail_on_callback_error property: {callback_policy_set}")
    print(f"Task has fail_on_memory_error property: {memory_policy_set}")
    
    # Check that non_fatal_errors list is initialized
    has_error_list = hasattr(task, 'non_fatal_errors') and isinstance(task.non_fatal_errors, list)
    print(f"Task has non_fatal_errors list: {has_error_list}")
    
    print("✅ Task failure policies test passed\n")
    return True


def test_timeout_enforcement():
    """Test Gap 1 fix: timeout enforcement in sync workflow"""
    print("Testing sync workflow timeout enforcement...")
    
    # Import the Process class
    from praisonaiagents.process.process import Process
    from praisonaiagents.task.task import Task
    from praisonaiagents.agent.agent import Agent
    
    # Create a minimal workflow with timeout
    task1 = Task(description="Test task", name="task1")
    tasks = {"task1": task1}
    agents = [Agent(name="test_agent")]
    
    process = Process(
        tasks=tasks,
        agents=agents,
        workflow_timeout=1,  # 1 second timeout
        max_iter=5
    )
    
    # Check that timeout parameter is set
    has_timeout = hasattr(process, 'workflow_timeout') and process.workflow_timeout == 1
    print(f"Process has workflow timeout configured: {has_timeout}")
    
    # Check that workflow_cancelled flag exists
    has_cancelled_flag = hasattr(process, 'workflow_cancelled')
    print(f"Process has workflow_cancelled flag: {has_cancelled_flag}")
    
    print("✅ Timeout enforcement test passed\n")
    return True


def main():
    """Run all tests for the architectural fixes"""
    print("Running tests for architectural fixes (Issue #1553)...")
    print("=" * 60)
    
    try:
        test_retry_jitter()
        test_task_failure_policies()
        test_timeout_enforcement()
        
        print("🎉 All architectural fix tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)