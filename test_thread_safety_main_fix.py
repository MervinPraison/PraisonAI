#!/usr/bin/env python3
"""
Comprehensive thread safety test for main.py global variables fix.

This test verifies that the contextvars-based fix properly isolates state 
between concurrent agents/contexts, preventing race conditions and cross-contamination.
"""

import asyncio
import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict

# Import the thread-safe globals
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.main import (
    error_logs,
    sync_display_callbacks, 
    async_display_callbacks,
    approval_callback,
    register_display_callback,
    register_approval_callback
)


def test_error_logs_isolation():
    """Test that error logs are isolated between different contexts."""
    results = {}
    
    def worker(worker_id):
        # Each worker runs in its own context - need to create a fresh context for each worker
        def worker_task():
            worker_errors = [f"Error {i} from worker {worker_id}" for i in range(10)]
            
            for error in worker_errors:
                error_logs.append(error)
            
            # Verify only this worker's errors are visible
            current_errors = list(error_logs)
            return current_errors
        
        # Run the task in a new context
        ctx = contextvars.copy_context()
        current_errors = ctx.run(worker_task)
        results[worker_id] = current_errors
        
        # Verify no contamination from other workers
        for error in current_errors:
            assert f"worker {worker_id}" in error, f"Cross-contamination detected: {error}"
    
    # Run 10 concurrent workers
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(10)]
        for future in futures:
            future.result()
    
    # Verify each worker saw only its own errors
    for worker_id, errors in results.items():
        assert len(errors) == 10, f"Worker {worker_id} saw {len(errors)} errors, expected 10"
        for error in errors:
            assert f"worker {worker_id}" in error, f"Worker {worker_id} saw foreign error: {error}"
    
    print("✅ Error logs isolation test passed")


def test_callback_isolation():
    """Test that display callbacks are isolated between contexts."""
    results = {}
    
    def worker(worker_id):
        def worker_task():
            # Each worker registers its own callback
            def my_callback(message=None, **kwargs):
                return f"Worker {worker_id} processed: {message}"
            
            register_display_callback('test_event', my_callback)
            
            # Verify only this worker's callback is registered
            callback = sync_display_callbacks.get('test_event')
            assert callback is not None, f"Worker {worker_id} callback not found"
            
            # Test the callback
            result = callback(message=f"test message {worker_id}")
            return result
        
        # Run in fresh context
        ctx = contextvars.copy_context()
        result = ctx.run(worker_task)
        results[worker_id] = result
        
        # Verify isolation
        assert f"Worker {worker_id}" in result, f"Callback isolation failed for worker {worker_id}"
    
    # Run 5 concurrent workers
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, i) for i in range(5)]
        for future in futures:
            future.result()
    
    # Verify each worker got its own callback result
    for worker_id, result in results.items():
        assert f"Worker {worker_id}" in result, f"Callback result contamination for worker {worker_id}"
        assert f"test message {worker_id}" in result, f"Message processing failed for worker {worker_id}"
    
    print("✅ Callback isolation test passed")


def test_approval_callback_isolation():
    """Test that approval callbacks are isolated between contexts."""
    results = {}
    
    def worker(worker_id):
        def worker_task():
            # Each worker sets its own approval callback
            def my_approval(func_name, args, risk_level):
                return f"Worker {worker_id} approved {func_name}"
            
            register_approval_callback(my_approval)
            
            # Verify this worker's callback is set
            current_callback = approval_callback.get()
            assert current_callback is not None, f"Worker {worker_id} approval callback not set"
            
            # Test the callback
            result = current_callback("test_func", {}, "low")
            return result
        
        # Run in fresh context
        ctx = contextvars.copy_context()
        result = ctx.run(worker_task)
        results[worker_id] = result
        
        # Verify isolation
        assert f"Worker {worker_id}" in result, f"Approval callback isolation failed for worker {worker_id}"
    
    # Run 5 concurrent workers  
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, i) for i in range(5)]
        for future in futures:
            future.result()
    
    # Verify each worker got its own approval result
    for worker_id, result in results.items():
        assert f"Worker {worker_id}" in result, f"Approval callback result contamination for worker {worker_id}"
    
    print("✅ Approval callback isolation test passed")


async def test_async_callback_isolation():
    """Test that async callbacks are also properly isolated."""
    results = {}
    
    async def worker(worker_id):
        # Create a task within the current context - asyncio automatically copies context
        async def worker_task():
            # Each worker registers its own async callback
            async def my_async_callback(message=None, **kwargs):
                await asyncio.sleep(0.01)  # Small async operation
                return f"Async Worker {worker_id} processed: {message}"
            
            register_display_callback('async_test_event', my_async_callback, is_async=True)
            
            # Verify only this worker's callback is registered
            callback = async_display_callbacks.get('async_test_event')
            assert callback is not None, f"Async Worker {worker_id} callback not found"
            
            # Test the callback
            result = await callback(message=f"async test message {worker_id}")
            return result
        
        result = await worker_task()
        results[worker_id] = result
        
        # Verify isolation
        assert f"Async Worker {worker_id}" in result, f"Async callback isolation failed for worker {worker_id}"
    
    # Run 5 concurrent async workers - each will run in its own context copy
    tasks = [worker(i) for i in range(5)]
    await asyncio.gather(*tasks)
    
    # Verify each worker got its own callback result
    for worker_id, result in results.items():
        assert f"Async Worker {worker_id}" in result, f"Async callback result contamination for worker {worker_id}"
        assert f"async test message {worker_id}" in result, f"Async message processing failed for worker {worker_id}"
    
    print("✅ Async callback isolation test passed")


def test_context_inheritance():
    """Test that context variables provide proper isolation between parent and child contexts."""
    
    # Test that contexts start clean by default
    initial_errors = list(error_logs)
    assert len(initial_errors) == 0, f"Expected clean context, found {len(initial_errors)} errors"
    
    # Add something in the current context
    error_logs.append("Current context error")
    current_errors = list(error_logs)
    assert len(current_errors) == 1, "Current context should have 1 error"
    
    # Test that a new context starts fresh (doesn't inherit from this context unless explicitly copied)
    def new_context_task():
        new_errors = list(error_logs)  
        return len(new_errors)
    
    ctx = contextvars.Context()  # Create truly empty context
    new_context_error_count = ctx.run(new_context_task)
    
    # The new context should start with empty state (our ContextVar has default=[])
    assert new_context_error_count == 0, f"New context should start empty, but had {new_context_error_count} errors"
    
    # Original context should still have its error
    final_current_errors = list(error_logs)
    assert len(final_current_errors) == 1, "Original context should still have 1 error"
    
    print("✅ Context inheritance test passed")


def run_all_tests():
    """Run all thread safety tests."""
    print("🧪 Running thread safety tests for main.py globals fix...\n")
    
    # Run each test in its own clean context
    def run_test_in_clean_context(test_func):
        ctx = contextvars.copy_context()
        ctx.run(test_func)
    
    # Run sync tests
    run_test_in_clean_context(test_error_logs_isolation)
    run_test_in_clean_context(test_callback_isolation)
    run_test_in_clean_context(test_approval_callback_isolation)
    run_test_in_clean_context(test_context_inheritance)
    
    # Run async tests in clean context too
    def run_async_test():
        asyncio.run(test_async_callback_isolation())
    
    run_test_in_clean_context(run_async_test)
    
    print("\n🎉 All thread safety tests passed!")
    print("✅ main.py global variables are now thread-safe with proper context isolation")


if __name__ == "__main__":
    run_all_tests()