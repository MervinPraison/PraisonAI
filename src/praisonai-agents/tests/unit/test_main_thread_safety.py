"""
Additional thread safety tests for main.py callback registries.

Tests the fixes made to global mutable state in main.py.
"""
import threading
import time
import pytest


def test_callback_registry_has_locks():
    """Test that callback registries are protected by locks."""
    import praisonaiagents.main as main
    
    # Verify lock exists
    assert hasattr(main, '_callbacks_lock')
    assert isinstance(main._callbacks_lock, type(threading.RLock()))


def test_concurrent_callback_registration():
    """Test concurrent callback registration is thread-safe."""
    import praisonaiagents.main as main
    
    # Clear initial state
    main.sync_display_callbacks.clear()
    main.async_display_callbacks.clear()
    
    errors = []
    num_threads = 5
    num_iterations = 10
    
    def callback_worker(thread_id):
        try:
            for i in range(num_iterations):
                # Register callbacks
                main.register_display_callback(
                    f"sync_{thread_id}_{i}", 
                    lambda **kwargs: None, 
                    is_async=False
                )
                main.register_display_callback(
                    f"async_{thread_id}_{i}", 
                    lambda **kwargs: None, 
                    is_async=True
                )
                time.sleep(0.001)  # Small delay
        except Exception as e:
            errors.append(f"Thread {thread_id}: {e}")
    
    # Start threads
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=callback_worker, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    # Check results
    assert len(errors) == 0, f"Thread errors: {errors}"
    assert len(main.sync_display_callbacks) == num_threads * num_iterations
    assert len(main.async_display_callbacks) == num_threads * num_iterations


def test_concurrent_approval_callback_registration():
    """Test concurrent approval callback registration is thread-safe."""
    import praisonaiagents.main as main
    
    errors = []
    num_threads = 5
    
    def approval_worker(thread_id):
        try:
            for i in range(10):
                main.register_approval_callback(
                    lambda func, args, risk: f"approval_{thread_id}_{i}"
                )
                time.sleep(0.001)
        except Exception as e:
            errors.append(f"Thread {thread_id}: {e}")
    
    # Start threads
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=approval_worker, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    # Check results
    assert len(errors) == 0, f"Thread errors: {errors}"
    assert main.approval_callback is not None


def test_callback_execution_with_concurrent_registration():
    """Test callback execution while registration happens concurrently."""
    import praisonaiagents.main as main
    
    # Set up test callback
    call_count = [0]
    call_lock = threading.Lock()
    
    def test_callback(**kwargs):
        with call_lock:
            call_count[0] += 1
    
    main.register_display_callback('test_concurrent', test_callback, is_async=False)
    
    errors = []
    
    def execution_worker():
        try:
            for _ in range(20):
                main.execute_sync_callback('test_concurrent', data='test')
                time.sleep(0.001)
        except Exception as e:
            errors.append(f"Execution error: {e}")
    
    def registration_worker():
        try:
            for i in range(20):
                main.register_display_callback(
                    f'test_reg_{i}', 
                    lambda **kwargs: None, 
                    is_async=False
                )
                time.sleep(0.001)
        except Exception as e:
            errors.append(f"Registration error: {e}")
    
    # Start both execution and registration threads
    threads = [
        threading.Thread(target=execution_worker),
        threading.Thread(target=registration_worker),
    ]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    # Check results
    assert len(errors) == 0, f"Thread errors: {errors}"
    assert call_count[0] == 20  # All executions should succeed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])