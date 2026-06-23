"""
Tests for the agent-facing send_message tool (Issue #2183).

Covers the lightweight built-in that resolves the active gateway messenger
from the per-turn session context and delivers proactive messages.
"""

import asyncio
import json

import pytest

from praisonaiagents.tools import send_message
from praisonaiagents.tools.messaging_tools import _parse_media
from praisonaiagents.gateway import (
    OutboundMessengerProtocol,
    DeliveryResult,
    TargetInfo,
)
from praisonaiagents.session.context import (
    register_outbound_messenger,
    get_outbound_messenger,
    clear_outbound_messenger,
)


class FakeMessenger:
    """Minimal OutboundMessengerProtocol implementation for tests."""

    def __init__(self):
        self.sent = []

    async def send(self, target, text, *, media=None):
        self.sent.append((target, text, media))
        return DeliveryResult(
            ok=True, target=target, summary=f"Delivered to {target}"
        )

    def list_targets(self):
        return [
            TargetInfo(
                target="telegram:home",
                platform="telegram",
                kind="home",
                label="Telegram",
            )
        ]


def test_messenger_satisfies_protocol():
    assert isinstance(FakeMessenger(), OutboundMessengerProtocol)


def test_no_gateway_fails_cleanly():
    # No messenger registered -> graceful message, not an exception.
    result = send_message("origin", "hello")
    assert "No active gateway" in result


def test_send_routes_to_messenger():
    messenger = FakeMessenger()
    token = register_outbound_messenger(messenger)
    try:
        out = send_message("slack:#ops", "Deploy finished")
        assert out == "Delivered to slack:#ops"
        assert messenger.sent == [("slack:#ops", "Deploy finished", None)]
    finally:
        clear_outbound_messenger(token)
    assert get_outbound_messenger() is None


def test_list_returns_json_targets():
    messenger = FakeMessenger()
    token = register_outbound_messenger(messenger)
    try:
        out = send_message(action="list")
        parsed = json.loads(out)
        assert parsed == [
            {
                "target": "telegram:home",
                "platform": "telegram",
                "kind": "home",
                "label": "Telegram",
            }
        ]
    finally:
        clear_outbound_messenger(token)


def test_media_directive_is_parsed():
    messenger = FakeMessenger()
    token = register_outbound_messenger(messenger)
    try:
        send_message("origin", "Report ready MEDIA:/tmp/report.pdf")
        target, text, media = messenger.sent[0]
        assert text == "Report ready"
        assert media == ["/tmp/report.pdf"]
    finally:
        clear_outbound_messenger(token)


def test_unknown_action_message():
    messenger = FakeMessenger()
    token = register_outbound_messenger(messenger)
    try:
        out = send_message("origin", "hi", action="frobnicate")
        assert "Unknown action" in out
    finally:
        clear_outbound_messenger(token)


def test_parse_media_helper():
    assert _parse_media("no media here") == ("no media here", None)
    assert _parse_media("a MEDIA:/x b MEDIA:/y") == ("a b", ["/x", "/y"])


def test_parse_media_preserves_message_text_with_path():
    # Path token is removed cleanly; surrounding text is preserved verbatim.
    text, media = _parse_media("Report ready MEDIA:/tmp/report.pdf thanks")
    assert text == "Report ready thanks"
    assert media == ["/tmp/report.pdf"]


def test_send_works_inside_running_loop():
    messenger = FakeMessenger()

    async def main():
        token = register_outbound_messenger(messenger)
        try:
            return send_message("origin", "hi")
        finally:
            clear_outbound_messenger(token)

    result = asyncio.run(main())
    assert result == "Delivered to origin"


class LoopBoundMessenger:
    """Messenger holding an asyncio resource bound to a specific loop.

    Mimics a real bot whose HTTP client/lock is created on the gateway loop.
    Sending from a *different* event loop would raise the classic
    "bound to a different event loop" RuntimeError, so this exercises the
    cross-thread ``run_coroutine_threadsafe`` path.
    """

    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.lock = asyncio.Lock()  # bound to self.loop
        self.sent = []

    async def send(self, target, text, *, media=None):
        async with self.lock:  # raises if driven on a different loop
            self.sent.append((target, text, media))
            return DeliveryResult(ok=True, target=target, summary=f"OK {target}")

    def list_targets(self):
        return []


def test_send_routes_to_gateway_loop_from_worker_thread():
    """A real bot pattern: loop in one thread, sync tool called from another."""
    import threading
    from praisonaiagents.session.context import (
        register_gateway_loop,
        clear_gateway_loop,
    )

    ready = threading.Event()
    holder = {}

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        holder["loop"] = loop
        loop.call_soon(ready.set)
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    ready.wait(timeout=5)
    loop = holder["loop"]

    # Build the loop-bound messenger ON the gateway loop.
    fut = asyncio.run_coroutine_threadsafe(
        _make_loop_bound_messenger(), loop
    )
    messenger = fut.result(timeout=5)

    register_gateway_loop(loop)
    mtoken = register_outbound_messenger(messenger)
    try:
        # Called from the main (non-loop) thread, as a sync tool would be.
        out = send_message("origin", "hi from worker")
        assert out == "OK origin"
        assert messenger.sent == [("origin", "hi from worker", None)]
    finally:
        clear_outbound_messenger(mtoken)
        clear_gateway_loop()
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=5)


async def _make_loop_bound_messenger():
    return LoopBoundMessenger()
