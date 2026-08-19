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
- Bounded retry: an ephemeral tick (cron / CI / scale-to-zero) has no persistent
  process to drain a durable outbox, so instead of a fire-and-forget send each
  HTTP call is retried in-process with exponential backoff, honouring a
  server-mandated ``Retry-After`` on a 429. Only transient failures (5xx / 429 /
  network) are retried; a permanent failure (bad token, 4xx) raises immediately
  so the executor records ``delivery_error`` without wasting the tick. Retries
  reuse the same battle-tested ``bots._resilience`` primitives interactive
  replies use, so behaviour stays consistent across paths.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
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


def _home_channel_from_registry(platform: str) -> str:
    """Read a home channel id for ``platform`` from the gateway's state file.

    The gateway persists home channels to ``~/.praisonai/state/home_channels.json``
    (see :class:`praisonai_bot.gateway.home_channels.HomeChannelRegistry`). Out of
    process there is no live registry, but the file is plain JSON, so a bare
    ``deliver: telegram`` target set through the gateway still resolves without a
    ``{PLATFORM}_HOME_CHANNEL`` env var. Read lazily and defensively — any error
    (missing file, bad JSON) simply yields no id, never raising into delivery.
    """
    try:
        path = Path.home() / ".praisonai" / "state" / "home_channels.json"
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        entry = data.get(platform)
        if isinstance(entry, dict):
            return str(entry.get("chat_id", "") or "")
    except Exception:  # pragma: no cover - defensive: never break delivery
        return ""
    return ""


def _resolve_chat_id(
    target: "DeliveryTarget", platform: str, *home_env: str,
) -> str:
    """Resolve the concrete chat id for ``target``.

    Resolution order, matching the live gateway as closely as an out-of-process
    sender can:
    1. explicit ``channel_id`` on the target (``telegram:123456``)
    2. a ``{PLATFORM}_HOME_CHANNEL`` env var (env-first so a deployment can
       override without touching the gateway's state file)
    3. the gateway's persisted ``HomeChannelRegistry`` state file, so a home
       channel registered via the live gateway also works out of process.
    """
    if target.channel_id:
        return target.channel_id
    from_env = _env(*home_env)
    if from_env:
        return from_env
    return _home_channel_from_registry(platform)


class _HttpSendError(RuntimeError):
    """HTTP send failure that carries the status code.

    Exposing ``status``/``headers`` lets the shared ``bots._resilience``
    classifiers recognise a transient 5xx/429 (and honour a ``Retry-After``)
    even when the response body has no recognisable text, so the retry decision
    matches the interactive path exactly. The raw ``Retry-After`` header is
    preserved verbatim (rather than pre-parsed to a float) so ``server_retry_after``
    honours both integer-seconds *and* HTTP-date forms via its own parser — a
    plain ``float(raw)`` here would silently discard an HTTP-date delay.
    """

    def __init__(self, status: int, body: str = "", retry_after: Optional[str] = None):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        # Mirror the response-header shape ``server_retry_after`` reads from, so
        # it can parse an integer-seconds *or* HTTP-date ``Retry-After`` itself.
        if retry_after is not None:
            self.headers = {"Retry-After": retry_after}


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
                raise _HttpSendError(status, body)
    except urllib.error.HTTPError as e:  # 4xx/5xx
        body = e.read().decode("utf-8", "replace")[:500] if e.fp else ""
        # Preserve the raw ``Retry-After`` verbatim so ``server_retry_after``
        # honours both integer-seconds and HTTP-date forms; parsing to a float
        # here would silently drop an HTTP-date delay (429 under throttling).
        raw = None
        try:
            raw = e.headers.get("Retry-After") if e.headers else None
        except Exception:  # pragma: no cover - defensive: headers always dict-like
            raw = None
        retry_after = str(raw) if raw is not None else None
        raise _HttpSendError(e.code, body, retry_after) from e


