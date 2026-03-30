"""
Tests for thread safety in praisonaiagents.

These tests verify that Agent chat_history and caches are thread-safe
when accessed concurrently, and that global state is properly protected.
"""
import sys
import threading
import time
import pytest


def clear_modules():
    """Clear all praisonai and litellm related modules from cache."""
    to_remove = [m for m in list(sys.modules.keys()) 
                 if 'praison' in m or 'litellm' in m]
    for mod in to_remove:
        del sys.modules[mod]


class TestLiteAgentThreadSafety:
    """Test thread safety of LiteAgent (no external deps)."""
    
    def test_concurrent_chat_history_access(self):
        """Multiple threads should safely access chat_history."""
        from praisonaiagents.lite import LiteAgent
        
        # Create agent with mock LLM
        call_count = [0]
        lock = threading.Lock()
        
        def mock_llm(messages):
            with lock:
                call_count[0] += 1
            time.sleep(0.01)  # Simulate some work
            return f"Response {call_count[0]}"
        
        agent = LiteAgent(llm_fn=mock_llm)
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(5):
                    response = agent.chat(f"Message from thread {thread_id}, iteration {i}")
                    assert response is not None
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check for errors
        assert len(errors) == 0, f"Thread errors: {errors}"
        
        # Verify history was updated (should have entries from all threads)
        assert len(agent.chat_history) > 0
    
    def test_concurrent_clear_history(self):
        """Clearing history while other threads are chatting should be safe."""
        from praisonaiagents.lite import LiteAgent
        
        def mock_llm(messages):
            return "Response"
        
        agent = LiteAgent(llm_fn=mock_llm)
        
        errors = []
        stop_flag = threading.Event()
        
        def chat_worker():
            try:
                while not stop_flag.is_set():
                    agent.chat("Hello")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(f"Chat error: {e}")
        
        def clear_worker():
            try:
                for _ in range(10):
                    time.sleep(0.01)
                    agent.clear_history()
            except Exception as e:
                errors.append(f"Clear error: {e}")
        
        # Start chat threads
        chat_threads = []
        for _ in range(2):
            t = threading.Thread(target=chat_worker)
            chat_threads.append(t)
            t.start()
        
        # Start clear thread
        clear_thread = threading.Thread(target=clear_worker)
        clear_thread.start()
        
        # Wait for clear thread to finish
        clear_thread.join()
        
        # Stop chat threads
        stop_flag.set()
        for t in chat_threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors}"


class TestAgentThreadSafety:
    """Test thread safety of main Agent class.
    
    Note: These tests use a mock LLM to avoid network calls.
    """
    
    def setup_method(self):
        """Set up test fixtures."""
        clear_modules()
    
    def test_agent_has_history_lock(self):
        """Agent should have a history lock for thread safety."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o-mini"  # Won't actually call
        )
        
        assert hasattr(agent, '_history_lock')
        assert isinstance(agent._history_lock, type(threading.Lock()))
    
    def test_agent_has_cache_lock(self):
        """Agent should have a cache lock for thread safety."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o-mini"
        )
        
        assert hasattr(agent, '_cache_lock')
        # RLock is a different type than Lock
        assert agent._cache_lock is not None


class TestMCPCleanup:
    """Test MCP cleanup and context manager support."""
    
    def test_mcp_has_context_manager(self):
        """MCP should support context manager protocol."""
        try:
            from praisonaiagents.mcp.mcp import MCP
        except ImportError:
            pytest.skip("MCP package not installed")
        
        assert hasattr(MCP, '__enter__')
        assert hasattr(MCP, '__exit__')
        assert hasattr(MCP, 'shutdown')
    
    def test_mcp_shutdown_method(self):
        """MCP should have a shutdown method."""
        try:
            from praisonaiagents.mcp.mcp import MCP
        except ImportError:
            pytest.skip("MCP package not installed")
        
        assert callable(getattr(MCP, 'shutdown', None))


class TestGlobalStateThreadSafety:
    """Test thread safety of global mutable state."""
    
    def test_trace_emitter_concurrent_access(self):
        """Multiple threads should safely access default trace emitter."""
        from praisonaiagents.trace.protocol import get_default_emitter, set_default_emitter, TraceEmitter, NoOpSink
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    emitter = get_default_emitter()
                    assert emitter is not None
                    
                    # Try setting a new emitter
                    new_emitter = TraceEmitter(sink=NoOpSink(), enabled=False)
                    set_default_emitter(new_emitter)
                    
                    # Verify we can get it back
                    retrieved = get_default_emitter()
                    assert retrieved is not None
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check for errors
        assert len(errors) == 0, f"Thread errors: {errors}"
    
    def test_display_callbacks_concurrent_registration(self):
        """Multiple threads should safely register display callbacks."""
        from praisonaiagents.main import register_display_callback, sync_display_callbacks, async_display_callbacks
        
        # Clear existing callbacks
        sync_display_callbacks.clear()
        async_display_callbacks.clear()
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    # Register sync callback
                    def sync_callback(**kwargs):
                        pass
                    register_display_callback(f"test_sync_{thread_id}_{i}", sync_callback, is_async=False)
                    
                    # Register async callback
                    async def async_callback(**kwargs):
                        pass
                    register_display_callback(f"test_async_{thread_id}_{i}", async_callback, is_async=True)
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check for errors
        assert len(errors) == 0, f"Thread errors: {errors}"
        
        # Verify callbacks were registered
        assert len(sync_display_callbacks) > 0
        assert len(async_display_callbacks) > 0
    
    def test_data_dir_cache_concurrent_access(self):
        """Multiple threads should safely access data directory cache."""
        from praisonaiagents.paths import get_data_dir, _clear_cache
        
        # Clear cache first
        _clear_cache()
        
        errors = []
        results = []
        
        def worker(thread_id):
            try:
                for i in range(5):
                    data_dir = get_data_dir()
                    results.append(data_dir)
                    assert data_dir is not None
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check for errors
        assert len(errors) == 0, f"Thread errors: {errors}"
        
        # All results should be the same (cached value)
        unique_results = set(str(r) for r in results)
        assert len(unique_results) == 1, f"Cache inconsistency: {unique_results}"
    
    def test_bus_concurrent_access(self):
        """Multiple threads should safely access event bus."""
        from praisonaiagents.bus.bus import get_default_bus, set_default_bus, EventBus
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(5):
                    # Get default bus
                    bus = get_default_bus()
                    assert bus is not None
                    
                    # Subscribe to events
                    def callback(event):
                        pass
                    
                    sub_id = bus.subscribe(callback, ["test_event"])
                    assert sub_id is not None
                    
                    # Publish an event
                    bus.publish("test_event", {"data": f"thread_{thread_id}_{i}"})
                    
                    # Unsubscribe
                    bus.unsubscribe(sub_id)
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(3):  # Fewer threads to avoid overwhelming the event bus
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check for errors
        assert len(errors) == 0, f"Thread errors: {errors}"
    
    def test_telemetry_performance_mode_concurrent_access(self):
        """Multiple threads should safely access performance mode flag."""
        try:
            from praisonaiagents.telemetry.integration import enable_performance_mode, disable_performance_mode, _performance_mode_enabled, _performance_mode_lock
        except ImportError:
            pytest.skip("Telemetry module not available")
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    if i % 2 == 0:
                        enable_performance_mode()
                    else:
                        disable_performance_mode()
                    
                    # Read the flag safely
                    with _performance_mode_lock:
                        current_mode = _performance_mode_enabled
                    
                    assert isinstance(current_mode, bool)
                    
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check for errors
        assert len(errors) == 0, f"Thread errors: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
