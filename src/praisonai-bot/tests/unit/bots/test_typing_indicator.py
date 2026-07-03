"""Unit tests for the typing indicator renewal utility."""

import asyncio
import sys
import os
import pytest

# Ensure the praisonai package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from praisonai_bot.bots._typing_indicator import TypingIndicator, with_typing_renewal


class TestTypingIndicator:
    """Tests for the TypingIndicator class."""

    @pytest.mark.asyncio
    async def test_start_creates_background_task(self):
        calls = []

        async def _typing():
            calls.append(1)

        indicator = TypingIndicator(interval=0.05)
        await indicator.start(_typing)
        assert indicator._task is not None
        assert not indicator._task.done()
        indicator.cancel()
        await asyncio.sleep(0.02)

    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_cancel_stops_loop(self):
        calls = []

        async def _typing():
            calls.append(1)

        indicator = TypingIndicator(interval=0.05)
        await indicator.start(_typing)
        await asyncio.sleep(0.12)  # Let it fire ~2 times
        count_at_cancel = len(calls)
        indicator.cancel()
        await asyncio.sleep(0.15)  # Extra time after cancel
        assert len(calls) == count_at_cancel or len(calls) == count_at_cancel + 1

    @pytest.mark.asyncio
    async def test_start_idempotent_when_already_running(self):
        """Calling start() while already running should be a no-op."""
        calls = []

        async def _typing():
            calls.append(1)

        indicator = TypingIndicator(interval=1.0)
        await indicator.start(_typing)
        first_task = indicator._task

        await indicator.start(_typing)  # Second start — should not replace task
        assert indicator._task is first_task

        indicator.cancel()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_sync_typing_func_is_called(self):
        calls = []

        def _sync_typing():
            calls.append(1)

        indicator = TypingIndicator(interval=0.001)
        await indicator.start(_sync_typing)
        await asyncio.sleep(0.05)  # fast_sleep makes this near-instant, still lets loop iterate
        indicator.cancel()
        assert len(calls) >= 1

    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_loop_continues_after_typing_func_exception(self):
        """Errors in the typing func should not stop the renewal loop."""
        error_calls = 0
        ok_calls = []

        async def _flaky():
            nonlocal error_calls
            if error_calls < 2:
                error_calls += 1
                raise RuntimeError("network blip")
            ok_calls.append(1)

        indicator = TypingIndicator(interval=0.04)
        await indicator.start(_flaky)
        await asyncio.sleep(0.30)
        indicator.cancel()
        assert len(ok_calls) >= 1, "Loop should have continued after errors"

    @pytest.mark.asyncio
    async def test_task_is_done_after_cancel_and_await(self):
        async def _typing():
            pass

        indicator = TypingIndicator(interval=0.05)
        await indicator.start(_typing)
        indicator.cancel()
        if indicator._task is not None:
            try:
                await indicator._task
            except (asyncio.CancelledError, Exception):
                pass
        assert indicator._task is None or indicator._task.done()


class TestWithTypingRenewal:
    """Tests for the with_typing_renewal helper."""

    @pytest.mark.asyncio
    async def test_returns_operation_result(self):
        async def _typing():
            pass

        async def _op():
            return "hello"

        result = await with_typing_renewal(
            typing_func=_typing,
            operation_coro=_op(),
            interval=0.05,
        )
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_typing_called_at_least_once(self):
        calls = []

        async def _typing():
            calls.append(1)

        async def _op():
            await asyncio.sleep(0.001)  # yield to let typing task run first

        await with_typing_renewal(
            typing_func=_typing,
            operation_coro=_op(),
            interval=0.001,
        )
        assert len(calls) >= 1

    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_typing_called_multiple_times_for_long_op(self):
        calls = []

        async def _typing():
            calls.append(1)

        await with_typing_renewal(
            typing_func=_typing,
            operation_coro=asyncio.sleep(0.25),
            interval=0.05,
        )
        assert len(calls) >= 3

    @pytest.mark.asyncio
    async def test_exception_propagates_and_task_cleaned_up(self):
        calls = []

        async def _typing():
            calls.append(1)

        async def _failing():
            await asyncio.sleep(0.001)
            raise ValueError("agent error")

        with pytest.raises(ValueError, match="agent error"):
            await with_typing_renewal(
                typing_func=_typing,
                operation_coro=_failing(),
                interval=0.02,
            )

    @pytest.mark.asyncio
    async def test_task_fully_cleaned_up_after_completion(self):
        """After with_typing_renewal returns, the background task must be done."""
        created_indicators = []

        original_init = TypingIndicator.__init__

        def _tracking_init(self, interval=4.0):
            original_init(self, interval=interval)
            created_indicators.append(self)

        TypingIndicator.__init__ = _tracking_init
        try:
            async def _typing():
                pass

            async def _op():
                await asyncio.sleep(0.001)

            await with_typing_renewal(
                typing_func=_typing,
                operation_coro=_op(),
                interval=0.02,
            )

            await asyncio.sleep(0.02)  # Give event loop a tick to clean up
            for indicator in created_indicators:
                assert indicator._task is None or indicator._task.done(), \
                    "Background task must be done after with_typing_renewal returns"
        finally:
            TypingIndicator.__init__ = original_init

    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_interval_parameter_respected(self):
        call_times = []

        async def _typing():
            call_times.append(asyncio.get_event_loop().time())

        await with_typing_renewal(
            typing_func=_typing,
            operation_coro=asyncio.sleep(0.30),
            interval=0.10,
        )

        assert len(call_times) >= 2
        for i in range(1, len(call_times)):
            gap = call_times[i] - call_times[i - 1]
            # Allow ±50% tolerance for CI timing jitter
            assert gap >= 0.05, f"Gap {gap:.3f}s too small (expected ~0.10s)"
            assert gap <= 0.20, f"Gap {gap:.3f}s too large (expected ~0.10s)"

    @pytest.mark.asyncio
    async def test_none_result_is_returned(self):
        """Coroutines that return None should work correctly."""
        async def _typing():
            pass

        async def _op():
            pass  # returns None

        result = await with_typing_renewal(
            typing_func=_typing,
            operation_coro=_op(),
            interval=0.05,
        )
        assert result is None

