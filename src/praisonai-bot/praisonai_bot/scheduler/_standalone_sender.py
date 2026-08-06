"""
Out-of-process ("standalone") delivery senders for scheduled jobs.

When ``praisonai schedule tick`` runs without a live gateway (a plain OS cron
entry, a CI runner, a scale-to-zero deployment), the executor has no live bot
adapter to route a job's ``deliver:`` target through. These stateless senders
close that gap: each is a single token-authenticated HTTP call that pushes the
result to the platform using nothing but the same ``{PLATFORM}_BOT_TOKEN`` env
the gateway already uses — no adapter, no SDK, no persistent process.

Design notes:
- Zero new dependencies: the HTTP call uses :mod:`urllib.request` from the
  stdlib, so a standalone sender works in the leanest environment.
- The token (and, for a bare-platform target, the home chat id) is read from
  the environment lazily *at send time*, so importing this module is free and a
  platform with no token simply has no standalone sender available.
- Fully additive: this is only consulted as a fallback when the executor has no
  live ``delivery_handler``; the live-adapter path is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.scheduler.models import DeliveryTarget

logger = logging.getLogger(__name__)

# Standalone sender = async callable ``(target, text) -> None`` that raises on
# a failed send so the executor records ``delivery_error`` exactly as it does
# for the live-adapter path.
StandaloneSender = Callable[["DeliveryTarget", str], Awaitable[None]]

_HTTP_TIMEOUT = 30.0


def _env(*names: str) -> str:
    """Return the first non-empty environment value among ``names``."""
    for name in names:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def _resolve_chat_id(target: "DeliveryTarget", *home_env: str) -> str:
    """Resolve the concrete chat id for ``target``.

    Prefers the explicit ``channel_id`` on the target (``telegram:123456``) and
    falls back to a ``{PLATFORM}_HOME_CHANNEL`` env var for a bare-platform
    token (``deliver: telegram``) so home-channel delivery works out of process.
    """
    if target.channel_id:
        return target.channel_id
    return _env(*home_env)


def _post_json(url: str, payload: dict, *, headers: Optional[dict] = None) -> None:
    """POST ``payload`` as JSON to ``url``, raising on a non-2xx response.

    Runs synchronously; callers dispatch it off the event loop via
    :func:`asyncio.to_thread` so a slow send does not block the ticker.
    """
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as resp:
            status = getattr(resp, "status", 200)
            if status >= 300:
                body = resp.read().decode("utf-8", "replace")[:500]
                raise RuntimeError(f"HTTP {status}: {body}")
    except urllib.error.HTTPError as e:  # 4xx/5xx
        body = e.read().decode("utf-8", "replace")[:500] if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


async def _run_sync(fn: Callable[[], None]) -> None:
    """Run a blocking send ``fn`` off the event loop."""
    import asyncio

    await asyncio.to_thread(fn)


# ── per-platform senders ─────────────────────────────────────────────


async def _telegram_send(target: "DeliveryTarget", text: str) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set for standalone delivery")
    chat_id = _resolve_chat_id(target, "TELEGRAM_HOME_CHANNEL")
    if not chat_id:
        raise RuntimeError("no chat id for telegram standalone delivery")
    payload: dict = {"chat_id": chat_id, "text": text}
    if target.thread_id:
        payload["message_thread_id"] = target.thread_id
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    await _run_sync(lambda: _post_json(url, payload))


async def _slack_send(target: "DeliveryTarget", text: str) -> None:
    token = _env("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set for standalone delivery")
    channel = _resolve_chat_id(target, "SLACK_HOME_CHANNEL")
    if not channel:
        raise RuntimeError("no channel for slack standalone delivery")
    payload = {"channel": channel, "text": text}
    if target.thread_id:
        payload["thread_ts"] = target.thread_id
    headers = {"Authorization": f"Bearer {token}"}

    def _send() -> None:
        # Slack returns HTTP 200 with ``{"ok": false, "error": ...}`` on a
        # logical failure, so inspect the body rather than only the status.
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except ValueError:
            raise RuntimeError(f"unexpected slack response: {body[:200]}")
        if not parsed.get("ok", False):
            raise RuntimeError(f"slack error: {parsed.get('error', 'unknown')}")

    await _run_sync(_send)


async def _discord_send(target: "DeliveryTarget", text: str) -> None:
    token = _env("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN not set for standalone delivery")
    channel_id = _resolve_chat_id(target, "DISCORD_HOME_CHANNEL")
    if not channel_id:
        raise RuntimeError("no channel id for discord standalone delivery")
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    await _run_sync(lambda: _post_json(url, {"content": text}, headers=headers))


# Platform → standalone sender. Keyed by the same lowercase platform names the
# adapter registry uses so a ``deliver: telegram`` target resolves uniformly.
_STANDALONE_SENDERS: dict = {
    "telegram": _telegram_send,
    "slack": _slack_send,
    "discord": _discord_send,
}


def resolve_standalone_sender(channel: str) -> Optional[StandaloneSender]:
    """Return the standalone sender for ``channel``, or ``None`` if none exists.

    ``None`` means the executor has no out-of-process delivery path for that
    platform and falls back to logging a warning (its prior behaviour when no
    live adapter is wired), so an unsupported platform never raises here.
    """
    if not channel:
        return None
    return _STANDALONE_SENDERS.get(channel.lower())
