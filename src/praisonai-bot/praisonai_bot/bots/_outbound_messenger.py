"""
Concrete outbound messenger binding for the built-in ``send_message`` tool.

The core SDK ships an agent-callable ``send_message`` tool (Issue #2183) that
resolves an :class:`OutboundMessengerProtocol` from the per-turn session
context. Core deliberately owns only the *surface* — the tool, the protocol,
the context-var registration slot and the send-policy guard — leaving the
heavy, platform-specific delivery binding to the wrapper.

``BotOutboundMessenger`` is that missing binding: it adapts the running
gateway's :class:`~praisonai.bots.delivery.DeliveryRouter` (which already
resolves symbolic targets to a concrete bot adapter and dispatches through it)
to the protocol the core tool expects. It is registered into the per-turn
context by :class:`~praisonai.bots._session.BotSessionManager` for the duration
of each agent turn, so a model calling ``send_message`` mid-task actually
reaches the user on Telegram/Discord/Slack/WhatsApp — subject to the existing
send-policy guard enforced inside the core tool.

Wrapper-only by design: it depends on a live transport adapter and the
wrapper's delivery stack, neither of which belong in the core SDK.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from praisonaiagents.gateway import (
    DeliveryResult,
    ReactionResult,
    TargetInfo,
    ThreadResult,
)

from .delivery import DeliveryRouter, SessionSource
from ._outbound_media import (
    MediaDeliveryError,
    OutboundMediaPolicy,
    validate_media_delivery_path,
)

logger = logging.getLogger(__name__)


class BotOutboundMessenger:
    """Bind a :class:`DeliveryRouter` to the core ``OutboundMessengerProtocol``.

    Implements ``send``/``list_targets`` by resolving the symbolic target via
    the router's :class:`ChannelDirectory` and dispatching through the live bot
    adapter the router already manages. An ``origin`` :class:`SessionSource`
    (the chat the current turn came from) lets the ``"origin"`` token reply to
    the user on the channel they messaged from.

    Args:
        router: The gateway's delivery router (owns the channel directory and a
            handle to every connected bot adapter).
        origin: Optional source of the current turn, used to resolve the
            ``"origin"`` target. When absent, ``"origin"`` sends fail cleanly
            with a model-readable message instead of raising.
        media_policy: Optional :class:`OutboundMediaPolicy` governing which
            agent-supplied file paths may be uploaded (exfiltration guard).
            Defaults to a permissive-but-denylisted policy.
    """

    def __init__(
        self,
        router: DeliveryRouter,
        *,
        origin: Optional[SessionSource] = None,
        media_policy: Optional[OutboundMediaPolicy] = None,
    ) -> None:
        self._router = router
        self._origin = origin
        self._media_policy = media_policy or OutboundMediaPolicy()

    async def send(
        self,
        target: str,
        text: str,
        *,
        media: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> DeliveryResult:
        """Deliver ``text`` to a symbolic ``target`` via the delivery router.

        When ``media`` paths are supplied each is validated through the
        outbound delivery-path guard (rejecting credential/system locations a
        prompt injection might name) and then uploaded through the live
        platform adapter. The result truthfully reports how many attachments
        were delivered, skipped by policy, or unsupported by the transport.
        """
        try:
            platform, channel_id, _thread_id = self._router.resolve(target, self._origin)
        except ValueError as e:
            return DeliveryResult(
                ok=False,
                target=target,
                summary=f"Failed to send to {target}: {e}",
                detail=str(e),
            )

        resolved = f"{platform}:{channel_id}"

        # Idempotency covers the *whole* text+media envelope (issue #2578). A
        # duplicate proactive send must skip both the text and any media upload,
        # otherwise a re-fired job with attachments would double-upload media
        # even though the text was suppressed. We therefore check the key here
        # (before any work) and only record it after the full send succeeds —
        # deferring the router's own recording by not passing the key down.
        if idempotency_key and self._router.is_duplicate_key(idempotency_key):
            logger.info(
                "BotOutboundMessenger: suppressing duplicate proactive send "
                "(idempotency_key=%s) to %s",
                idempotency_key,
                resolved,
            )
            return DeliveryResult(
                ok=True,
                target=resolved,
                summary=f"Sent to {resolved} (duplicate suppressed).",
                detail="idempotency_key already delivered",
            )

        try:
            delivered = await self._router.deliver(
                target, text, self._origin
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.error("BotOutboundMessenger.send failed for %s: %s", target, e)
            # Release the durable reservation this envelope claimed up-front
            # (#4541) so a failed send stays retryable rather than being
            # deduplicated against its own crashed attempt.
            if idempotency_key:
                self._router.release_key(idempotency_key)
            return DeliveryResult(
                ok=False,
                target=resolved,
                summary=f"Failed to send to {target}: {e}",
                detail=str(e),
            )

        if not delivered:
            if idempotency_key:
                self._router.release_key(idempotency_key)
            return DeliveryResult(
                ok=False,
                target=resolved,
                summary=f"Failed to send to {target}: delivery was not accepted",
                detail="delivery_router returned False",
            )

        detail = None
        summary = f"Sent to {resolved}."
        if media:
            # The body text was already delivered above; passing it again as the
            # first attachment caption would duplicate it on platforms that show
            # captions (and can blow Telegram's caption length limit). Send the
            # attachments without re-captioning the full text.
            sent, skipped, notes = await self._deliver_media(
                target, media, caption=None
            )
            detail = "; ".join(notes) if notes else None
            if sent:
                summary = (
                    f"Sent to {resolved} ({sent} attachment(s) delivered"
                    + (f", {skipped} skipped" if skipped else "")
                    + ")."
                )
            else:
                summary = f"Sent to {resolved} (media not attached)."

        # Record the key only after the full text+media envelope has been sent,
        # so a failed send stays retryable and a re-fire is deduplicated across
        # both text and attachments.
        if idempotency_key:
            self._router.remember_key(idempotency_key)

        return DeliveryResult(
            ok=True,
            target=resolved,
            summary=summary,
            detail=detail,
        )

    async def _deliver_media(
        self,
        target: str,
        media: List[str],
        *,
        caption: Optional[str],
    ):
        """Validate + upload each media path; return (sent, skipped, notes).

        The path guard runs before any upload so a model-named credential/
        system path is rejected rather than exfiltrated. Failures are
        collected as human-readable notes for the result detail instead of
        aborting the whole send.
        """
        if not self._media_policy.enabled:
            return 0, len(media), [
                f"Media delivery disabled by policy ({len(media)} skipped)."
            ]

        sent = 0
        skipped = 0
        notes: List[str] = []
        # Only the first attachment carries the caption to avoid repeating the
        # full text on every file.
        first = True
        for path in media:
            try:
                safe = validate_media_delivery_path(
                    path, policy=self._media_policy
                )
            except MediaDeliveryError as e:
                skipped += 1
                notes.append(f"Skipped {path!r}: {e}")
                logger.warning("Outbound media rejected: %s", e)
                continue

            try:
                ok = await self._router.send_media(
                    target,
                    safe,
                    caption=caption if first else None,
                    origin=self._origin,
                )
            except Exception as e:  # pragma: no cover — defensive
                ok = False
                logger.error("Media upload failed for %s: %s", path, e)

            if ok:
                sent += 1
                first = False
            else:
                skipped += 1
                notes.append(
                    f"Transport could not attach {path!r}."
                )

        return sent, skipped, notes

    async def react(
        self,
        target: str,
        emoji: str,
        *,
        message_id: str = "",
        remove: bool = False,
    ) -> ReactionResult:
        """Add/remove a reaction on a message via the delivery router.

        Dispatches through the live adapter's native reaction primitive, gated
        on the channel's ``capabilities["reactions"]`` flag (Issue #3917). When
        ``message_id`` is empty and ``target`` is ``"origin"`` the inbound
        message being handled is used, so a model can acknowledge the current
        message with a single emoji instead of a full text reply. A channel that
        cannot react returns a typed ``unsupported`` outcome rather than raising.
        """
        resolved_message_id = message_id
        if not resolved_message_id and target == "origin" and self._origin is not None:
            resolved_message_id = self._origin.message_id or ""

        if not resolved_message_id:
            return ReactionResult(
                status="failed",
                target=target,
                detail="no message_id to react to",
            )

        status, resolved = await self._router.react(
            target,
            emoji,
            resolved_message_id,
            self._origin,
            remove=remove,
        )
        detail = None
        if status == "unsupported":
            detail = f"channel '{resolved}' has no reactions capability"
        elif status == "no_route":
            detail = f"could not resolve target '{target}'"
        return ReactionResult(status=status, target=resolved, detail=detail)

    async def create_thread(
        self,
        target: str,
        name: str,
    ) -> ThreadResult:
        """Open a new thread/topic named ``name`` under ``target`` (#3987).

        Dispatches through the live adapter's native ``create_thread`` primitive,
        gated on the channel's ``capabilities["threads"]`` flag. A channel that
        cannot thread returns a typed ``unsupported`` outcome rather than raising,
        so the caller can fall back to the parent channel::

            res = await messenger.create_thread("slack:C123", name="research")
            target = f"slack:C123:{res.thread_id}" if res.ok else "slack:C123"
            await messenger.send(target, subtask_output)
        """
        status, resolved, thread_id = await self._router.create_thread(
            target,
            name,
            self._origin,
        )
        detail = None
        if status == "unsupported":
            detail = f"channel '{resolved}' has no threads capability"
        elif status == "no_route":
            detail = f"could not resolve target '{target}'"
        elif status == "failed":
            detail = f"transport could not open a thread on '{resolved}'"
        return ThreadResult(
            status=status,
            target=resolved,
            thread_id=thread_id,
            detail=detail,
        )

    def list_targets(self) -> List[TargetInfo]:
        """List targets currently reachable through the delivery router.

        Surfaces ``"origin"`` (when the current turn has a source) plus every
        home/alias/observed channel the router's directory knows about, mapped
        into the core :class:`TargetInfo` shape the ``send_message`` tool
        returns for ``action="list"``.
        """
        targets: List[TargetInfo] = []

        if self._origin is not None:
            targets.append(
                TargetInfo(
                    target="origin",
                    platform=self._origin.platform,
                    kind="origin",
                    label=f"origin ({self._origin.platform}:{self._origin.channel_id})",
                )
            )

        try:
            described = self._router.directory.describe_targets()
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("BotOutboundMessenger.list_targets failed: %s", e)
            described = []

        for t in described:
            platform = t.get("platform", "")
            channel_id = t.get("channel_id", "")
            kind = t.get("kind", "alias")
            name = t.get("name", "")
            # Prefer the friendly alias name as the addressable token; fall back
            # to the platform home shorthand, else the explicit platform:channel.
            if kind == "alias" and name:
                token = name
            elif kind == "home" and platform:
                token = platform
            else:
                token = f"{platform}:{channel_id}" if platform and channel_id else name
            targets.append(
                TargetInfo(
                    target=token,
                    platform=platform,
                    kind=kind,
                    label=name or token,
                )
            )

        return targets


__all__ = ["BotOutboundMessenger"]
