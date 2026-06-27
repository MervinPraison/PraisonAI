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

from praisonaiagents.gateway import DeliveryResult, TargetInfo

from .delivery import DeliveryRouter, SessionSource

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
    """

    def __init__(
        self,
        router: DeliveryRouter,
        *,
        origin: Optional[SessionSource] = None,
    ) -> None:
        self._router = router
        self._origin = origin

    async def send(
        self,
        target: str,
        text: str,
        *,
        media: Optional[List[str]] = None,
    ) -> DeliveryResult:
        """Deliver ``text`` to a symbolic ``target`` via the delivery router.

        Media attachments are not yet supported by the underlying router; when
        ``media`` paths are supplied the text is still delivered and the
        attachments are noted in the result detail so the model is not misled
        into believing files were sent.
        """
        try:
            platform, channel_id = self._router.resolve(target, self._origin)
        except ValueError as e:
            return DeliveryResult(
                ok=False,
                target=target,
                summary=f"Failed to send to {target}: {e}",
                detail=str(e),
            )

        resolved = f"{platform}:{channel_id}"
        try:
            delivered = await self._router.deliver(target, text, self._origin)
        except Exception as e:  # pragma: no cover — defensive
            logger.error("BotOutboundMessenger.send failed for %s: %s", target, e)
            return DeliveryResult(
                ok=False,
                target=resolved,
                summary=f"Failed to send to {target}: {e}",
                detail=str(e),
            )

        if not delivered:
            return DeliveryResult(
                ok=False,
                target=resolved,
                summary=f"Failed to send to {target}: delivery was not accepted",
                detail="delivery_router returned False",
            )

        detail = None
        summary = f"Sent to {resolved}."
        if media:
            detail = (
                "Text delivered; media attachments are not yet supported by "
                f"this transport ({len(media)} skipped)."
            )
            summary = f"Sent to {resolved} (media not attached)."

        return DeliveryResult(
            ok=True,
            target=resolved,
            summary=summary,
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
