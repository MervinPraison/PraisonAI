#!/usr/bin/env python3
"""
Test script to verify thread safety fixes for main.py globals.
Tests concurrent access to error_logs, callbacks, and approval_callback.
"""

import sys
import os
import threading
import time
import contextvars
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.main import (
    error_logs,
    sync_display_callbacks,
    async_display_callbacks,
    approval_callback,
    register_display_callback,
    register_approval_callback
)

def test_error_logs_thread_safety():
    """Test that error_logs are properly isolated per context"""
    print("Testing error_logs thread safety...")
    
    results = []
    
    def worker(worker_id):
        """Each worker should see its own error logs in its context"""
        # Create a new context for this worker
        ctx = contextvars.copy_context()
        
        def in_context():
            # Add some errors specific to this worker
            for i in range(5):
                error_logs.append(f"Worker {worker_id} error {i}")
                time.sleep(0.001)  # Small delay to encourage race conditions
            
            # Check that only this worker's errors are visible
            worker_errors = [log for log in error_logs if f"Worker {worker_id}" in log]
            total_errors = len(error_logs)
            
            return {
                'worker_id': worker_id,
                'worker_errors': len(worker_errors),
                'total_errors': total_errors,
                'errors': list(error_logs)
            }
        
        return ctx.run(in_context)
    
    # Run multiple workers concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(10)]
        results = [future.result() for future in as_completed(futures)]
    
    # Analyze results
    print(f"Completed {len(results)} workers")
    for result in results:
        print(f"Worker {result['worker_id']}: {result['worker_errors']} own errors, {result['total_errors']} total")
        # Each worker should only see its own 5 errors
        assert result['worker_errors'] == 5, f"Worker {result['worker_id']} saw {result['worker_errors']} own errors, expected 5"
        assert result['total_errors'] == 5, f"Worker {result['worker_id']} saw {result['total_errors']} total errors, expected 5"
    
    print("✅ error_logs thread safety test passed!")

def test_callbacks_thread_safety():
    """Test that callbacks are properly isolated per context"""
    print("Testing callbacks thread safety...")
    
    def test_callback(message=None, **kwargs):
        return f"Processed: {message}"
    
    results = []
    
    def worker(worker_id):
        """Each worker should see its own callbacks in its context"""
        ctx = contextvars.copy_context()
        
        def in_context():
            # Register a callback specific to this worker
            callback_name = f"worker_{worker_id}_callback"
            register_display_callback(callback_name, test_callback)
            
            # Check that only this worker's callback is visible
            worker_callbacks = [k for k in sync_display_callbacks.keys() if f"worker_{worker_id}" in k]
            all_callbacks = list(sync_display_callbacks.keys())
            
            return {
                'worker_id': worker_id,
                'worker_callbacks': len(worker_callbacks),
                'total_callbacks': len(all_callbacks),
                'callback_names': all_callbacks
            }
        
        return ctx.run(in_context)
    
    # Run multiple workers concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, i) for i in range(5)]
        results = [future.result() for future in as_completed(futures)]
    
    # Analyze results
    for result in results:
        print(f"Worker {result['worker_id']}: {result['worker_callbacks']} own callbacks, {result['total_callbacks']} total")
        # Each worker should only see its own 1 callback
        assert result['worker_callbacks'] == 1, f"Worker {result['worker_id']} saw {result['worker_callbacks']} own callbacks, expected 1"
        assert result['total_callbacks'] == 1, f"Worker {result['worker_id']} saw {result['total_callbacks']} total callbacks, expected 1"
    
    print("✅ callbacks thread safety test passed!")

def test_approval_callback_thread_safety():
    """Test that approval_callback is properly isolated per context"""
    print("Testing approval_callback thread safety...")
    
    results = []
    
    def worker(worker_id):
        """Each worker should have its own approval callback in its context"""
        ctx = contextvars.copy_context()
        
        def in_context():
            # Set an approval callback specific to this worker
            def worker_approval_callback(func_name, args, risk_level):
                return f"Worker {worker_id} approved {func_name}"
            
            register_approval_callback(worker_approval_callback)
            
            # Test the callback
            if approval_callback:
                result_msg = approval_callback("test_func", {}, "low")
                has_own_callback = f"Worker {worker_id}" in result_msg
            else:
                has_own_callback = False
                result_msg = "No callback"
            
            return {
                'worker_id': worker_id,
                'has_callback': bool(approval_callback),
                'has_own_callback': has_own_callback,
                'result': result_msg
            }
        
        return ctx.run(in_context)
    
    # Run multiple workers concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker, i) for i in range(3)]
        results = [future.result() for future in as_completed(futures)]
    
    # Analyze results
    for result in results:
        print(f"Worker {result['worker_id']}: has_callback={result['has_callback']}, own_callback={result['has_own_callback']}")
        print(f"  Result: {result['result']}")
        assert result['has_callback'], f"Worker {result['worker_id']} has no callback"
        assert result['has_own_callback'], f"Worker {result['worker_id']} doesn't have its own callback"
    
    print("✅ approval_callback thread safety test passed!")

def test_basic_functionality():
    """Test that the basic functionality still works after thread safety changes"""
    print("Testing basic functionality...")
    
    # Test error logging
    error_logs.clear()
    error_logs.append("Test error 1")
    error_logs.append("Test error 2")
    assert len(error_logs) == 2
    assert error_logs[0] == "Test error 1"
    assert error_logs[1] == "Test error 2"
    
    # Test sync callbacks
    sync_display_callbacks.clear()
    
    def test_sync_callback(message=None):
        return f"Sync: {message}"
    
    register_display_callback("test", test_sync_callback)
    assert "test" in sync_display_callbacks
    assert sync_display_callbacks["test"] == test_sync_callback
    
    # Test approval callback
    def test_approval(func_name, args, risk_level):
        return f"Approved {func_name}"
    
    register_approval_callback(test_approval)
    assert approval_callback
    result = approval_callback("test_func", {}, "low")
    assert result == "Approved test_func"
    
    print("✅ Basic functionality test passed!")

if __name__ == "__main__":
    print("Starting thread safety tests for main.py globals...")
    
    try:
        test_basic_functionality()
        test_error_logs_thread_safety()
        test_callbacks_thread_safety()
        test_approval_callback_thread_safety()
        
        print("\n🎉 All thread safety tests passed!")
        print("The main.py globals are now properly isolated per context and thread-safe.")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)