_MAX_ATTEMPTS = 4


async def _run_sync(fn: Callable[[], None]) -> None:
    """Run a blocking send ``fn`` off the event loop, retrying transient failures.

    A standalone tick has no persistent process to drain a durable outbox, so
    durability here is a bounded in-process retry: ``fn`` is attempted up to
    :data:`_MAX_ATTEMPTS` times with exponential backoff. A server-mandated
    ``Retry-After`` (e.g. a Telegram/HTTP 429) is honoured over the computed
    backoff. Only errors classified transient by the shared resilience helper
    are retried; a permanent failure (bad token, 4xx) raises on the first
    attempt so the executor records ``delivery_error`` promptly rather than
    burning the whole tick on a doomed send.
    """
    try:
        from ..bots._resilience import (
            BackoffPolicy,
            compute_backoff,
            is_recoverable_error,
            server_retry_after,
        )
    except Exception:  # pragma: no cover - defensive: helper ships in-package
        await asyncio.to_thread(fn)
        return

    policy = BackoffPolicy(initial_ms=1000, max_ms=20000, factor=2.0, jitter=0.2)
    attempt = 0
    while True:
        attempt += 1
        try:
            await asyncio.to_thread(fn)
            return
        except Exception as e:  # noqa: BLE001 — classify then re-raise/retry
            if attempt >= _MAX_ATTEMPTS or not is_recoverable_error(e):
                raise
            wait = server_retry_after(e)
            if wait is None:
                wait = compute_backoff(policy, attempt)
            logger.warning(
                "Standalone delivery attempt %d/%d failed (%s); retrying in %.1fs",
                attempt, _MAX_ATTEMPTS, e, wait,
            )
            await asyncio.sleep(wait)


def _chunk(text: str, max_length: int) -> list:
    """Split ``text`` into platform-sized chunks.

    Reuses the same markdown-aware :func:`praisonai_bot.bots._chunk.chunk_message`
    the live adapters use so a long scheduled result is delivered as multiple
    messages instead of being rejected by the platform's size limit. Falls back
    to a plain character split if that helper is unavailable (defensive; it ships
    in the same package).
    """
    if len(text) <= max_length:
        return [text]
    try:
        from ..bots._chunk import chunk_message

        return chunk_message(text, max_length=max_length)
    except Exception:  # pragma: no cover - defensive
        return [text[i:i + max_length] for i in range(0, len(text), max_length)]


# ── per-platform senders ─────────────────────────────────────────────


_TELEGRAM_LIMIT = 4096
_SLACK_LIMIT = 39000
_DISCORD_LIMIT = 2000
_WHATSAPP_LIMIT = 4096
_SIGNAL_LIMIT = 2000


async def _telegram_send(target: "DeliveryTarget", text: str) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set for standalone delivery")
    chat_id = _resolve_chat_id(target, "telegram", "TELEGRAM_HOME_CHANNEL")
    if not chat_id:
        raise RuntimeError("no chat id for telegram standalone delivery")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for part in _chunk(text, _TELEGRAM_LIMIT):
        payload: dict = {"chat_id": chat_id, "text": part}
        if target.thread_id:
            payload["message_thread_id"] = target.thread_id
        await _run_sync(lambda p=payload: _post_json(url, p))


async def _slack_send(target: "DeliveryTarget", text: str) -> None:
    token = _env("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set for standalone delivery")
    channel = _resolve_chat_id(target, "slack", "SLACK_HOME_CHANNEL")
    if not channel:
        raise RuntimeError("no channel for slack standalone delivery")
    headers = {"Authorization": f"Bearer {token}"}

    def _send(payload: dict) -> None:
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

    for part in _chunk(text, _SLACK_LIMIT):
        payload = {"channel": channel, "text": part}
        if target.thread_id:
            payload["thread_ts"] = target.thread_id
        await _run_sync(lambda p=payload: _send(p))


