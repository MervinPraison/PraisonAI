"""
Focused unit tests for AutoGenAdapter task_callback dispatch.

These exercise ``AutoGenAdapter._fire_task_callback`` directly, so they need no
live AutoGen chat service or ``autogen`` install. They guard the contract that:

- sync callbacks receive the event payload,
- async (coroutine) callbacks are actually run (not left un-awaited), and
- a raising callback is swallowed and logged, never propagated into the chat.
"""

import unittest


class TestAutoGenFireTaskCallback(unittest.TestCase):
    """Guard sync/async execution and exception isolation of task_callback."""

    def setUp(self):
        from praisonai.framework_adapters.autogen_adapter import AutoGenAdapter
        self.adapter = AutoGenAdapter()

    def test_sync_callback_receives_payload(self):
        seen = []
        payload = {"event": "task_prepared", "task_spec": "x"}

        self.adapter._fire_task_callback(seen.append, payload)

        self.assertEqual(seen, [payload])

    def test_async_callback_is_executed(self):
        seen = []

        async def cb(payload):
            seen.append(payload)

        payload = {"event": "task_completed", "summary": "done"}
        self.adapter._fire_task_callback(cb, payload)

        # The coroutine must have actually run (not returned un-awaited).
        self.assertEqual(seen, [payload])

    def test_sync_callback_exception_is_swallowed(self):
        def boom(_payload):
            raise ValueError("boom")

        # Must not propagate — a broken observability sink can't abort the chat.
        self.adapter._fire_task_callback(boom, {"event": "task_prepared"})

    def test_async_callback_exception_is_swallowed(self):
        async def boom(_payload):
            raise ValueError("boom")

        self.adapter._fire_task_callback(boom, {"event": "task_completed"})


if __name__ == "__main__":
    unittest.main()
