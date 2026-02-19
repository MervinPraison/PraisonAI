"""
Telegram Approval Backend for PraisonAI Agents.

Implements the ApprovalProtocol by sending messages with inline keyboard
buttons to Telegram and polling ``getUpdates`` for callback_query responses.

Uses raw aiohttp HTTP calls to the Telegram Bot API — does NOT depend on
``python-telegram-bot`` to avoid getUpdates conflicts with a running TelegramBot.

Usage::

    from praisonaiagents import Agent
    from praisonai.bots import TelegramApproval

    agent = Agent(
        name="assistant",
        tools=[execute_command],
        approval=TelegramApproval(chat_id="123456789"),  # token from TELEGRAM_BOT_TOKEN env
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

from ._approval_base import classify_keyword, classify_with_llm, sync_wrapper

logger = logging.getLogger(__name__)


class TelegramApproval:
    """Approval backend that sends Telegram messages with inline buttons.

    Posts a formatted message with Approve/Deny inline keyboard buttons,
    then polls ``getUpdates`` for ``callback_query`` matching the message.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.

    Args:
        token: Telegram bot token. Falls back to ``TELEGRAM_BOT_TOKEN`` env var.
        chat_id: Telegram chat ID (user or group) to send approval requests to.
        timeout: Max seconds to wait for a response (default 300 = 5 min).
        poll_interval: Seconds between polls (default 2.0).

    Example::

        from praisonai.bots import TelegramApproval
        agent = Agent(name="bot", approval=TelegramApproval(chat_id="123456789"))
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 300,
        poll_interval: float = 2.0,
    ):
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not self._token:
            raise ValueError(
                "Telegram bot token is required. Pass token= or set TELEGRAM_BOT_TOKEN env var."
            )
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._timeout = timeout
        self._poll_interval = poll_interval
        # Optional: set PRAISONAI_TELEGRAM_SSL_VERIFY=false to skip SSL verify (e.g. corporate proxy / CA issues)
        _v = os.environ.get("PRAISONAI_TELEGRAM_SSL_VERIFY", "true").lower()
        self._ssl_verify = _v not in ("false", "0", "no")

    def __repr__(self) -> str:
        masked = f"...{self._token[-4:]}" if len(self._token) > 4 else "***"
        return f"TelegramApproval(chat_id={self._chat_id!r}, token={masked!r})"

    # ── Internal Telegram API helper ───────────────────────────────────

    def _connector(self):
        """aiohttp connector with optional SSL verify (for corporate/proxy CA issues)."""
        import aiohttp
        return aiohttp.TCPConnector(ssl=self._ssl_verify)

    async def _telegram_api(
        self,
        method: str,
        payload: Dict[str, Any],
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Call a Telegram Bot API method. Override in tests for mocking."""
        import aiohttp

        url = f"https://api.telegram.org/bot{self._token}/{method}"
        if session is not None:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return await resp.json()
        else:
            async with aiohttp.ClientSession(connector=self._connector()) as _session:
                async with _session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    return await resp.json()

    # ── ApprovalProtocol implementation ─────────────────────────────────

    async def request_approval(self, request) -> Any:
        """Send a Telegram message with inline buttons and poll for response."""
        from praisonaiagents.approval.protocols import ApprovalDecision
        import aiohttp

        chat_id = self._chat_id
        if not chat_id:
            return ApprovalDecision(
                approved=False,
                reason="No Telegram chat_id configured",
            )

        async with aiohttp.ClientSession(connector=self._connector()) as session:
            # 1. Send approval message with inline keyboard
            text = self._build_message_text(request)
            keyboard = self._build_inline_keyboard(request)

            try:
                post_data = await self._telegram_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard,
                }, session=session)

                if not post_data.get("ok"):
                    return ApprovalDecision(
                        approved=False,
                        reason=f"Failed to send Telegram message: {post_data.get('description', 'unknown')}",
                    )

                message_id = post_data["result"]["message_id"]

                # 2. Poll for callback_query response
                decision = await self._poll_for_callback(
                    chat_id, message_id, request=request, session=session,
                )

                # 3. Update original message with result
                await self._update_message(
                    chat_id, message_id, request, decision, session=session,
                )

                return decision

            except Exception as e:
                logger.error(f"TelegramApproval error: {e}")
                return ApprovalDecision(
                    approved=False,
                    reason=f"Telegram approval error: {e}",
                )

    def request_approval_sync(self, request) -> Any:
        """Synchronous wrapper — runs async method in a new event loop."""
        return sync_wrapper(self.request_approval(request), self._timeout)

    # ── Message Builder ────────────────────────────────────────────────

    def _build_message_text(self, request) -> str:
        """Build formatted message text for Telegram."""
        risk_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        emoji = risk_emoji.get(request.risk_level, "⚪")

        args_lines = []
        for key, value in request.arguments.items():
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            args_lines.append(f"  `{key}`: `{val_str}`")
        args_text = "\n".join(args_lines) if args_lines else "  _(none)_"

        agent_line = f"\n*Agent:* {request.agent_name}" if request.agent_name else ""

        return (
            f"🔒 *Tool Approval Required*\n\n"
            f"*Tool:* `{request.tool_name}`\n"
            f"*Risk:* {emoji} {request.risk_level.upper()}{agent_line}\n"
            f"*Arguments:*\n{args_text}\n\n"
            f"_Timeout: {int(self._timeout)}s_"
        )

    def _build_inline_keyboard(self, request) -> Dict[str, Any]:
        """Build Telegram InlineKeyboardMarkup JSON."""
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": "approve"},
                    {"text": "❌ Deny", "callback_data": "deny"},
                ]
            ]
        }

    # ── Polling ─────────────────────────────────────────────────────────

    async def _poll_for_callback(
        self,
        chat_id: str,
        message_id: int,
        request: Optional[Any] = None,
        session: Optional[Any] = None,
    ) -> Any:
        """Poll getUpdates for callback_query matching our message."""
        from praisonaiagents.approval.protocols import ApprovalDecision

        deadline = time.monotonic() + self._timeout
        offset = 0

        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)

            try:
                data = await self._telegram_api("getUpdates", {
                    "offset": offset,
                    "timeout": 1,
                    "allowed_updates": ["callback_query", "message"],
                }, session=session)

                if not data.get("ok"):
                    logger.warning(f"Telegram poll error: {data.get('description')}")
                    continue

                for update in data.get("result", []):
                    update_id = update.get("update_id", 0)
                    if update_id >= offset:
                        offset = update_id + 1

                    # Check callback_query (button press)
                    cb = update.get("callback_query")
                    if cb:
                        cb_msg = cb.get("message", {})
                        if cb_msg.get("message_id") == message_id:
                            cb_data = cb.get("data", "")
                            user = cb.get("from", {})
                            user_id = str(user.get("id", "unknown"))
                            username = user.get("username", user_id)

                            # Answer the callback to remove loading state
                            await self._telegram_api("answerCallbackQuery", {
                                "callback_query_id": cb.get("id"),
                            }, session=session)

                            if cb_data == "approve":
                                return ApprovalDecision(
                                    approved=True,
                                    reason=f"Approved via Telegram by @{username}",
                                    approver=user_id,
                                    metadata={"platform": "telegram", "message_id": message_id},
                                )
                            else:
                                return ApprovalDecision(
                                    approved=False,
                                    reason=f"Denied via Telegram by @{username}",
                                    approver=user_id,
                                    metadata={"platform": "telegram", "message_id": message_id},
                                )

                    # Check text reply as fallback
                    msg = update.get("message")
                    if msg:
                        reply_to = msg.get("reply_to_message", {})
                        msg_chat_id = str(msg.get("chat", {}).get("id", ""))
                        if (
                            msg_chat_id == str(chat_id)
                            and reply_to.get("message_id") == message_id
                        ):
                            text = msg.get("text", "").strip()
                            user = msg.get("from", {})
                            user_id = str(user.get("id", "unknown"))
                            kw = classify_keyword(text)

                            if kw == "approve":
                                return ApprovalDecision(
                                    approved=True,
                                    reason=f"Approved via Telegram by user {user_id}",
                                    approver=user_id,
                                    metadata={"platform": "telegram", "message_id": message_id},
                                )
                            if kw == "deny":
                                return ApprovalDecision(
                                    approved=False,
                                    reason=f"Denied via Telegram by user {user_id}",
                                    approver=user_id,
                                    metadata={"platform": "telegram", "message_id": message_id},
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
                                            "platform": "telegram",
                                            "message_id": message_id,
                                            "llm_classified": True,
                                            "original_text": text,
                                        },
                                    )
                                except Exception as llm_err:
                                    logger.warning(f"LLM classification failed: {llm_err}")

            except Exception as e:
                logger.warning(f"Telegram poll exception: {e}")

        return ApprovalDecision(
            approved=False,
            reason=f"Timed out waiting for Telegram approval ({int(self._timeout)}s)",
            metadata={"platform": "telegram", "timeout": True},
        )

    # ── Message Update ──────────────────────────────────────────────────

    async def _update_message(
        self,
        chat_id: str,
        message_id: int,
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

        new_text = (
            f"{status_emoji} *Tool {status_text}*\n\n"
            f"*Tool:* `{request.tool_name}`\n"
            f"*Decision:* {status_text}"
            + (f" by user {approver}" if decision.approver else "")
            + (f"\n*Reason:* {reason}" if reason else "")
        )

        try:
            data = await self._telegram_api("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": new_text,
                "parse_mode": "Markdown",
            }, session=session)
            if not data.get("ok"):
                logger.warning(f"Failed to update Telegram message: {data.get('description')}")
        except Exception as e:
            logger.warning(f"Failed to update Telegram message: {e}")
