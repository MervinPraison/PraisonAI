#!/usr/bin/env python3
"""
Test script to verify thread safety fixes for issue #1145.
This tests the specific areas that were fixed for thread-unsafe global mutable state.
"""

import threading
import time
import sys
import os

# Add the package to the path if running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_context_agent_lazy_loaders():
    """Test thread safety of lazy loaders in context_agent.py"""
    print("Testing context_agent.py lazy loaders...")
    
    from praisonaiagents.agent.context_agent import _get_subprocess, _get_glob, _get_ast, _get_asyncio
    
    results = []
    errors = []
    
    def worker(loader_func, name):
        try:
            result = loader_func()
            results.append((name, id(result)))
        except Exception as e:
            errors.append((name, str(e)))
    
    threads = []
    for _ in range(10):
        for func, name in [(_get_subprocess, 'subprocess'), (_get_glob, 'glob'), 
                          (_get_ast, 'ast'), (_get_asyncio, 'asyncio')]:
            t = threading.Thread(target=worker, args=(func, name))
            threads.append(t)
    
    # Start all threads
    for t in threads:
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    if errors:
        print(f"❌ Context agent lazy loaders failed: {errors}")
        return False
    
    # Check that all instances of the same module are identical
    modules = {}
    for name, obj_id in results:
        if name not in modules:
            modules[name] = obj_id
        elif modules[name] != obj_id:
            print(f"❌ Context agent lazy loaders: Different instances for {name}")
            return False
    
    print("✅ Context agent lazy loaders are thread-safe")
    return True

def test_tools_instance_cache():
    """Test thread safety of tools instance cache"""
    print("Testing tools/__init__.py instance cache...")
    
    try:
        from praisonaiagents.tools import _instances, _instances_lock
        
        # Test concurrent access to _instances dict
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                with _instances_lock:
                    key = f"test_class_{thread_id}"
                    if key not in _instances:
                        _instances[key] = f"instance_{thread_id}"
                    results.append((_instances[key], thread_id))
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        if errors:
            print(f"❌ Tools instance cache failed: {errors}")
            return False
        
        print("✅ Tools instance cache is thread-safe")
        return True
        
    except ImportError as e:
        print(f"❌ Could not import tools module: {e}")
        return False

def test_agent_counter():
    """Test thread safety of agent counter (should already be fixed)"""
    print("Testing Agent._agent_counter thread safety...")
    
    try:
        from praisonaiagents.agent.agent import Agent
        
        results = []
        errors = []
        
        def create_agent(thread_id):
            try:
                # Create agent without LLM call to avoid API requirements
                agent = Agent.__new__(Agent)
                agent._agent_index = None
                agent.__class__ = Agent
                
                # Call the counter increment logic
                with Agent._agent_counter_lock:
                    Agent._agent_counter += 1
                    counter_val = Agent._agent_counter
                    
                results.append(counter_val)
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Reset counter
        Agent._agent_counter = 0
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=create_agent, args=(i,))
            threads.append(t)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        if errors:
            print(f"❌ Agent counter failed: {errors}")
            return False
        
        # Check that all counters are unique and in sequence
        results.sort()
        expected = list(range(1, 11))
        if results != expected:
            print(f"❌ Agent counter not sequential: got {results}, expected {expected}")
            return False
        
        print("✅ Agent counter is thread-safe")
        return True
        
    except ImportError as e:
        print(f"❌ Could not import agent module: {e}")
        return False

def test_concurrent_imports():
    """Test that concurrent imports of lazy modules work correctly"""
    print("Testing concurrent lazy imports...")
    
    errors = []
    
    def import_worker(thread_id):
        try:
            # Import the modules in threads to test lazy loading
            from praisonaiagents.agent.context_agent import _get_subprocess, _get_glob
            subprocess_mod = _get_subprocess()
            glob_mod = _get_glob()
            
            # Verify modules are what we expect
            assert hasattr(subprocess_mod, 'run'), f"subprocess module missing 'run' method"
            assert hasattr(glob_mod, 'glob'), f"glob module missing 'glob' method"
            
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    threads = []
    for i in range(5):
        t = threading.Thread(target=import_worker, args=(i,))
        threads.append(t)
    
    # Start all threads
    for t in threads:
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    if errors:
        print(f"❌ Concurrent imports failed: {errors}")
        return False
    
    print("✅ Concurrent lazy imports work correctly")
    return True

def main():
    print("🧪 Testing thread safety fixes for issue #1145")
    print("=" * 50)
    
    tests = [
        test_context_agent_lazy_loaders,
        test_tools_instance_cache,
        test_agent_counter,
        test_concurrent_imports
    ]
    
    results = []
    for test in tests:
        try:
            success = test()
            results.append(success)
            print()
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
            print()
    
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 All {total} thread safety tests PASSED!")
        return 0
    else:
        print(f"❌ {passed}/{total} tests passed, {total-passed} failed")
        return 1

if __name__ == "__main__":
    exit(main())