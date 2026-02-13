"""Unit tests for the Chainlit Bot UI streaming bridge.

Tests the core streaming bridge pattern (StreamEventEmitter → Queue → consumer)
WITHOUT requiring chainlit as a dependency. Uses mocks for all chainlit objects.
"""

import asyncio
import queue
import unittest
from unittest.mock import AsyncMock, MagicMock

from praisonaiagents.streaming.events import StreamEvent, StreamEventType, StreamEventEmitter


class TestStreamEventEmitterBridge(unittest.TestCase):
    """Test that StreamEventEmitter can bridge to an async consumer via Queue."""

    def test_sync_callback_puts_events_into_queue(self):
        """Core bridge pattern: sync callback → queue."""
        event_queue = queue.Queue()

        def relay(event):
            event_queue.put_nowait(event)

        emitter = StreamEventEmitter()
        emitter.add_callback(relay)

        # Emit events
        evt1 = StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello")
        evt2 = StreamEvent(type=StreamEventType.DELTA_TEXT, content=" world")
        evt3 = StreamEvent(type=StreamEventType.STREAM_END)

        emitter.emit(evt1)
        emitter.emit(evt2)
        emitter.emit(evt3)

        # Verify queue has all events
        self.assertEqual(event_queue.qsize(), 3)
        self.assertEqual(event_queue.get_nowait().content, "Hello")
        self.assertEqual(event_queue.get_nowait().content, " world")
        self.assertEqual(event_queue.get_nowait().type, StreamEventType.STREAM_END)

    def test_callback_cleanup_after_chat(self):
        """Verify callback is removed after agent.chat completes."""
        emitter = StreamEventEmitter()

        def relay(event):
            pass

        emitter.add_callback(relay)
        self.assertEqual(len(emitter._callbacks), 1)

        emitter.remove_callback(relay)
        self.assertEqual(len(emitter._callbacks), 0)

    def test_multiple_callbacks_isolation(self):
        """Multiple callbacks (e.g., gateway + chainlit) don't interfere."""
        q1 = queue.Queue()
        q2 = queue.Queue()

        def relay1(event):
            q1.put_nowait(event)

        def relay2(event):
            q2.put_nowait(event)

        emitter = StreamEventEmitter()
        emitter.add_callback(relay1)
        emitter.add_callback(relay2)

        evt = StreamEvent(type=StreamEventType.DELTA_TEXT, content="test")
        emitter.emit(evt)

        self.assertEqual(q1.qsize(), 1)
        self.assertEqual(q2.qsize(), 1)
        self.assertEqual(q1.get_nowait().content, "test")
        self.assertEqual(q2.get_nowait().content, "test")


