#!/usr/bin/env python
"""
Test thread safety of main.py global state fixes.
"""
import threading
import time
import concurrent.futures

def test_thread_safe_callback_registration():
    """Test that display callback registration is thread-safe."""
    from praisonaiagents.main import register_display_callback, _get_sync_display_callbacks, _get_async_display_callbacks
    
    def register_callbacks_concurrently(worker_id):
        """Register both sync and async callbacks from multiple threads."""
        register_display_callback(f'sync_test_{worker_id}', lambda: f'sync_{worker_id}', is_async=False)
        time.sleep(0.001)
        register_display_callback(f'async_test_{worker_id}', lambda: f'async_{worker_id}', is_async=True)
        return worker_id
    
    # Run 20 concurrent workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(register_callbacks_concurrently, i) for i in range(20)]
        concurrent.futures.wait(futures)
    
    # Verify all callbacks were registered successfully
    sync_callbacks = _get_sync_display_callbacks()
    async_callbacks = _get_async_display_callbacks()
    
    sync_count = len([k for k in sync_callbacks.keys() if k.startswith('sync_test_')])
    async_count = len([k for k in async_callbacks.keys() if k.startswith('async_test_')])
    
    assert sync_count == 20, f"Expected 20 sync callbacks, got {sync_count}"
    assert async_count == 20, f"Expected 20 async callbacks, got {async_count}"
    print(f"✅ Thread-safe callback registration: {sync_count} sync + {async_count} async callbacks")


def test_thread_safe_error_logging():
    """Test that error logging is thread-safe."""
    from praisonaiagents.main import _add_error_log, _get_error_logs
    
    def log_errors_concurrently(worker_id):
        """Log multiple errors from different threads."""
        for i in range(10):
            _add_error_log(f"Thread-{worker_id}: Error message #{i}")
            time.sleep(0.0001)
        return worker_id
    
    # Run 15 concurrent workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(log_errors_concurrently, i) for i in range(15)]
        concurrent.futures.wait(futures)
    
    # Verify all errors were logged
    all_errors = _get_error_logs()
    thread_errors = [e for e in all_errors if e.startswith('Thread-')]
    
    assert len(thread_errors) == 150, f"Expected 150 error logs, got {len(thread_errors)}"
    print(f"✅ Thread-safe error logging: {len(thread_errors)} errors from 15 threads")


if __name__ == '__main__':
    print("Testing thread safety fixes for main.py global state...")
    print("=" * 60)
    
    test_thread_safe_callback_registration()
    test_thread_safe_error_logging() 
    
    print("=" * 60)
    print("🎉 All thread safety tests passed!")