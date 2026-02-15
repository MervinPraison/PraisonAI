"""
Slack Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by sending Block Kit messages to Slack
and polling for user replies (yes/no) to approve or deny tool executions.

Usage::

    from praisonaiagents import Agent
    from praisonai.bots import SlackApproval

    agent = Agent(
        name="assistant",
        tools=[execute_command],
        approval=SlackApproval(channel="#approvals"),  # token from SLACK_BOT_TOKEN env
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from ._approval_base import classify_keyword, classify_with_llm, sync_wrapper

logger = logging.getLogger(__name__)


class SlackApproval:
    """Approval backend that sends Slack messages and polls for responses.

    Sends a rich Block Kit message with tool details to a Slack channel or DM,
    then polls ``conversations.history`` for a reply containing an approval
    or denial keyword.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        token: Slack bot token (xoxb-...). Falls back to ``SLACK_BOT_TOKEN`` env var.
        channel: Slack channel ID, channel name, or user ID for DMs.
        timeout: Max seconds to wait for a response (default 300 = 5 min).
        poll_interval: Seconds between polls (default 3.0).

    Example::

        from praisonai.bots import SlackApproval
        agent = Agent(name="bot", approval=SlackApproval(channel="U0ABPEV1HK8"))
    """

    def __init__(
        self,
        token: Optional[str] = None,
        channel: Optional[str] = None,
        timeout: float = 300,
        poll_interval: float = 3.0,
    ):
        self._token = token or os.environ.get("SLACK_BOT_TOKEN", "")
        if not self._token:
            raise ValueError(
                "Slack bot token is required. Pass token= or set SLACK_BOT_TOKEN env var."
            )
        self._channel = channel or os.environ.get("SLACK_CHANNEL", "")
        self._timeout = timeout
        self._poll_interval = poll_interval

    def __repr__(self) -> str:
        masked = f"xoxb-...{self._token[-4:]}" if len(self._token) > 4 else "***"
        return f"SlackApproval(channel={self._channel!r}, token={masked!r})"

    # ── Internal Slack API helper ──────────────────────────────────────

    async def _slack_api(
        self,
        method: str,
        payload: Dict[str, Any],
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Call a Slack Web API method. Override in tests for mocking.

        Args:
            method: Slack API method name (e.g. ``chat.postMessage``).
            payload: JSON payload.
            session: Optional pre-existing ``aiohttp.ClientSession`` for reuse.
        """
        import aiohttp

        url = f"https://slack.com/api/{method}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if session is not None:
            async with session.post(
                url, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return await resp.json()
        else:
            async with aiohttp.ClientSession() as _session:
                async with _session.post(
                    url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return await resp.json()

    # ── ApprovalProtocol implementation ─────────────────────────────────

    async def request_approval(self, request) -> Any:
        """Send a Slack message and poll for approval/denial.

        Args:
            request: ApprovalRequest with tool_name, arguments, risk_level, etc.

        Returns:
            ApprovalDecision with approved=True/False and metadata.
        """
        from praisonaiagents.approval.protocols import ApprovalDecision

        import aiohttp

        channel = self._channel
        async with aiohttp.ClientSession() as session:
            if not channel:
                try:
                    data = await self._slack_api("auth.test", {}, session=session)
                    if data.get("ok"):
                        channel = data["user_id"]
                except Exception:
                    pass
                if not channel:
                    return ApprovalDecision(
                        approved=False,
                        reason="No Slack channel configured and could not resolve bot user",
                    )

            # 1. Post approval message
            blocks = self._build_blocks(request)
            fallback = self._build_fallback_text(request)

            try:
                post_data = await self._slack_api("chat.postMessage", {
                    "channel": channel,
                    "text": fallback,
                    "blocks": blocks,
                }, session=session)

                if not post_data.get("ok"):
                    return ApprovalDecision(
                        approved=False,
                        reason=f"Failed to post Slack message: {post_data.get('error', 'unknown')}",
                    )

                msg_ts = post_data["ts"]
                msg_channel = post_data["channel"]

                # 2. Poll for response (thread-scoped for multi-agent isolation)
                decision = await self._poll_for_response(
                    msg_channel, msg_ts, request=request, session=session,
                )

                # 3. Update original message with result
                await self._update_message(
                    msg_channel, msg_ts, request, decision, session=session,
                )

                return decision

            except Exception as e:
                logger.error(f"SlackApproval error: {e}")
                return ApprovalDecision(
                    approved=False,
                    reason=f"Slack approval error: {e}",
                )

    def request_approval_sync(self, request) -> Any:
        """Synchronous wrapper — runs async method in a new event loop."""
        return sync_wrapper(self.request_approval(request), self._timeout)

    # ── Block Kit Builder ───────────────────────────────────────────────

    def _build_blocks(self, request) -> List[Dict[str, Any]]:
        """Build Slack Block Kit blocks for the approval message."""
        risk_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        emoji = risk_emoji.get(request.risk_level, "⚪")
        risk_upper = request.risk_level.upper()

        # Format arguments
        args_lines = []
        for key, value in request.arguments.items():
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            args_lines.append(f"  `{key}`: `{val_str}`")
        args_text = "\n".join(args_lines) if args_lines else "  _(none)_"

        agent_line = f"\n*Agent:* {request.agent_name}" if request.agent_name else ""

        header_text = (
            f"🔒 *Tool Approval Required*\n\n"
            f"*Tool:* `{request.tool_name}`\n"
            f"*Risk:* {emoji} {risk_upper}{agent_line}\n"
            f"*Arguments:*\n{args_text}"
        )

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": header_text},
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Reply *yes* to approve or *no* to deny. "
                            f"You can also reply with modifications "
                            f"(e.g. _yes, but use ~/Downloads_) "
                            f"(timeout: {int(self._timeout) if self._timeout is not None else '∞'}s)"
                        ),
                    }
                ],
            },
        ]
        return blocks

    def _build_fallback_text(self, request) -> str:
        """Build plain-text fallback for notifications."""
        return (
            f"🔒 Tool Approval Required: `{request.tool_name}` "
            f"(risk: {request.risk_level}). "
            f"Reply yes to approve or no to deny."
        )

    # ── Polling ─────────────────────────────────────────────────────────

    async def _poll_for_response(
        self,
        channel: str,
        message_ts: str,
        request: Optional[Any] = None,
        session: Optional[Any] = None,
    ) -> Any:
        """Poll for replies scoped to the approval message thread.

        Uses ``conversations.replies`` when available so concurrent approval
        requests on the same channel don't cross-talk.  Falls back to
        ``conversations.history`` if replies returns an error (e.g. DMs).

        When a reply is not a simple yes/no keyword, the text is sent to an
        LLM to classify intent and extract any modified arguments (e.g.
        *"yes, but path is ~/Downloads"*).
        """
        from praisonaiagents.approval.protocols import ApprovalDecision

        deadline = None if self._timeout is None else time.monotonic() + self._timeout

        while deadline is None or time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)

            try:
                # Try thread-scoped replies first (best isolation)
                data = await self._slack_api("conversations.replies", {
                    "channel": channel,
                    "ts": message_ts,
                    "limit": 20,
                }, session=session)

                # Fallback to history if replies fails (some DM contexts)
                if not data.get("ok"):
                    data = await self._slack_api("conversations.history", {
                        "channel": channel,
                        "oldest": message_ts,
                        "limit": 10,
                    }, session=session)

                if not data.get("ok"):
                    logger.warning(f"Slack poll error: {data.get('error')}")
                    continue

                for msg in data.get("messages", []):
                    # Skip the bot's own approval message
                    if msg.get("ts") == message_ts:
                        continue
                    # Skip bot messages
                    if msg.get("bot_id"):
                        continue

                    text = msg.get("text", "").strip()
                    user = msg.get("user", "unknown")
                    kw = classify_keyword(text)

                    if kw == "approve":
                        return ApprovalDecision(
                            approved=True,
                            reason=f"Approved via Slack by <@{user}>",
                            approver=user,
                            metadata={"platform": "slack", "message_ts": msg.get("ts")},
                        )
                    if kw == "deny":
                        return ApprovalDecision(
                            approved=False,
                            reason=f"Denied via Slack by <@{user}>",
                            approver=user,
                            metadata={"platform": "slack", "message_ts": msg.get("ts")},
                        )

                    # Not a simple keyword — use LLM to classify free-text
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
                                approver=user,
                                modified_args=llm_result.get("modified_args", {}),
                                metadata={
                                    "platform": "slack",
                                    "message_ts": msg.get("ts"),
                                    "llm_classified": True,
                                    "original_text": text,
                                },
                            )
                        except Exception as llm_err:
                            logger.warning(f"LLM classification failed: {llm_err}")

            except Exception as e:
                logger.warning(f"Slack poll exception: {e}")

        # Timeout
        timeout_str = "indefinite" if self._timeout is None else f"{int(self._timeout)}s"
        return ApprovalDecision(
            approved=False,
            reason=f"Timed out waiting for Slack approval ({timeout_str})",
            metadata={"platform": "slack", "timeout": True},
        )

    # ── Message Update ──────────────────────────────────────────────────

    async def _update_message(
        self,
        channel: str,
        message_ts: str,
        request,
        decision,
        session: Optional[Any] = None,
    ) -> None:
        """Update the original approval message with the decision."""
        if decision.approved:
            status_emoji = "✅"
            status_text = "Approved"
        else:
            status_emoji = "❌"
            status_text = "Denied"

        approver = decision.approver or "system"
        reason = decision.reason or ""

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{status_emoji} *Tool {status_text}*\n\n"
                        f"*Tool:* `{request.tool_name}`\n"
                        f"*Decision:* {status_text}"
                        + (f" by <@{approver}>" if decision.approver else "")
                        + (f"\n*Reason:* {reason}" if reason else "")
                    ),
                },
            },
        ]

        try:
            data = await self._slack_api("chat.update", {
                "channel": channel,
                "ts": message_ts,
                "text": f"{status_emoji} Tool {status_text}: {request.tool_name}",
                "blocks": blocks,
            }, session=session)
            if not data.get("ok"):
                logger.warning(f"Failed to update Slack message: {data.get('error')}")
        except Exception as e:
            logger.warning(f"Failed to update Slack message: {e}")
