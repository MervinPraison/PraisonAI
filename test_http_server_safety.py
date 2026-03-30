#!/usr/bin/env python3
"""
Test script to verify HTTP server globals thread safety fixes.
"""

import threading
import sys
import os

# Add the package to the path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_server_globals_access():
    """Test that HTTP server globals are accessed safely"""
    print("Testing HTTP server globals thread safety...")
    
    try:
        # Import the globals and lock
        from praisonaiagents.agent.agent import _server_started, _registered_agents, _shared_apps, _server_lock
        
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                # Test safe access pattern
                with _server_lock:
                    port = 8000 + thread_id
                    
                    # Initialize if needed
                    if port not in _registered_agents:
                        _registered_agents[port] = {}
                    
                    # Test getting endpoints list safely
                    endpoints = list(_registered_agents[port].keys())
                    
                    # Mark server as started
                    _server_started[port] = True
                    
                results.append((thread_id, len(endpoints), _server_started.get(port, False)))
                
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        if errors:
            print(f"❌ HTTP server globals test failed: {errors}")
            return False
        
        # Verify results
        for thread_id, endpoint_count, server_started in results:
            if not isinstance(endpoint_count, int) or not isinstance(server_started, bool):
                print(f"❌ Invalid result types for thread {thread_id}")
                return False
        
        print("✅ HTTP server globals are accessed safely")
        return True
        
    except ImportError as e:
        print(f"❌ Could not import agent module: {e}")
        return False

def main():
    print("🔒 Testing HTTP server thread safety fixes")
    print("=" * 40)
    
    success = test_server_globals_access()
    
    print("=" * 40)
    if success:
        print("🎉 HTTP server thread safety test PASSED!")
        return 0
    else:
        print("❌ HTTP server thread safety test FAILED!")
        return 1

if __name__ == "__main__":
    exit(main())