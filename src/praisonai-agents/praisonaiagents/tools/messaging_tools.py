"""
Send Message tool for PraisonAI Agents (Issue #2183).

A lightweight, agent-callable built-in that lets a running agent proactively
reach the user mid-task — e.g. "I've finished the report, sending it to you on
Telegram" — or discover where the user can be reached.

The tool resolves the active gateway messenger from the per-turn session
context (``register_outbound_messenger``), so it has no heavy third-party
dependencies. When no gateway is running (CLI / one-shot runs), it fails
cleanly with an explanatory message instead of raising.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import send_message

    agent = Agent(
        name="assistant",
        instructions="You can proactively message the user on their channels.",
        tools=[send_message],
    )
    # During a task the model can do:
    #   send_message(action="list")
    #   send_message("slack:#ops", "Deploy finished ✅ MEDIA:/tmp/report.pdf")
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import List, Optional

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

_NO_GATEWAY_MSG = (
    "No active gateway: send_message is only available inside a running "
    "bot/gateway (e.g. Telegram, Slack, Discord). It is unavailable for "
    "CLI/one-shot runs."
)

_MEDIA_RE = re.compile(r"MEDIA:(\S+)")


def _run_async(coro):
    """Run an async coroutine from sync code from any threading posture.

    Three cases, each correct for a real gateway/bot:

    1. No running loop in *this* thread, but a gateway loop is running in
       another thread (the common case: agent tools execute in an executor
       worker thread while the bot's event loop runs elsewhere). The
       messenger's async resources are bound to that loop, so we schedule the
       coroutine on it via ``run_coroutine_threadsafe`` and block on the
       result. This avoids the "Task got Future attached to a different loop"
       error a fresh loop would cause.

    2. No running loop anywhere we can see (CLI / one-shot). Drive the
       coroutine directly with ``asyncio.run``.

    3. Called *on* a running loop's own thread. We cannot block that thread on
       the loop (it would deadlock), so we run the coroutine on a fresh loop in
       a worker thread. This path is unusual for real bots (whose tools run in
       executor threads) and is primarily exercised by tests.
    """
    import concurrent.futures

    # Is there a loop running in THIS thread?
    try:
        asyncio.get_running_loop()
        on_loop_thread = True
    except RuntimeError:
        on_loop_thread = False

    if not on_loop_thread:
        # Prefer an existing gateway loop running in another thread so the
        # coroutine executes where its async resources are bound.
        loop = _get_gateway_loop()
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        # Nothing running anywhere — safe to drive directly.
        return asyncio.run(coro)

    # We are ON a running loop's thread; blocking it would deadlock. Run on a
    # fresh loop in a worker thread instead.
    def _runner():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_runner).result()


def _get_gateway_loop():
    """Return the running gateway event loop if one was registered, else None.

    The gateway/bot may register its loop in the session context so sync tools
    invoked from executor threads can reach loop-bound async resources. Falls
    back to ``None`` when unavailable.
    """
    try:
        from ..session.context import get_gateway_loop
    except Exception:
        return None
    try:
        return get_gateway_loop()
    except Exception:
        return None


def _parse_media(message: str) -> tuple[str, Optional[List[str]]]:
    """Split ``MEDIA:<path>`` directives from the message text.

    Supports one or more ``MEDIA:<path>`` tokens anywhere in the message.
    Paths may contain spaces because only the ``MEDIA:`` directive itself is
    removed (not split on whitespace). Returns the cleaned text and a list of
    media paths (or ``None`` when there are none).
    """
    if "MEDIA:" not in message:
        return message, None

    media: List[str] = []
    remaining = message
    for m in _MEDIA_RE.finditer(message):
        path = m.group(1).strip()
        if path:
            media.append(path)
        remaining = remaining.replace(m.group(0), "", 1)

    text = " ".join(remaining.split()).strip()
    return text, (media or None)


def send_message(
    target: str = "origin",
    message: str = "",
    action: str = "send",
) -> str:
    """Proactively message the user through the active gateway.

    Use this to reach the user mid-task on the channel this conversation came
    from, or on another channel they have configured. Requires a running
    bot/gateway; it is unavailable for plain CLI/one-shot runs.

    Args:
        target: Symbolic destination. One of:
            - "origin": the chat this conversation came from
            - "<platform>": that platform's home channel (e.g. "telegram")
            - "<platform>:<chat_id>[:<thread_id>]": an explicit chat
            - "<alias>": a friendly alias for a known target
        message: The text to send. Append " MEDIA:<path>" to attach a local
            file, e.g. "Report ready MEDIA:/tmp/report.pdf".
        action: "send" to deliver a message (default), or "list" to return the
            targets currently reachable so you can pick a destination.

    Returns:
        For action="send": a short human-readable summary of the delivery.
        For action="list": a JSON array of reachable targets.
    """
    try:
        from ..session.context import get_outbound_messenger

        messenger = get_outbound_messenger()
        if messenger is None:
            return _NO_GATEWAY_MSG

        if action == "list":
            targets = messenger.list_targets()
            return json.dumps([t.as_dict() for t in targets])

        if action != "send":
            return f"Unknown action '{action}'. Use 'send' or 'list'."

        text, media = _parse_media(message)
        result = _run_async(messenger.send(target, text, media=media))
        return result.summary or (
            f"Sent to {result.target or target}." if result.ok
            else f"Failed to send to {target}: {result.detail or 'unknown error'}"
        )
    except Exception as e:
        logger.error("send_message failed: %s", e, exc_info=True)
        return f"Error sending message: {e}"


__all__ = ["send_message"]