async def _discord_send(target: "DeliveryTarget", text: str) -> None:
    token = _env("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN not set for standalone delivery")
    channel_id = _resolve_chat_id(target, "discord", "DISCORD_HOME_CHANNEL")
    if not channel_id:
        raise RuntimeError("no channel id for discord standalone delivery")
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    # Preserve threaded context: when the target carries a thread_id, reply to
    # that message via ``message_reference`` so the scheduled result stays in
    # the same conversation instead of landing bare in the parent channel —
    # matching how Telegram/Slack standalone senders preserve ``thread_id``.
    # ``fail_if_not_exists=false`` degrades gracefully to a normal message if
    # the referenced message is gone rather than dropping delivery.
    reference: Optional[dict] = None
    if target.thread_id:
        reference = {
            "message_id": str(target.thread_id),
            "channel_id": str(channel_id),
            "fail_if_not_exists": False,
        }
    for part in _chunk(text, _DISCORD_LIMIT):
        payload: dict = {"content": part}
        if reference is not None:
            payload["message_reference"] = reference
        await _run_sync(lambda p=payload: _post_json(url, p, headers=headers))


async def _whatsapp_send(target: "DeliveryTarget", text: str) -> None:
    # WhatsApp Cloud API: same token/phone-number-id env the live adapter uses
    # (see bots/whatsapp.py). The chat id is the recipient phone number, resolved
    # via the standard target/env/registry order like every other platform.
    token = _env("WHATSAPP_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN not set for standalone delivery")
    phone_number_id = _env("WHATSAPP_PHONE_NUMBER_ID")
    if not phone_number_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID not set for standalone delivery")
    to = _resolve_chat_id(target, "whatsapp", "WHATSAPP_HOME_CHANNEL")
    if not to:
        raise RuntimeError("no recipient for whatsapp standalone delivery")
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}

    def _send(part: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": part},
        }
        # NOTE: a scheduler ``thread_id`` is a generic conversation identifier,
        # NOT a WhatsApp message id. WhatsApp's ``context.message_id`` requires a
        # real inbound message id to quote-reply; feeding it a generic thread id
        # yields an invalid id the Cloud API rejects (a permanent 4xx). The live
        # adapter (bots/whatsapp.py) only sets ``context`` from an explicit
        # ``reply_to`` message id, never from ``thread_id`` — so we mirror that
        # and simply omit the context here.
        _post_json(url, payload, headers=headers)

    for part in _chunk(text, _WHATSAPP_LIMIT):
        await _run_sync(lambda p=part: _send(p))


async def _signal_send(target: "DeliveryTarget", text: str) -> None:
    # Signal via a signal-cli-rest-api bridge (see bots/signal.py). The bridge
    # url and sender account come from the same env the live adapter uses; the
    # target channel id is the recipient number/group.
    account = _env("SIGNAL_ACCOUNT")
    if not account:
        raise RuntimeError("SIGNAL_ACCOUNT not set for standalone delivery")
    bridge = _env("SIGNAL_BRIDGE_URL") or "http://localhost:8080"
    recipient = _resolve_chat_id(target, "signal", "SIGNAL_HOME_CHANNEL")
    if not recipient:
        raise RuntimeError("no recipient for signal standalone delivery")
    url = f"{bridge.rstrip('/')}/v2/send"
    for part in _chunk(text, _SIGNAL_LIMIT):
        payload = {"number": account, "message": part, "recipients": [recipient]}
        await _run_sync(lambda p=payload: _post_json(url, p))


# Platform → standalone sender. Keyed by the same lowercase platform names the
# adapter registry uses so a ``deliver: telegram`` target resolves uniformly.
_STANDALONE_SENDERS: dict = {
    "telegram": _telegram_send,
    "slack": _slack_send,
    "discord": _discord_send,
    "whatsapp": _whatsapp_send,
    "signal": _signal_send,
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
