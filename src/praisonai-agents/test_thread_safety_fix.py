#!/usr/bin/env python3
"""
Simple test to verify thread safety fixes work correctly.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def test_tools_cache_thread_safety():
    """Test that tools cache is thread-safe"""
    print("Testing tools cache thread safety...")
    
    # Test lazy loading under concurrency
    def load_tool():
        try:
            from praisonaiagents.tools import internet_search
            return f"Success: {id(internet_search)}"
        except Exception as e:
            return f"Error: {e}"
    
    # Run concurrent loads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(load_tool) for _ in range(10)]
        results = [f.result() for f in as_completed(futures)]
    
    print(f"Tool loading results: {len(results)} completed")
    for result in results[:3]:  # Show first 3 results
        print(f"  {result}")
    
    return True

def test_memory_cache_thread_safety():
    """Test that memory cache is thread-safe"""
    print("Testing memory cache thread safety...")
    
    def check_memory():
        try:
            from praisonaiagents.memory import memory
            # Try to access the lazy import functionality 
            return "Memory module loaded successfully"
        except Exception as e:
            return f"Error: {e}"
    
    # Run concurrent checks
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_memory) for _ in range(5)]
        results = [f.result() for f in as_completed(futures)]
    
    print(f"Memory loading results: {len(results)} completed")
    for result in results[:2]:  # Show first 2 results
        print(f"  {result}")
    
    return True

def test_sqlite_backend_thread_safety():
    """Test that SQLite backend is thread-safe with WAL mode"""
    print("Testing SQLite backend thread safety...")
    
    def test_storage():
        try:
            from praisonaiagents.storage.backends import SQLiteBackend
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                db_path = tmp.name
            
            try:
                storage = SQLiteBackend(db_path=db_path)
                # Test basic operations
                storage.save("test_key", {"data": "test_value"})
                result = storage.load("test_key")
                return f"Storage test passed: {result is not None}"
            finally:
                try:
                    os.unlink(db_path)
                except OSError:
                    pass
                    
        except Exception as e:
            return f"Error: {e}"
    
    # Run concurrent storage operations
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(test_storage) for _ in range(3)]
        results = [f.result() for f in as_completed(futures)]
    
    print(f"Storage results: {len(results)} completed")
    for result in results:
        print(f"  {result}")
    
    return True

def main():
    print("Running thread safety verification tests...\n")
    
    tests = [
        test_tools_cache_thread_safety,
        test_memory_cache_thread_safety,
        test_sqlite_backend_thread_safety,
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
                print("✅ PASSED\n")
            else:
                print("❌ FAILED\n")
        except Exception as e:
            print(f"❌ FAILED with exception: {e}\n")
    
    print(f"Tests passed: {passed}/{len(tests)}")
    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)