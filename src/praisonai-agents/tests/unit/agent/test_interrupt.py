"""
Tests for InterruptController.

Ensures thread safety, cooperative cancellation, and zero overhead when not used.
"""

import threading
import time
import pytest
from praisonaiagents.agent.interrupt import InterruptController


class TestInterruptController:
    
    def test_basic_functionality(self):
        """Test basic interrupt request and check."""
        controller = InterruptController()
        
        # Initially not set
        assert not controller.is_set()
        assert controller.reason is None
        
        # Request interruption
        controller.request("test_reason")
        assert controller.is_set()
        assert controller.reason == "test_reason"
        
        # Clear interruption
        controller.clear()
        assert not controller.is_set()
        assert controller.reason is None

    def test_default_reason(self):
        """Test default reason when none provided."""
        controller = InterruptController()
        controller.request()
        assert controller.reason == "user"

    def test_check_raises_when_set(self):
        """Test that check() raises InterruptedError when set."""
        controller = InterruptController()
        
        # Should not raise when not set
        controller.check()
        
        # Should raise when set
        controller.request("test")
        with pytest.raises(InterruptedError, match="Operation cancelled: test"):
            controller.check()

    def test_thread_safety(self):
        """Test thread-safe operations."""
        controller = InterruptController()
        results = []
        
        def worker():
            # Wait a bit then request interrupt
            time.sleep(0.1)
            controller.request("thread_cancel")
            results.append("requested")
        
        def checker():
            # Keep checking until interrupted
            while not controller.is_set():
                time.sleep(0.05)
            results.append(f"cancelled: {controller.reason}")
        
        # Start threads
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=checker)
        
        t1.start()
        t2.start()
        
        t1.join(timeout=1)
        t2.join(timeout=1)
        
        # Verify both completed
        assert "requested" in results
        assert "cancelled: thread_cancel" in results

    def test_multiple_requests(self):
        """Test that multiple requests preserve the first reason."""
        controller = InterruptController()
        
        controller.request("first")
        controller.request("second")
        
        assert controller.reason == "first"
        assert controller.is_set()

    def test_clear_resets_state(self):
        """Test that clear completely resets state."""
        controller = InterruptController()
        
        controller.request("test")
        assert controller.is_set()
        assert controller.reason == "test"
        
        controller.clear()
        assert not controller.is_set()
        assert controller.reason is None
        
        # Can be reused
        controller.request("new_reason")
        assert controller.reason == "new_reason"

    def test_zero_overhead_when_not_used(self):
        """Test that creation and is_set() have minimal overhead."""
        import time
        
        # Test creation overhead
        start = time.perf_counter()
        for _ in range(1000):
            controller = InterruptController()
        creation_time = time.perf_counter() - start
        
        # Test check overhead  
        controller = InterruptController()
        start = time.perf_counter()
        for _ in range(10000):
            controller.is_set()
        check_time = time.perf_counter() - start
        
        # Should be very fast (< 1ms each)
        assert creation_time < 0.001
        assert check_time < 0.001