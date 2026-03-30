#!/usr/bin/env python3
"""
Test the thread safety fixes we implemented for global mutable state.
"""
import threading
import time
import contextvars
from concurrent.futures import ThreadPoolExecutor, as_completed

# Test our context variable fixes
def test_error_logs_thread_safety():
    """Test that error logs work correctly in concurrent scenarios without crashing."""
    from praisonaiagents.main import error_logs, add_error_log, get_error_logs
    
    errors_list = []
    
    def worker(thread_id):
        try:
            # Test both old API (backward compatibility) and new API
            error_logs.append(f"Thread {thread_id} old API error")  # Old way
            add_error_log(f"Thread {thread_id} new API error")      # New way
            
            # These operations should not crash or cause race conditions
            current_errors = get_error_logs()
            return True, len(current_errors)
        except Exception as e:
            errors_list.append(f"Thread {thread_id}: {e}")
            return False, 0
    
    # Run in multiple threads
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker, i) for i in range(3)]
        for future in as_completed(futures):
            results.append(future.result())
    
    print("Error logs thread safety test:")
    for i, (success, count) in enumerate(results):
        print(f"  Thread {i}: {'✓' if success else '✗'} - {count} errors seen")
        assert success, f"Thread {i} failed"
    
    if errors_list:
        print(f"Errors encountered: {errors_list}")
        assert False, "Some threads encountered errors"
    
    print("✅ Error logs API works safely in concurrent access")


def test_server_registry_thread_safety():
    """Test that server registry handles concurrent access safely."""
    from praisonaiagents._server_registry import get_server_registry
    
    registry = get_server_registry()
    
    def worker(thread_id):
        port = 8000 + thread_id
        
        # Initialize port
        registry.initialize_port(port)
        
        # Register multiple endpoints concurrently  
        results = []
        for i in range(3):
            endpoint = f"/agent_{thread_id}_{i}"
            agent_id = f"agent_{thread_id}_{i}"
            success = registry.register_endpoint(port, endpoint, agent_id)
            results.append((endpoint, success))
        
        # Mark server as started
        registry.mark_server_started(port)
        
        return port, results, registry.is_server_started(port)
    
    # Run in multiple threads
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker, i) for i in range(3)]
        for future in as_completed(futures):
            results.append(future.result())
    
    print("\nServer registry thread safety test:")
    for port, endpoint_results, server_started in results:
        print(f"  Port {port}: server_started={server_started}")
        for endpoint, success in endpoint_results:
            print(f"    {endpoint}: {'✓' if success else '✗'}")
            assert success, f"Failed to register {endpoint}"
        assert server_started, f"Server on port {port} not marked as started"
    
    print("✅ Server registry is thread-safe")


def test_callback_thread_safety():
    """Test that display callbacks work correctly in concurrent scenarios."""
    from praisonaiagents.main import sync_display_callbacks, set_sync_display_callback, get_sync_display_callbacks
    
    errors_list = []
    
    def worker(thread_id):
        try:
            # Test both old API (backward compatibility) and new API
            callback_name = f"test_callback_{thread_id}"
            callback_fn = lambda x: f"Thread {thread_id} callback: {x}"
            
            # Old way
            sync_display_callbacks[callback_name + "_old"] = callback_fn
            
            # New way  
            set_sync_display_callback(callback_name + "_new", callback_fn)
            
            # These operations should not crash or cause race conditions
            callbacks = get_sync_display_callbacks()
            return True, len(callbacks)
        except Exception as e:
            errors_list.append(f"Thread {thread_id}: {e}")
            return False, 0
    
    # Run in multiple threads
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker, i) for i in range(3)]
        for future in as_completed(futures):
            results.append(future.result())
    
    print("\nCallback thread safety test:")
    for i, (success, count) in enumerate(results):
        print(f"  Thread {i}: {'✓' if success else '✗'} - {count} callbacks seen")
        assert success, f"Thread {i} failed"
    
    if errors_list:
        print(f"Errors encountered: {errors_list}")
        assert False, "Some threads encountered errors"
    
    print("✅ Callbacks API works safely in concurrent access")


def test_lazy_cache_thread_safety():
    """Test that lazy caches handle concurrent access safely."""
    from praisonaiagents.tools import duckduckgo  # This should trigger lazy loading
    from praisonaiagents.agent import Agent  # This should trigger lazy loading
    
    def worker(thread_id):
        try:
            # Try to import something that uses lazy loading
            import praisonaiagents.tools as tools
            import praisonaiagents.agent as agent_module
            
            # Access lazy-loaded items
            _ = getattr(tools, 'duckduckgo', None)
            _ = getattr(agent_module, 'Agent', None)
            
            return True, None
        except Exception as e:
            return False, str(e)
    
    # Run in multiple threads
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, i) for i in range(5)]
        for future in as_completed(futures):
            results.append(future.result())
    
    print("\nLazy cache thread safety test:")
    for i, (success, error) in enumerate(results):
        print(f"  Thread {i}: {'✓' if success else '✗'} {error or ''}")
        assert success, f"Thread {i} failed: {error}"
    
    print("✅ Lazy caches handle concurrent access safely")


if __name__ == "__main__":
    print("Testing thread safety fixes...")
    
    test_error_logs_thread_safety()
    test_server_registry_thread_safety()
    test_callback_thread_safety()
    test_lazy_cache_thread_safety()
    
    print("\n🎉 All thread safety tests passed!")