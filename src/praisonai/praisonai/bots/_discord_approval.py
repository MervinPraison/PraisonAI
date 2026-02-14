"""
Discord Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by sending embed messages to a Discord channel
via REST API and polling for text-reply responses containing approval keywords.

Uses raw aiohttp HTTP calls to the Discord REST API — does NOT depend on
``discord.py`` to avoid gateway conflicts with a running DiscordBot.

Usage::

    from praisonaiagents import Agent
    from praisonai.bots import DiscordApproval

    agent = Agent(
        name="assistant",
        tools=[execute_command],
        approval=DiscordApproval(channel_id="123456789"),  # token from DISCORD_BOT_TOKEN env
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

from ._approval_base import classify_keyword, sync_wrapper

logger = logging.getLogger(__name__)

_DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordApproval:
    """Approval backend that sends Discord embeds and polls for text replies.

    Posts a rich embed message to a Discord channel, then polls the channel
    for text replies containing approval/denial keywords.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        token: Discord bot token. Falls back to ``DISCORD_BOT_TOKEN`` env var.
        channel_id: Discord channel ID to send approval requests to.
        timeout: Max seconds to wait for a response (default 300 = 5 min).
        poll_interval: Seconds between polls (default 3.0).

    Example::

        from praisonai.bots import DiscordApproval
        agent = Agent(name="bot", approval=DiscordApproval(channel_id="1234567890"))
    """

    def __init__(
        self,
        token: Optional[str] = None,
        channel_id: Optional[str] = None,
        timeout: float = 300,
        poll_interval: float = 3.0,
    ):
        self._token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
        if not self._token:
            raise ValueError(
                "Discord bot token is required. Pass token= or set DISCORD_BOT_TOKEN env var."
            )
        self._channel_id = channel_id or ""
        self._timeout = timeout
        self._poll_interval = poll_interval

    def __repr__(self) -> str:
        masked = f"...{self._token[-4:]}" if len(self._token) > 4 else "***"
        return f"DiscordApproval(channel_id={self._channel_id!r}, token={masked!r})"

    # ── Internal Discord API helper ────────────────────────────────────

    async def _discord_api(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Call a Discord REST API endpoint. Override in tests for mocking."""
        import aiohttp

        url = f"{_DISCORD_API_BASE}{path}"
        headers = {
            "Authorization": f"Bot {self._token}",
            "Content-Type": "application/json",
        }

        async def _do_request(s):
            if method.upper() == "GET":
                async with s.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return await resp.json()
            else:
                async with s.post(
                    url, headers=headers, json=payload or {},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return await resp.json()

        if session is not None:
            return await _do_request(session)
        else:
            async with aiohttp.ClientSession() as _session:
                return await _do_request(_session)

    # ── ApprovalProtocol implementation ─────────────────────────────────

    async def request_approval(self, request) -> Any:
        """Send a Discord embed and poll for approval/denial text reply."""
        from praisonaiagents.approval.protocols import ApprovalDecision
        import aiohttp

        channel_id = self._channel_id
        if not channel_id:
            return ApprovalDecision(
                approved=False,
                reason="No Discord channel_id configured",
            )

        async with aiohttp.ClientSession() as session:
            # 1. Post approval embed
            embed = self._build_embed(request)
            content = self._build_fallback_text(request)

            try:
                post_data = await self._discord_api("POST",
                    f"/channels/{channel_id}/messages",
                    {"content": content, "embeds": [embed]},
                    session=session,
                )

                msg_id = post_data.get("id")
                if not msg_id:
                    return ApprovalDecision(
                        approved=False,
                        reason=f"Failed to post Discord message: {post_data.get('message', 'unknown')}",
                    )

                # 2. Poll for text reply
                decision = await self._poll_for_response(
                    channel_id, msg_id, session=session,
                )

                # 3. Update original message with result
                await self._update_message(
                    channel_id, msg_id, request, decision, session=session,
                )

                return decision

            except Exception as e:
                logger.error(f"DiscordApproval error: {e}")
                return ApprovalDecision(
                    approved=False,
                    reason=f"Discord approval error: {e}",
                )

    def request_approval_sync(self, request) -> Any:
        """Synchronous wrapper — runs async method in a new event loop."""
        return sync_wrapper(self.request_approval(request), self._timeout)

    # ── Embed Builder ──────────────────────────────────────────────────

    def _build_embed(self, request) -> Dict[str, Any]:
        """Build a Discord embed for the approval message."""
        risk_colors = {
            "critical": 0xFF0000,
            "high": 0xFF8C00,
            "medium": 0xFFD700,
            "low": 0x00FF00,
        }

        args_lines = []
        for key, value in request.arguments.items():
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            args_lines.append(f"`{key}`: `{val_str}`")
        args_text = "\n".join(args_lines) if args_lines else "_(none)_"

        fields = [
            {"name": "Tool", "value": f"`{request.tool_name}`", "inline": True},
            {"name": "Risk", "value": request.risk_level.upper(), "inline": True},
            {"name": "Arguments", "value": args_text, "inline": False},
        ]
        if request.agent_name:
            fields.insert(2, {"name": "Agent", "value": request.agent_name, "inline": True})

        return {
            "title": "🔒 Tool Approval Required",
            "color": risk_colors.get(request.risk_level, 0x808080),
            "fields": fields,
            "footer": {"text": f"Reply yes to approve or no to deny (timeout: {int(self._timeout)}s)"},
        }

    def _build_fallback_text(self, request) -> str:
        return (
            f"🔒 Tool Approval Required: `{request.tool_name}` "
            f"(risk: {request.risk_level}). "
            f"Reply yes to approve or no to deny."
        )

    # ── Polling ─────────────────────────────────────────────────────────

    async def _poll_for_response(
        self,
        channel_id: str,
        message_id: str,
        session: Optional[Any] = None,
    ) -> Any:
        """Poll channel messages for a reply after the approval message."""
        from praisonaiagents.approval.protocols import ApprovalDecision

        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)

            try:
                data = await self._discord_api("GET",
                    f"/channels/{channel_id}/messages?after={message_id}&limit=10",
                    session=session,
                )

                if isinstance(data, dict) and data.get("message"):
                    logger.warning(f"Discord poll error: {data.get('message')}")
                    continue

                if not isinstance(data, list):
                    continue

                for msg in data:
                    # Skip bot messages
                    author = msg.get("author", {})
                    if author.get("bot"):
                        continue

                    text = msg.get("content", "").strip()
                    user_id = author.get("id", "unknown")
                    username = author.get("username", user_id)
                    kw = classify_keyword(text)

                    if kw == "approve":
                        return ApprovalDecision(
                            approved=True,
                            reason=f"Approved via Discord by {username}",
                            approver=user_id,
                            metadata={"platform": "discord", "message_id": msg.get("id")},
                        )
                    if kw == "deny":
                        return ApprovalDecision(
                            approved=False,
                            reason=f"Denied via Discord by {username}",
                            approver=user_id,
                            metadata={"platform": "discord", "message_id": msg.get("id")},
                        )

            except Exception as e:
                logger.warning(f"Discord poll exception: {e}")

        return ApprovalDecision(
            approved=False,
            reason=f"Timed out waiting for Discord approval ({int(self._timeout)}s)",
            metadata={"platform": "discord", "timeout": True},
        )

    # ── Message Update ──────────────────────────────────────────────────

    async def _update_message(
        self,
        channel_id: str,
        message_id: str,
        request,
        decision,
        session: Optional[Any] = None,
    ) -> None:
        """Update the original approval message with the decision."""
        if decision.approved:
            status_emoji = "✅"
            status_text = "Approved"
            color = 0x00FF00
        else:
            status_emoji = "❌"
            status_text = "Denied"
            color = 0xFF0000

        approver = decision.approver or "system"

        embed = {
            "title": f"{status_emoji} Tool {status_text}",
            "color": color,
            "fields": [
                {"name": "Tool", "value": f"`{request.tool_name}`", "inline": True},
                {"name": "Decision", "value": status_text, "inline": True},
            ],
        }
        if decision.approver:
            embed["fields"].append({"name": "By", "value": f"<@{approver}>", "inline": True})

        try:
            import aiohttp
            url = f"{_DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
            headers = {
                "Authorization": f"Bot {self._token}",
                "Content-Type": "application/json",
            }
            payload = {
                "content": f"{status_emoji} Tool {status_text}: `{request.tool_name}`",
                "embeds": [embed],
            }
            if session is not None:
                async with session.patch(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
            else:
                async with aiohttp.ClientSession() as _session:
                    async with _session.patch(
                        url, headers=headers, json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        data = await resp.json()

            if isinstance(data, dict) and data.get("message"):
                logger.warning(f"Failed to update Discord message: {data.get('message')}")
        except Exception as e:
            logger.warning(f"Failed to update Discord message: {e}")
