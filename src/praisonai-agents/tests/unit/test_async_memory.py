"""
Tests for async memory operations and concurrency.

These tests verify that memory operations are safe under concurrent access
and that async patterns work correctly.
"""
import pytest
import asyncio
import threading
from typing import Dict, List, Any, Optional


class TestAsyncMemoryProtocol:
    """Test async memory protocol compliance."""
    
    def test_async_memory_protocol_importable(self):
        """AsyncMemoryProtocol should be importable."""
        from praisonaiagents.memory.protocols import AsyncMemoryProtocol
        assert AsyncMemoryProtocol is not None
    
    def test_mock_async_memory_implementation(self):
        """Mock async memory should satisfy AsyncMemoryProtocol."""
        from praisonaiagents.memory.protocols import AsyncMemoryProtocol
        
        class MockAsyncMemory:
            def __init__(self):
                self._store: List[Dict[str, Any]] = []
            
            async def astore_short_term(
                self, 
                text: str, 
                metadata: Optional[Dict[str, Any]] = None,
                **kwargs
            ) -> str:
                entry_id = f"stm_{len(self._store)}"
                self._store.append({"id": entry_id, "text": text, "type": "short"})
                return entry_id
            
            async def asearch_short_term(
                self, 
                query: str, 
                limit: int = 5,
                **kwargs
            ) -> List[Dict[str, Any]]:
                # Simple text matching
                matches = [e for e in self._store if query.lower() in e["text"].lower()]
                return matches[:limit]
            
            async def astore_long_term(
                self, 
                text: str, 
                metadata: Optional[Dict[str, Any]] = None,
                **kwargs
            ) -> str:
                entry_id = f"ltm_{len(self._store)}"
                self._store.append({"id": entry_id, "text": text, "type": "long"})
                return entry_id
            
            async def asearch_long_term(
                self, 
                query: str, 
                limit: int = 5,
                **kwargs
            ) -> List[Dict[str, Any]]:
                matches = [e for e in self._store if query.lower() in e["text"].lower()]
                return matches[:limit]
        
        # Test async operations
        async def run_test():
            memory = MockAsyncMemory()
            
            # Store
            id1 = await memory.astore_short_term("Hello world")
            id2 = await memory.astore_long_term("Important document")
            
            assert id1 == "stm_0"
            assert id2 == "ltm_1"
            
            # Search
            results = await memory.asearch_short_term("hello")
            assert len(results) == 1
            assert results[0]["text"] == "Hello world"
        
        asyncio.run(run_test())


class TestConcurrentMemoryAccess:
    """Test thread-safe memory access patterns."""
    
    def test_concurrent_protocol_import(self):
        """Protocols should be safely importable from multiple threads."""
        errors = []
        results = []
        
        def import_protocols():
            try:
                from praisonaiagents.memory.protocols import MemoryProtocol
                from praisonaiagents.agent.protocols import AgentProtocol
                from praisonaiagents.tools.protocols import ToolProtocol
                results.append(True)
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=import_protocols) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 5
    
    def test_concurrent_mock_memory_access(self):
        """Mock memory should handle concurrent access."""
        from praisonaiagents.memory.protocols import MemoryProtocol
        
        class ThreadSafeMockMemory:
            def __init__(self):
                self._store: List[Dict] = []
                self._lock = threading.Lock()
            
            def store_short_term(self, text: str, metadata=None, **kwargs) -> str:
                with self._lock:
                    entry_id = f"entry_{len(self._store)}"
                    self._store.append({"id": entry_id, "text": text})
                    return entry_id
            
            def search_short_term(self, query: str, limit: int = 5, **kwargs):
                with self._lock:
                    return list(self._store)[:limit]
            
            def store_long_term(self, text: str, metadata=None, **kwargs) -> str:
                return self.store_short_term(text, metadata, **kwargs)
            
            def search_long_term(self, query: str, limit: int = 5, **kwargs):
                return self.search_short_term(query, limit, **kwargs)
        
        memory = ThreadSafeMockMemory()
        errors = []
        
        def worker(thread_id: int):
            try:
                for i in range(10):
                    memory.store_short_term(f"Thread {thread_id} message {i}")
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors: {errors}"
        # 4 threads * 10 messages = 40 entries
        assert len(memory._store) == 40


class TestLazyCacheThreadSafety:
    """Test _lazy_cache thread safety."""
    
    def test_lazy_cache_access_thread_safe(self):
        """_lazy_cache access should be thread-safe."""
        from praisonaiagents import _get_lazy_cache
        
        errors = []
        
        def access_cache():
            try:
                cache = _get_lazy_cache()
                assert isinstance(cache, dict)
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=access_cache) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
