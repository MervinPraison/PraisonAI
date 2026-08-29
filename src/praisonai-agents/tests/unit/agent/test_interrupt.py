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
        ready_event = threading.Event()
        done_event = threading.Event()
        
        def worker():
            # Wait for checker to be ready
            ready_event.wait(timeout=1)
            controller.request("thread_cancel")
            results.append("requested")
            done_event.set()
        
        def checker():
            # Signal ready and wait for interrupt
            ready_event.set()
            done_event.wait(timeout=1)
            assert controller.is_set()
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

    def test_is_set_is_stable_when_not_used(self):
        """Test that repeated checks do not mutate state."""
        controller = InterruptController()
        
        # Should consistently return False and None
        for _ in range(1000):
            assert not controller.is_set()
            assert controller.reason is None

    def test_event_cleared_after_interrupted_turn_ends(self):
        """A stale interrupt must not carry into the next turn's tools.

        Regression: the ``event`` (exposed to running tool bodies) previously
        stayed set after an interrupted turn, so a reused controller aborted
        subprocesses launched by the NEXT turn. Ending the interrupted turn now
        clears the underlying flag so a fresh turn starts uninterrupted.
        """
        controller = InterruptController()

        turn = controller._begin_turn()
        controller.request("user_stop")
        assert controller.event.is_set()
        assert controller._turn_is_cancelled(turn)

        # The interrupted turn ends without an explicit clear().
        controller._end_turn(turn)
        assert not controller.event.is_set()
        assert controller.reason is None

        # A brand-new turn must NOT be seen as cancelled.
        next_turn = controller._begin_turn()
        assert not controller.event.is_set()
        assert not controller._turn_is_cancelled(next_turn)
        controller._end_turn(next_turn)

    def test_event_stays_set_while_another_turn_still_cancelled(self):
        """Ending one cancelled turn must not release a still-cancelled sibling."""
        controller = InterruptController()
        t1 = controller._begin_turn()
        t2 = controller._begin_turn()
        controller.request("user_stop")  # cancels both active turns

        controller._end_turn(t1)
        # t2 is still cancelled, so the shared event must remain set.
        assert controller.event.is_set()
        assert controller._turn_is_cancelled(t2)

        controller._end_turn(t2)
        assert not controller.event.is_set()

    def test_event_is_optional_capability_protocol(self):
        """The base protocol stays event-free; the cancellable one requires it."""
        from praisonaiagents.agent.interrupt import (
            CancellableInterruptControllerProtocol,
        )

        controller = InterruptController()
        assert isinstance(controller, CancellableInterruptControllerProtocol)

        class MinimalController:
            def request(self, reason="user"):
                pass

            def clear(self):
                pass

            def is_set(self):
                return False

            @property
            def reason(self):
                return None

            def check(self):
                pass

        # A controller without ``event`` is NOT cancellable-capable but must not
        # raise — the runtime probes via getattr(..., 'event', None).
        assert not isinstance(MinimalController(), CancellableInterruptControllerProtocol)


class TestLLMLoopCancellation:
    """The litellm tool loop (llm/llm.py) must honour the InterruptController.

    Regression tests for #2748: /stop must promptly halt a mid-flight run on
    every provider path, not just the OpenAI completion path.
    """

    def _make_llm(self):
        try:
            from praisonaiagents.llm.llm import LLM
        except Exception:
            pytest.skip("litellm not installed")
        try:
            return LLM(model="anthropic/claude-3-haiku-20240307")
        except Exception:
            pytest.skip("litellm not available or model construction failed")

    def test_sync_loop_returns_cancelled_outcome(self):
        """A pre-set controller short-circuits get_response before any LLM call."""
        llm = self._make_llm()
        controller = InterruptController()
        controller.request("user_stop")

        result = llm.get_response(
            prompt="hello",
            tools=None,
            verbose=False,
            stream=False,
            cancel_token=controller,
        )

        assert isinstance(result, str)
        assert "interrupted" in result.lower()
        assert "user_stop" in result

    @pytest.mark.asyncio
    async def test_async_loop_returns_cancelled_outcome(self):
        """A pre-set controller short-circuits get_response_async before any LLM call."""
        llm = self._make_llm()
        controller = InterruptController()
        controller.request("user_stop")

        result = await llm.get_response_async(
            prompt="hello",
            tools=None,
            verbose=False,
            stream=False,
            cancel_token=controller,
        )

        assert isinstance(result, str)
        assert "interrupted" in result.lower()
        assert "user_stop" in result
