"""
Email tools for PraisonAI Agents.

Provides send_email, list_emails, and read_email as plain tool functions
that agents can use during LLM reasoning. Uses AgentMail SDK under the hood.

Requires:
    pip install agentmail
    Set AGENTMAIL_API_KEY and AGENTMAIL_INBOX_ID environment variables.

Example:
    from praisonaiagents import Agent
    from praisonaiagents.tools.email_tools import send_email, list_emails

    agent = Agent(
        instructions="You are an assistant that can send and read emails",
        tools=[send_email, list_emails, read_email]
    )
    result = agent.start("Send an email to bob@example.com saying hello")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded AgentMail client (module-level singleton)
_client = None


def _get_client():
    """Lazy-load the AgentMail client from env vars."""
    global _client
    if _client is None:
        api_key = os.environ.get("AGENTMAIL_API_KEY", "")
        if not api_key:
            raise ValueError(
                "AGENTMAIL_API_KEY environment variable is required. "
                "Get your key at https://agentmail.to"
            )
        try:
            from agentmail import AgentMail
            _client = AgentMail(api_key=api_key)
        except ImportError:
            raise ImportError(
                "agentmail package not installed. "
                "Install with: pip install agentmail"
            )
    return _client


def _get_inbox_id() -> str:
    """Get the default inbox ID from env."""
    inbox_id = os.environ.get("AGENTMAIL_INBOX_ID", "")
    if not inbox_id:
        raise ValueError(
            "AGENTMAIL_INBOX_ID environment variable is required. "
            "Set it to your inbox email, e.g. praison@agentmail.to"
        )
    return inbox_id


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to someone.

    Args:
        to: Recipient email address (e.g. bob@example.com)
        subject: Email subject line
        body: Email body text content

    Returns:
        Confirmation message with the sent message ID
    """
    client = _get_client()
    inbox_id = _get_inbox_id()

    try:
        result = client.inboxes.messages.send(
            inbox_id,
            to=to,
            subject=subject,
            text=body,
        )
        msg_id = getattr(result, "message_id", "unknown")
        thread_id = getattr(result, "thread_id", "")
        logger.info(f"Email sent to {to}: {msg_id}")
        return f"Email sent successfully to {to}. Message ID: {msg_id}, Thread ID: {thread_id}"
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return f"Failed to send email: {e}"


def list_emails(limit: int = 10) -> str:
    """List recent emails in the inbox.

    Args:
        limit: Maximum number of emails to return (default 10)

    Returns:
        Summary of recent emails with sender, subject, and preview
    """
    client = _get_client()
    inbox_id = _get_inbox_id()

    try:
        response = client.inboxes.messages.list(inbox_id, limit=limit)
        msg_list = response.messages if hasattr(response, "messages") else response

        if not msg_list:
            return "No emails found in inbox."

        results = []
        for msg in msg_list:
            sender = getattr(msg, "from_", "") or "unknown"
            subject = getattr(msg, "subject", "(no subject)") or "(no subject)"
            preview = getattr(msg, "preview", "") or ""
            msg_id = getattr(msg, "message_id", "")
            timestamp = getattr(msg, "timestamp", "") or getattr(msg, "created_at", "")

            results.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Preview: {preview[:100]}{'...' if len(preview) > 100 else ''}\n"
                f"  ID: {msg_id}\n"
                f"  Date: {timestamp}"
            )

        count_info = getattr(response, "count", len(msg_list))
        header = f"Found {count_info} email(s) (showing up to {limit}):\n\n"
        return header + "\n\n".join(results)
    except Exception as e:
        logger.error(f"Failed to list emails: {e}")
        return f"Failed to list emails: {e}"


def read_email(message_id: str) -> str:
    """Read the full content of a specific email.

    Args:
        message_id: The message ID to read (get this from list_emails)

    Returns:
        Full email content including sender, subject, and body
    """
    client = _get_client()
    inbox_id = _get_inbox_id()

    # LLMs often strip angle brackets from message IDs — restore them
    if message_id and not message_id.startswith("<"):
        message_id = f"<{message_id}>"

    try:
        msg = client.inboxes.messages.get(inbox_id, message_id)

        sender = getattr(msg, "from_", "") or "unknown"
        to = getattr(msg, "to", []) or []
        subject = getattr(msg, "subject", "(no subject)") or "(no subject)"
        body = getattr(msg, "extracted_text", "") or getattr(msg, "text", "") or ""
        timestamp = getattr(msg, "timestamp", "") or getattr(msg, "created_at", "")
        in_reply_to = getattr(msg, "in_reply_to", "")

        to_str = ", ".join(to) if isinstance(to, list) else str(to)

        result = (
            f"From: {sender}\n"
            f"To: {to_str}\n"
            f"Subject: {subject}\n"
            f"Date: {timestamp}\n"
        )
        if in_reply_to:
            result += f"In-Reply-To: {in_reply_to}\n"
        result += f"\n{body}"

        return result
    except Exception as e:
        logger.error(f"Failed to read email {message_id}: {e}")
        return f"Failed to read email: {e}"


def list_inboxes() -> str:
    """List all email inboxes available for this API key.

    Returns:
        List of inbox email addresses
    """
    client = _get_client()

    try:
        response = client.inboxes.list()
        inbox_list = response.inboxes if hasattr(response, "inboxes") else response

        if not inbox_list:
            return "No inboxes found."

        results = []
        for inbox in inbox_list:
            email = getattr(inbox, "inbox_id", "unknown")
            display = getattr(inbox, "display_name", "") or ""
            label = f"{email} ({display})" if display else email
            results.append(f"- {label}")

        return f"Found {len(results)} inbox(es):\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"Failed to list inboxes: {e}")
        return f"Failed to list inboxes: {e}"