class TestStreamConsumer(unittest.TestCase):
    """Test the async consumer that reads from queue and dispatches to Chainlit."""

    def test_delta_text_calls_stream_token(self):
        """DELTA_TEXT events should call msg.stream_token(content)."""
        event_queue = queue.Queue()
        event_queue.put_nowait(StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello"))
        event_queue.put_nowait(StreamEvent(type=StreamEventType.DELTA_TEXT, content=" world"))

        # Use sentinel to signal end
        _STREAM_END = object()
        event_queue.put_nowait(_STREAM_END)

        mock_msg = MagicMock()
        mock_msg.stream_token = AsyncMock()
        mock_msg.update = AsyncMock()

        async def consume():
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue

                if event is _STREAM_END:
                    break

                if hasattr(event, 'type') and event.type == StreamEventType.DELTA_TEXT:
                    content = getattr(event, 'content', '') or ''
                    if content:
                        await mock_msg.stream_token(content)

        asyncio.run(consume())

        self.assertEqual(mock_msg.stream_token.call_count, 2)
        mock_msg.stream_token.assert_any_call("Hello")
        mock_msg.stream_token.assert_any_call(" world")

    def test_tool_call_events(self):
        """DELTA_TOOL_CALL events should be captured."""
        events = [
            StreamEvent(
                type=StreamEventType.DELTA_TOOL_CALL,
                tool_call={"index": 0, "name": "search_web", "arguments": '{"query":'}
            ),
            StreamEvent(
                type=StreamEventType.DELTA_TOOL_CALL,
                tool_call={"index": 0, "arguments": '"python"}'}
            ),
            StreamEvent(type=StreamEventType.TOOL_CALL_END),
        ]

        captured_tool_calls = {}
        for event in events:
            if event.type == StreamEventType.DELTA_TOOL_CALL:
                tc = event.tool_call or {}
                idx = tc.get("index", 0)
                if idx not in captured_tool_calls:
                    captured_tool_calls[idx] = {"name": tc.get("name"), "args": ""}
                args = tc.get("arguments", "")
                if args:
                    captured_tool_calls[idx]["args"] += args

        self.assertIn(0, captured_tool_calls)
        self.assertEqual(captured_tool_calls[0]["name"], "search_web")
        self.assertEqual(captured_tool_calls[0]["args"], '{"query":"python"}')

    def test_error_event(self):
        """ERROR events should be captured."""
        event = StreamEvent(type=StreamEventType.ERROR, error="Connection failed")
        self.assertEqual(event.type, StreamEventType.ERROR)
        self.assertEqual(event.error, "Connection failed")

    def test_stream_end_signals_completion(self):
        """STREAM_END should signal the consumer to stop."""
        event_queue = queue.Queue()
        event_queue.put_nowait(StreamEvent(type=StreamEventType.STREAM_END))

        _STREAM_END = object()
        event_queue.put_nowait(_STREAM_END)

        consumed = []

        async def consume():
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    break
                if event is _STREAM_END:
                    break
                consumed.append(event)

        asyncio.run(consume())
        self.assertEqual(len(consumed), 1)
        self.assertEqual(consumed[0].type, StreamEventType.STREAM_END)


class TestNoChainlitInCoreSdk(unittest.TestCase):
    """Verify chainlit is NOT imported in core SDK."""

    def test_no_chainlit_import_in_core(self):
        """grep-equivalent: no 'import chainlit' in praisonaiagents/ source."""
        import os
        core_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "praisonaiagents"
        )

        violations = []
        for root, dirs, files in os.walk(core_path):
            # Skip venv, __pycache__, .egg-info
            dirs[:] = [d for d in dirs if d not in ("venv", "__pycache__", ".egg-info", "praisonaiagents.egg-info")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            stripped = line.strip()
                            if stripped.startswith("#"):
                                continue
                            if "import chainlit" in stripped or "from chainlit" in stripped:
                                violations.append(f"{fpath}:{i}: {stripped}")
                except Exception:
                    pass

        self.assertEqual(
            violations, [],
            "Core SDK must not import chainlit. Found:\n" + "\n".join(violations)
        )


class TestStreamEventTypes(unittest.TestCase):
    """Verify all event types used by the bridge exist."""

    def test_required_event_types_exist(self):
        self.assertTrue(hasattr(StreamEventType, "DELTA_TEXT"))
        self.assertTrue(hasattr(StreamEventType, "DELTA_TOOL_CALL"))
        self.assertTrue(hasattr(StreamEventType, "TOOL_CALL_END"))
        self.assertTrue(hasattr(StreamEventType, "STREAM_END"))
        self.assertTrue(hasattr(StreamEventType, "ERROR"))
        self.assertTrue(hasattr(StreamEventType, "FIRST_TOKEN"))

    def test_stream_event_fields(self):
        """StreamEvent has all fields needed by the bridge."""
        evt = StreamEvent(
            type=StreamEventType.DELTA_TEXT,
            content="hello",
            tool_call={"name": "test"},
            error="err",
            agent_id="agent1",
        )
        self.assertEqual(evt.content, "hello")
        self.assertEqual(evt.tool_call, {"name": "test"})
        self.assertEqual(evt.error, "err")
        self.assertEqual(evt.agent_id, "agent1")


if __name__ == "__main__":
    unittest.main()
