"""
Resilience utilities for PraisonAI bots.

Provides exponential backoff, recoverable error detection,
and connection monitoring primitives.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class BackoffPolicy:
    """Exponential backoff configuration.
    
    Attributes:
        initial_ms: Initial delay in milliseconds
        max_ms: Maximum delay in milliseconds
        factor: Multiplicative factor per attempt
        jitter: Random jitter fraction (0.0 - 1.0)
        max_attempts: Max retry attempts (0 = unlimited)
    """
    
    initial_ms: float = 2000.0
    max_ms: float = 30000.0
    factor: float = 1.8
    jitter: float = 0.25
    max_attempts: int = 0


# Default policies
TELEGRAM_BACKOFF = BackoffPolicy(initial_ms=2000, max_ms=30000, factor=1.8, jitter=0.25)
DISCORD_BACKOFF = BackoffPolicy(initial_ms=3000, max_ms=60000, factor=2.0, jitter=0.2)
SLACK_BACKOFF = BackoffPolicy(initial_ms=2000, max_ms=30000, factor=1.5, jitter=0.3)
WHATSAPP_BACKOFF = BackoffPolicy(initial_ms=5000, max_ms=60000, factor=2.0, jitter=0.2)


def compute_backoff(policy: BackoffPolicy, attempt: int) -> float:
    """Compute delay for a given attempt number.
    
    Args:
        policy: Backoff configuration
        attempt: Attempt number (1-based)
        
    Returns:
        Delay in seconds
    """
    base_ms = policy.initial_ms * (policy.factor ** (attempt - 1))
    capped_ms = min(base_ms, policy.max_ms)
    
    if policy.jitter > 0:
        jitter_range = capped_ms * policy.jitter
        capped_ms += random.uniform(-jitter_range, jitter_range)
    
    return max(0, capped_ms / 1000.0)


# Common recoverable error patterns across platforms
_RECOVERABLE_PATTERNS: Set[str] = {
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "connection aborted",
    "network unreachable",
    "network is unreachable",
    "temporary failure",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "too many requests",
    "rate limit",
    "rate_limited",
    "internal server error",
    "server error",
    "eof occurred",
    "broken pipe",
    "reset by peer",
    "name resolution",
    "dns resolution",
    "ssl",
    "certificate",
    "transientdeliveryerror",
}

# Telegram-specific patterns
_TELEGRAM_RECOVERABLE: Set[str] = {
    "getupdates",
    "conflict",
    "terminated by other",
    "restart",
    "flood",
    "retry after",
    "webhook",
}

# Auth/credential rejection patterns. A token that is revoked, rotated, wrong,
# or expired is NOT transient (retrying an invalid token forever is pointless)
# and NOT a generic fatal (it self-heals the moment the credential is fixed).
# It is its own first-class outcome so the gateway can surface it as a
# redacted, operator-actionable degraded state and auto-recover on repair.
_CREDENTIAL_PATTERNS: Set[str] = {
    "unauthorized",
    "invalid token",
    "invalid_auth",
    "token_revoked",
    "token revoked",
    "not_authed",
    "authentication failed",
    "authentication error",
    "invalid credentials",
    "invalid api key",
    "invalid_api_key",
    "expired token",
    "token expired",
    "access token is invalid",
    "unauthenticated",
}


def _parse_http_date_seconds(value: str) -> Optional[float]:
    """Parse an HTTP-date Retry-After value into seconds from now.

    Returns None if the value is not a parseable HTTP-date.
    """
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone

        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


def server_retry_after(err: BaseException) -> Optional[float]:
    """Extract a server-mandated wait (seconds) from an error/response.

    Honours explicit throttle signals instead of guessing with backoff:
      * Telegram: ``parameters.retry_after`` (or ``retry_after``) on a 429.
      * HTTP channels (Slack/Discord/WhatsApp): ``Retry-After`` header,
        as integer seconds or an HTTP-date.
      * Text fallback: "retry after <n>" / "retry_after: <n>" in the message.

    Args:
        err: The exception raised by an outbound send.

    Returns:
        The mandated wait in seconds, or None when no hint is present.
    """
    if err is None:
        return None

    # 1) Telegram-style: parameters.retry_after (python-telegram-bot exposes
    #    `retry_after` directly; raw API returns parameters={"retry_after": N}).
    for attr in ("retry_after",):
        val = getattr(err, attr, None)
        if isinstance(val, (int, float)) and val >= 0:
            return float(val)

    params = getattr(err, "parameters", None)
    if isinstance(params, dict):
        val = params.get("retry_after")
        if isinstance(val, (int, float)) and val >= 0:
            return float(val)

    # 2) HTTP Retry-After header from a variety of response shapes.
    headers = None
    for holder in (err, getattr(err, "response", None), getattr(err, "resp", None)):
        if holder is None:
            continue
        h = getattr(holder, "headers", None)
        if h is not None:
            headers = h
            break

    if headers is not None:
        try:
            getter = getattr(headers, "get", None)
            raw = getter("Retry-After") if callable(getter) else None
            if raw is None and callable(getter):
                raw = getter("retry-after")
        except Exception:
            raw = None
        if raw is not None:
            raw_str = str(raw).strip()
            try:
                secs = float(raw_str)
                if secs >= 0:
                    return secs
            except (TypeError, ValueError):
                parsed = _parse_http_date_seconds(raw_str)
                if parsed is not None:
                    return parsed

    # 3) Text fallback: parse "retry after 30" / "retry_after: 30" from message.
    msg = str(err)
    match = re.search(r"retry[\s_-]?after[:\s]+(\d+(?:\.\d+)?)", msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            return None

    return None


def is_recoverable_error(err: BaseException, platform: str = "") -> bool:
    """Check if an error is likely transient/recoverable.
    
    Args:
        err: The exception to check
        platform: Optional platform name for platform-specific checks
        
    Returns:
        True if the error is likely transient
    """
    msg = str(err).lower()
    err_type = type(err).__name__.lower()
    
    # Check common patterns
    for pattern in _RECOVERABLE_PATTERNS:
        if pattern in msg or pattern in err_type:
            return True
    
    # Platform-specific checks
    if platform == "telegram":
        for pattern in _TELEGRAM_RECOVERABLE:
            if pattern in msg:
                return True
        # HTTP 409 = getUpdates conflict (another bot instance)
        if hasattr(err, 'error_code') and getattr(err, 'error_code', None) == 409:
            return True
    
    # Check for common HTTP status codes
    status = getattr(err, 'status', None) or getattr(err, 'status_code', None)
    if isinstance(status, int) and status in (408, 429, 500, 502, 503, 504):
        return True
    
    # asyncio timeouts
    if isinstance(err, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True
    
    return False


def is_credential_error(err: BaseException, platform: str = "") -> bool:
    """Check if an error is an auth/credential rejection (revoked/expired token).

    A runtime 401/403 (or the platform text equivalent — "Unauthorized",
    "invalid token", Slack's ``invalid_auth``/``token_revoked``) means the
    channel's credential is invalid *right now*. This is a distinct outcome from
    both transient/recoverable errors (network blips, 5xx, rate limits) and
    generic fatal errors: it should stop the pointless reconnect loop against a
    known-bad credential and surface as a redacted, operator-actionable degraded
    state that auto-recovers when the credential is repaired.

    Args:
        err: The exception to classify.
        platform: Optional platform name (reserved for platform-specific tuning).

    Returns:
        True if the error signals an invalid/rejected credential.
    """
    if err is None:
        return False

    # HTTP 401 Unauthorized / 403 Forbidden are the canonical auth-rejection
    # status codes across platforms (Telegram exposes ``error_code``).
    status = getattr(err, "status", None)
    if status is None:
        status = getattr(err, "status_code", None)
    if status is None:
        status = getattr(err, "error_code", None)
    if isinstance(status, int) and status in (401, 403):
        return True

    msg = str(err).lower()
    for pattern in _CREDENTIAL_PATTERNS:
        if pattern in msg:
            return True

    return False


# Patterns that confirm a *whole target* is permanently unreachable: the bot
# was kicked/blocked, the chat/group/channel no longer exists. These differ from
# transient errors (handled by is_recoverable_error) and from thread-/message-
# level 404s (deleting one message must NOT condemn the whole channel).
_PERMANENT_TARGET_PATTERNS: Set[str] = {
    "forbidden",
    "bot was kicked",
    "bot was blocked",
    "user is deactivated",
    "chat not found",
    "channel not found",
    "group chat was deleted",
    "the group chat was deleted",
    "bot is not a member",
    "not enough rights",
    "have no rights to send",
    "need administrator rights",
    "peer_id_invalid",
    "account_not_found",
    "channel_archived",
    "is_archived",
    "blocked by the user",
}

# Substrings that indicate a 404 is scoped to a *message/thread*, not the whole
# target, so it stays on the retry path instead of condemning the channel.
_THREAD_SCOPED_NOT_FOUND: Set[str] = {
    "message to edit not found",
    "message not found",
    "message to delete not found",
    "message_id_invalid",
    "thread not found",
    "unknown message",
    "reply not found",
    "message can't be edited",
}


def is_permanent_target_failure(err: BaseException, platform: str = "") -> bool:
    """Check if an error means a whole delivery target is permanently dead.

    Returns True only for *confirmed permanent* whole-target failures — the bot
    was kicked/blocked, or the chat/channel no longer exists (typically HTTP
    ``403`` or a ``404`` "chat not found"). Such targets should be suppressed by
    a :class:`~praisonai.bots._dead_targets.DeadTargetRegistry` until a later
    send succeeds and self-heals them.

    Transient errors (5xx, 429, timeouts) and thread-/message-level 404s are
    *not* permanent and return False so they stay on the retry/backoff path.

    Args:
        err: The exception raised by an outbound send.
        platform: Optional platform name (reserved for platform-specific tuning).

    Returns:
        True if the target should be marked dead, else False.
    """
    if err is None:
        return False

    # Transient wins: never condemn a target on a recoverable error.
    if is_recoverable_error(err, platform):
        return False

    msg = str(err).lower()

    # A 404 that is scoped to a single message/thread must not kill the channel.
    for pat in _THREAD_SCOPED_NOT_FOUND:
        if pat in msg:
            return False

    # HTTP status: 403 Forbidden / 404 Not Found / 410 Gone are the canonical
    # whole-target permanent signals (after the message-scoped 404 guard above).
    # NOTE: 401 Unauthorized is deliberately excluded — it signals an account-
    # /token-level auth problem (revoked or wrong credentials), not the death of
    # one specific channel. Condemning a channel on a 401 would suppress every
    # target the moment a token expires, and the TTL would keep them suppressed
    # long after the token is fixed. Auth failures stay off the dead-target path.
    status = getattr(err, "status", None)
    if status is None:
        status = getattr(err, "status_code", None)
    if status is None:
        status = getattr(err, "error_code", None)
    if isinstance(status, int) and status in (403, 404, 410):
        return True

    # Text patterns from platforms that don't surface a clean status code.
    for pat in _PERMANENT_TARGET_PATTERNS:
        if pat in msg:
            return True

    return False


def is_conflict_error(err: BaseException) -> bool:
    """Check if error is a Telegram getUpdates 409 conflict.
    
    This happens when another bot instance is using the same token.
    """
    msg = str(err).lower()
    status = getattr(err, 'error_code', None) or getattr(err, 'status_code', None)
    
    if status == 409:
        return True
    if "409" in msg and "conflict" in msg:
        return True
    if "getupdates" in msg and ("conflict" in msg or "terminated" in msg):
        return True
    
    return False


async def sleep_with_abort(seconds: float, abort_signal: Optional[asyncio.Event] = None) -> bool:
    """Sleep for a duration, but wake early if abort is signaled.
    
    Args:
        seconds: Duration to sleep
        abort_signal: Optional event that cancels the sleep
        
    Returns:
        True if sleep completed normally, False if aborted
    """
    if abort_signal is None:
        await asyncio.sleep(seconds)
        return True
    
    try:
        await asyncio.wait_for(abort_signal.wait(), timeout=seconds)
        return False  # Aborted
    except asyncio.TimeoutError:
        return True  # Normal completion


@dataclass
class ConnectionMonitor:
    """Tracks connection health with automatic backoff.
    
    Attributes:
        platform: Platform name for error classification
        policy: Backoff policy for retries
        attempt: Current retry attempt count
        last_error: Last error encountered
        last_error_time: Timestamp of last error
        total_recoveries: Total successful recoveries
    """
    
    platform: str = ""
    policy: BackoffPolicy = field(default_factory=BackoffPolicy)
    attempt: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    total_recoveries: int = 0
    
    def record_success(self) -> None:
        """Record a successful operation, resetting backoff."""
        if self.attempt > 0:
            self.total_recoveries += 1
            logger.info(
                f"[{self.platform}] Connection recovered after "
                f"{self.attempt} attempt(s)"
            )
        self.attempt = 0
        self.last_error = None
        self.last_error_time = None
    
    def record_error(self, err: BaseException) -> float:
        """Record an error and compute next delay.
        
        Args:
            err: The error that occurred
            
        Returns:
            Delay in seconds before next retry
        """
        self.attempt += 1
        self.last_error = str(err)
        self.last_error_time = time.time()
        
        # Honour an explicit server-mandated wait (Telegram retry_after,
        # HTTP Retry-After) over the generic backoff estimate.
        mandated = server_retry_after(err)
        if mandated is not None:
            delay = mandated
            logger.warning(
                f"[{self.platform}] Error (attempt {self.attempt}): "
                f"{self.last_error}; honouring server Retry-After {delay:.1f}s"
            )
        else:
            delay = compute_backoff(self.policy, self.attempt)
            logger.warning(
                f"[{self.platform}] Error (attempt {self.attempt}): "
                f"{self.last_error}; retrying in {delay:.1f}s"
            )
        
        return delay
    
    def should_retry(self) -> bool:
        """Check if we should retry based on policy."""
        if self.policy.max_attempts <= 0:
            return True  # Unlimited
        return self.attempt < self.policy.max_attempts
    
    def to_dict(self) -> dict:
        """Serialize for status/health reporting."""
        return {
            "platform": self.platform,
            "attempt": self.attempt,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time,
            "total_recoveries": self.total_recoveries,
            "max_attempts": self.policy.max_attempts,
        }


async def deliver_with_retry(
    send_func,
    *,
    policy: Optional[BackoffPolicy] = None,
    is_recoverable: Optional[callable] = None,
    platform: str = "",
    parked_store: Optional[Any] = None,
    reply_data: Optional[dict] = None,
) -> Any:
    """Deliver a message with bounded exponential backoff retry.
    
    This wrapper ensures reliable delivery of bot responses even when
    transient platform errors occur (HTTP 5xx, network issues, rate limits).
    
    Args:
        send_func: Async callable to execute (the send operation)
        policy: Backoff configuration (defaults to BackoffPolicy())
        is_recoverable: Function to check if error is transient (defaults to is_recoverable_error)
        platform: Platform name for error classification
        parked_store: Optional outbound DLQ for failed sends
        reply_data: Optional metadata about the reply for DLQ storage
        
    Returns:
        Result from successful send_func execution
        
    Raises:
        The original exception if non-recoverable or max attempts exceeded
    """
    if policy is None:
        policy = BackoffPolicy(max_attempts=3)  # Default to 3 attempts for outbound
    
    if is_recoverable is None:
        is_recoverable = lambda e: is_recoverable_error(e, platform)
    
    last_error = None
    attempt = 0
    
    # Handle unlimited retries when max_attempts is 0
    while True:
        attempt += 1
        try:
            return await send_func()
        except Exception as e:
            last_error = e
            
            # Check if error is recoverable
            if not is_recoverable(e):
                # Non-recoverable, park and raise
                if parked_store is not None and reply_data is not None:
                    try:
                        await parked_store.enqueue_outbound(
                            platform=platform,
                            error=f"{type(e).__name__}: {e}",
                            **reply_data
                        )
                        logger.info(f"[{platform}] Parked failed outbound message for later replay")
                    except Exception as dlq_exc:
                        logger.error(f"Failed to park outbound message: {dlq_exc}")
                raise
            
            # Check if we've exceeded max attempts (if limited)
            if policy.max_attempts > 0 and attempt >= policy.max_attempts:
                # Park the message for later replay if DLQ is configured
                if parked_store is not None and reply_data is not None:
                    try:
                        await parked_store.enqueue_outbound(
                            platform=platform,
                            error=f"{type(e).__name__}: {e}",
                            **reply_data
                        )
                        logger.info(f"[{platform}] Parked failed outbound message for later replay")
                    except Exception as dlq_exc:
                        logger.error(f"Failed to park outbound message: {dlq_exc}")
                raise
            
            # Honour a server-mandated wait if present, else generic backoff.
            mandated = server_retry_after(e)
            delay = mandated if mandated is not None else compute_backoff(policy, attempt)
            attempts_display = f"{attempt}/{policy.max_attempts}" if policy.max_attempts > 0 else f"{attempt}/∞"
            hint = " (server Retry-After)" if mandated is not None else ""
            logger.warning(
                f"[{platform}] Outbound send failed (attempt {attempts_display}): "
                f"{e}; retrying in {delay:.1f}s{hint}"
            )
            
            await asyncio.sleep(delay)
