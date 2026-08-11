"""
Discord Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by sending embed messages to a Discord channel
via REST API and polling for text-reply responses containing approval keywords.

Uses raw aiohttp HTTP calls to the Discord REST API — does NOT depend on
``discord.py`` to avoid gateway conflicts with a running DiscordBot.

Usage::

    from praisonaiagents import Agent
    from praisonai_bot.bots import DiscordApproval

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
from typing import Any, Dict, Iterable, Optional

from ._approval_base import (
    DEFAULT_APPROVAL_TIMEOUT,
    DurableApprovalMixin,
    classify_keyword,
    classify_with_llm,
    is_authorized_actor,
    normalize_approvers,
    sync_wrapper,
)

logger = logging.getLogger(__name__)

_DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordApproval(DurableApprovalMixin):
    """Approval backend that sends Discord embeds and polls for text replies.

    Posts a rich embed message to a Discord channel, then polls the channel
    for text replies containing approval/denial keywords.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        token: Discord bot token. Falls back to ``DISCORD_BOT_TOKEN`` env var.
        channel_id: Discord channel ID to send approval requests to.
        timeout: Max seconds to wait for a response (default 300 = 5 min).
        poll_interval: Seconds between polls (default 3.0).
        allowed_approvers: Optional set of Discord user IDs permitted to
            approve/deny. When provided, a reply from any other user is
            ignored, so an unauthorised member of a shared channel cannot
            resolve a gated tool. When ``None`` (default) any user may respond
            (legacy behaviour, backward compatible). Falls back to a
            comma-separated ``DISCORD_APPROVERS`` env var when not passed.

    Example::

        from praisonai_bot.bots import DiscordApproval
        agent = Agent(
            name="bot",
            approval=DiscordApproval(channel_id="1234567890", allowed_approvers=["999"]),
        )
    """

    def __init__(
        self,
        token: Optional[str] = None,
        channel_id: Optional[str] = None,
        timeout: float = DEFAULT_APPROVAL_TIMEOUT,
        poll_interval: float = 3.0,
        allowed_approvers: Optional[Iterable[str]] = None,
        store: Optional[Any] = None,
    ):
        self._token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
        if not self._token:
            raise ValueError(
                "Discord bot token is required. Pass token= or set DISCORD_BOT_TOKEN env var."
            )
        self._channel_id = channel_id or os.environ.get("DISCORD_CHANNEL_ID", "")
        self._timeout = timeout
        self._poll_interval = poll_interval
        if allowed_approvers is None:
            _env = os.environ.get("DISCORD_APPROVERS", "").strip()
            if _env:
                allowed_approvers = [a.strip() for a in _env.split(",") if a.strip()]
        self._allowed_approvers = normalize_approvers(allowed_approvers)
        # Optional: set PRAISONAI_DISCORD_SSL_VERIFY=false to skip SSL verify
        # (e.g. corporate proxy / CA issues)
        _v = os.environ.get("PRAISONAI_DISCORD_SSL_VERIFY", "true").lower()
        self._ssl_verify = _v not in ("false", "0", "no")
        self._init_store(store)

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
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self._ssl_verify),
            ) as _session:
                return await _do_request(_session)

    # ── ApprovalProtocol implementation ─────────────────────────────────

    async def request_approval(self, request) -> Any:
        """Send a Discord embed and poll for approval/denial text reply."""
        from praisonaiagents.approval.protocols import ApprovalDecision
        import aiohttp

        await self._persist_pending(request, self._timeout)

        channel_id = self._channel_id
        if not channel_id:
            decision = ApprovalDecision(
                approved=False,
                reason="No Discord channel_id configured",
            )
            await self._resolve_pending(request, decision)
            return decision

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self._ssl_verify),
        ) as session:
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
                    decision = ApprovalDecision(
                        approved=False,
                        reason=f"Failed to post Discord message: {post_data.get('message', 'unknown')}",
                    )
                    await self._resolve_pending(request, decision)
                    return decision

                # 2. Poll for text reply
                decision = await self._poll_for_response(
                    channel_id, msg_id, request=request, session=session,
                )

                # 3. Update original message with result
                await self._update_message(
                    channel_id, msg_id, request, decision, session=session,
                )

                await self._resolve_pending(request, decision)
                return decision

            except Exception as e:
                logger.error(f"DiscordApproval error: {e}")
                decision = ApprovalDecision(
                    approved=False,
                    reason=f"Discord approval error: {e}",
                )
                await self._resolve_pending(request, decision)
                return decision

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
            "footer": {"text": f"Reply yes/no, or with modifications (e.g. 'yes, but use ~/Downloads') (timeout: {int(self._timeout)}s)"},
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
        request: Optional[Any] = None,
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

                    # Only accept replies to the approval message
                    ref = msg.get("message_reference") or {}
                    if ref.get("message_id") != message_id:
                        continue

                    text = msg.get("content", "").strip()
                    user_id = author.get("id", "unknown")
                    username = author.get("username", user_id)

                    # Authorization boundary: ignore replies from users not in
                    # the allowlist so an unauthorised channel member cannot
                    # resolve a gated tool.
                    if not is_authorized_actor(user_id, self._allowed_approvers):
                        logger.warning(
                            "Ignoring Discord approval reply from unauthorized "
                            "user %s", user_id,
                        )
                        continue

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

                    # Not a simple keyword — use LLM to classify
                    if kw is None and text and request is not None:
                        try:
                            llm_result = await classify_with_llm(
                                text=text,
                                tool_name=request.tool_name,
                                arguments=request.arguments,
                                risk_level=request.risk_level,
                            )
                            return ApprovalDecision(
                                approved=llm_result["approved"],
                                reason=llm_result["reason"],
                                approver=user_id,
                                modified_args=llm_result.get("modified_args", {}),
                                metadata={
                                    "platform": "discord",
                                    "message_id": msg.get("id"),
                                    "llm_classified": True,
                                    "original_text": text,
                                },
                            )
                        except Exception as llm_err:
                            logger.warning(f"LLM classification failed: {llm_err}")

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
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=self._ssl_verify),
                ) as _session:
                    async with _session.patch(
                        url, headers=headers, json=payload,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        data = await resp.json()

            if isinstance(data, dict) and data.get("message"):
                logger.warning(f"Failed to update Discord message: {data.get('message')}")
        except Exception as e:
            logger.warning(f"Failed to update Discord message: {e}")
