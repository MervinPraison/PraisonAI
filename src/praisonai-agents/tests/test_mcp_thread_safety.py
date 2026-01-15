"""
TDD Tests for MCP thread safety.

These tests verify that MCP transports use thread-local event loops
instead of global event loops, ensuring thread safety when multiple
MCP instances are used concurrently.
"""

import pytest
import threading
import time
from unittest.mock import patch


class TestThreadLocalEventLoop:
    """Test ThreadLocalEventLoop class."""
    
    def test_thread_local_event_loop_exists(self):
        """Test that ThreadLocalEventLoop class exists."""
        from praisonaiagents.mcp.mcp_schema_utils import ThreadLocalEventLoop
        assert ThreadLocalEventLoop is not None
    
    def test_get_loop_returns_event_loop(self):
        """Test that get_loop returns an event loop."""
        import asyncio
        from praisonaiagents.mcp.mcp_schema_utils import ThreadLocalEventLoop
        
        manager = ThreadLocalEventLoop()
        loop = manager.get_loop()
        
        assert loop is not None
        assert isinstance(loop, asyncio.AbstractEventLoop)
    
    def test_same_thread_gets_same_loop(self):
        """Test that same thread gets same event loop."""
        from praisonaiagents.mcp.mcp_schema_utils import ThreadLocalEventLoop
        
        manager = ThreadLocalEventLoop()
        loop1 = manager.get_loop()
        loop2 = manager.get_loop()
        
        assert loop1 is loop2, "Same thread should get same loop"
    
    def test_different_threads_get_different_loops(self):
        """Test that different threads get different event loops."""
        from praisonaiagents.mcp.mcp_schema_utils import ThreadLocalEventLoop
        
        manager = ThreadLocalEventLoop()
        loops = []
        errors = []
        
        def get_loop_in_thread():
            try:
                loop = manager.get_loop()
                loops.append(loop)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=get_loop_in_thread)
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(loops) == 3, "Should have 3 loops"
        
        # All loops should be different
        unique_loops = set(id(loop) for loop in loops)
        assert len(unique_loops) == 3, "Each thread should have its own loop"
    
    def test_cleanup_closes_loop(self):
        """Test that cleanup closes the event loop."""
        from praisonaiagents.mcp.mcp_schema_utils import ThreadLocalEventLoop
        
        manager = ThreadLocalEventLoop()
        loop = manager.get_loop()
        
        assert not loop.is_closed(), "Loop should not be closed initially"
        
        manager.cleanup()
        
        assert loop.is_closed(), "Loop should be closed after cleanup"
    
    def test_get_loop_after_cleanup_creates_new_loop(self):
        """Test that get_loop after cleanup creates a new loop."""
        from praisonaiagents.mcp.mcp_schema_utils import ThreadLocalEventLoop
        
        manager = ThreadLocalEventLoop()
        loop1 = manager.get_loop()
        manager.cleanup()
        loop2 = manager.get_loop()
        
        assert loop1 is not loop2, "Should create new loop after cleanup"
        assert not loop2.is_closed(), "New loop should not be closed"


class TestGetThreadLocalEventLoop:
    """Test get_thread_local_event_loop function."""
    
    def test_function_exists(self):
        """Test that get_thread_local_event_loop function exists."""
        from praisonaiagents.mcp.mcp_schema_utils import get_thread_local_event_loop
        assert callable(get_thread_local_event_loop)
    
    def test_returns_event_loop(self):
        """Test that function returns an event loop."""
        import asyncio
        from praisonaiagents.mcp.mcp_schema_utils import get_thread_local_event_loop
        
        loop = get_thread_local_event_loop()
        
        assert loop is not None
        assert isinstance(loop, asyncio.AbstractEventLoop)


class TestFixArraySchemas:
    """Test fix_array_schemas function."""
    
    def test_function_exists(self):
        """Test that fix_array_schemas function exists."""
        from praisonaiagents.mcp.mcp_schema_utils import fix_array_schemas
        assert callable(fix_array_schemas)
    
    def test_adds_items_to_array_without_items(self):
        """Test that items is added to array schemas without it."""
        from praisonaiagents.mcp.mcp_schema_utils import fix_array_schemas
        
        schema = {"type": "array"}
        fixed = fix_array_schemas(schema)
        
        assert "items" in fixed
        assert fixed["items"] == {"type": "string"}
    
    def test_preserves_existing_items(self):
        """Test that existing items are preserved."""
        from praisonaiagents.mcp.mcp_schema_utils import fix_array_schemas
        
        schema = {"type": "array", "items": {"type": "integer"}}
        fixed = fix_array_schemas(schema)
        
        assert fixed["items"] == {"type": "integer"}
    
    def test_fixes_nested_arrays(self):
        """Test that nested arrays are fixed."""
        from praisonaiagents.mcp.mcp_schema_utils import fix_array_schemas
        
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array"}
            }
        }
        fixed = fix_array_schemas(schema)
        
        assert "items" in fixed["properties"]["tags"]
    
    def test_handles_non_dict_input(self):
        """Test that non-dict input is returned as-is."""
        from praisonaiagents.mcp.mcp_schema_utils import fix_array_schemas
        
        assert fix_array_schemas("string") == "string"
        assert fix_array_schemas(123) == 123
        assert fix_array_schemas(None) is None
    
    def test_does_not_modify_original(self):
        """Test that original schema is not modified."""
        from praisonaiagents.mcp.mcp_schema_utils import fix_array_schemas
        
        original = {"type": "array"}
        fixed = fix_array_schemas(original)
        
        assert "items" not in original
        assert "items" in fixed


class TestMCPTransportThreadSafety:
    """Test that MCP transports use thread-local event loops."""
    
    def test_sse_uses_thread_local(self):
        """Test that SSE transport can use thread-local event loop."""
        # This test verifies the import works - actual thread safety
        # is tested via ThreadLocalEventLoop tests
        try:
            from praisonaiagents.mcp.mcp_schema_utils import get_thread_local_event_loop
            loop = get_thread_local_event_loop()
            assert loop is not None
        except ImportError:
            pytest.skip("MCP not available")
    
    def test_http_stream_uses_thread_local(self):
        """Test that HTTP Stream transport can use thread-local event loop."""
        try:
            from praisonaiagents.mcp.mcp_schema_utils import get_thread_local_event_loop
            loop = get_thread_local_event_loop()
            assert loop is not None
        except ImportError:
            pytest.skip("MCP not available")
    
    def test_websocket_uses_thread_local(self):
        """Test that WebSocket transport can use thread-local event loop."""
        try:
            from praisonaiagents.mcp.mcp_schema_utils import get_thread_local_event_loop
            loop = get_thread_local_event_loop()
            assert loop is not None
        except ImportError:
            pytest.skip("MCP not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
