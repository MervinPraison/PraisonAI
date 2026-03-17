"""
Email tools for PraisonAI Agents.

Two backends available:

1. **AgentMail** (API-based):
   - Functions: send_email, list_emails, read_email, list_inboxes
   - Requires: pip install agentmail
   - Env vars: AGENTMAIL_API_KEY, AGENTMAIL_INBOX_ID

2. **SMTP/IMAP** (direct mailbox credentials):
   - Functions: smtp_send_email, smtp_read_inbox
   - Requires: nothing (uses Python stdlib smtplib/imaplib)
   - Env vars: EMAIL_ADDRESS, EMAIL_PASSWORD
   - Optional: EMAIL_SMTP_SERVER (default: smtp.gmail.com), EMAIL_IMAP_SERVER (default: imap.gmail.com)

Example (AgentMail):
    from praisonaiagents.tools.email_tools import send_email, list_emails
    agent = Agent(tools=[send_email, list_emails])

Example (SMTP — Gmail/Outlook/any):
    from praisonaiagents.tools.email_tools import smtp_send_email, smtp_read_inbox
    agent = Agent(tools=[smtp_send_email, smtp_read_inbox])
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


def reply_email(message_id: str, body: str) -> str:
    """Reply to an email message.

    Args:
        message_id: The message ID to reply to (get this from list_emails)
        body: Reply body text

    Returns:
        Confirmation with the reply message ID
    """
    client = _get_client()
    inbox_id = _get_inbox_id()

    # Normalize angle brackets (LLMs often strip them)
    if "@" in message_id and not message_id.startswith("<"):
        message_id = f"<{message_id}>"

    try:
        result = client.inboxes.messages.reply(
            inbox_id,
            message_id,
            text=body,
        )
        reply_id = getattr(result, "message_id", "unknown")
        logger.info(f"Reply sent: {reply_id}")
        return f"Reply sent successfully (ID: {reply_id})"
    except Exception as e:
        logger.error(f"Failed to reply to {message_id}: {e}")
        return f"Failed to reply: {e}"


def create_inbox(display_name: Optional[str] = None) -> str:
    """Create a new email inbox on AgentMail.

    Args:
        display_name: Optional display name for the inbox

    Returns:
        Details of the created inbox
    """
    client = _get_client()

    try:
        if display_name:
            try:
                from agentmail.inboxes.types import CreateInboxRequest
                result = client.inboxes.create(
                    request=CreateInboxRequest(display_name=display_name)
                )
            except ImportError:
                # Fallback if agentmail types not available
                result = client.inboxes.create()
        else:
            result = client.inboxes.create()

        inbox_id = getattr(result, "inbox_id", "unknown")
        name = getattr(result, "display_name", "") or ""
        logger.info(f"Inbox created: {inbox_id}")
        label = f"{inbox_id} ({name})" if name else inbox_id
        return f"Inbox created: {label}"
    except Exception as e:
        logger.error(f"Failed to create inbox: {e}")
        return f"Failed to create inbox: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SMTP/IMAP Backend — uses standard mailbox credentials
# Zero external dependencies (Python stdlib smtplib + imaplib)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Common provider defaults
_SMTP_DEFAULTS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
    "live.com": ("smtp.office365.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
}

_IMAP_DEFAULTS = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "live.com": ("outlook.office365.com", 993),
    "yahoo.com": ("imap.mail.yahoo.com", 993),
    "icloud.com": ("imap.mail.me.com", 993),
}


def _get_smtp_config():
    """Get SMTP config from env vars with smart defaults."""
    email_addr = os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    if not email_addr or not password:
        raise ValueError(
            "EMAIL_ADDRESS and EMAIL_PASSWORD environment variables are required. "
            "For Gmail, use an App Password: https://myaccount.google.com/apppasswords"
        )

    domain = email_addr.split("@")[-1].lower()
    default_smtp = _SMTP_DEFAULTS.get(domain, (f"smtp.{domain}", 587))

    smtp_server = os.environ.get("EMAIL_SMTP_SERVER", default_smtp[0])
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", str(default_smtp[1])))

    return email_addr, password, smtp_server, smtp_port


def _get_imap_config():
    """Get IMAP config from env vars with smart defaults."""
    email_addr = os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    if not email_addr or not password:
        raise ValueError(
            "EMAIL_ADDRESS and EMAIL_PASSWORD environment variables are required."
        )

    domain = email_addr.split("@")[-1].lower()
    default_imap = _IMAP_DEFAULTS.get(domain, (f"imap.{domain}", 993))

    imap_server = os.environ.get("EMAIL_IMAP_SERVER", default_imap[0])
    imap_port = int(os.environ.get("EMAIL_IMAP_PORT", str(default_imap[1])))

    return email_addr, password, imap_server, imap_port


def smtp_send_email(to: str, subject: str, body: str) -> str:
    """Send an email using SMTP with your own email credentials.

    Uses EMAIL_ADDRESS and EMAIL_PASSWORD env vars. Works with Gmail,
    Outlook, Yahoo, iCloud, or any SMTP server.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body text

    Returns:
        Confirmation message
    """
    import smtplib
    from email.mime.text import MIMEText

    try:
        email_addr, password, smtp_server, smtp_port = _get_smtp_config()

        msg = MIMEText(body, "plain")
        msg["From"] = email_addr
        msg["To"] = to
        msg["Subject"] = subject

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_addr, password)
            server.send_message(msg)

        logger.info(f"SMTP email sent to {to}")
        return f"Email sent successfully to {to} from {email_addr}"
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to send SMTP email to {to}: {e}")
        return f"Failed to send email: {e}"


def smtp_read_inbox(limit: int = 10, folder: str = "INBOX") -> str:
    """Read recent emails from your mailbox using IMAP.

    Uses EMAIL_ADDRESS and EMAIL_PASSWORD env vars. Works with Gmail,
    Outlook, Yahoo, iCloud, or any IMAP server.

    Args:
        limit: Maximum number of emails to return (default 10)
        folder: Mailbox folder to read from (default INBOX)

    Returns:
        Summary of recent emails with sender, subject, and preview
    """
    import imaplib
    import email as email_lib
    from email.header import decode_header

    try:
        email_addr, password, imap_server, imap_port = _get_imap_config()

        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_addr, password)
        mail.select(folder, readonly=True)

        # Search for all emails, get latest N
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0]:
            mail.logout()
            return "No emails found in inbox."

        msg_ids = data[0].split()
        latest_ids = msg_ids[-limit:]  # Get last N
        latest_ids.reverse()  # Newest first

        results = []
        for uid in latest_ids:
            status, msg_data = mail.fetch(uid, "(RFC822)")
            if status != "OK":
                continue

            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            # Decode subject
            subj_raw = msg.get("Subject", "(no subject)")
            decoded_parts = decode_header(subj_raw)
            subject = ""
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(charset or "utf-8", errors="replace")
                else:
                    subject += part

            sender = msg.get("From", "unknown")
            date = msg.get("Date", "")

            # Extract plain text body preview
            body_preview = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_preview = payload.decode(
                                part.get_content_charset() or "utf-8",
                                errors="replace"
                            )[:100]
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_preview = payload.decode(
                        msg.get_content_charset() or "utf-8",
                        errors="replace"
                    )[:100]

            results.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Preview: {body_preview}{'...' if len(body_preview) >= 100 else ''}\n"
                f"  Date: {date}"
            )

        mail.logout()

        if not results:
            return "No emails found in inbox."

        return f"Found {len(results)} email(s):\n\n" + "\n\n".join(results)
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to read SMTP inbox: {e}")
        return f"Failed to read inbox: {e}"
