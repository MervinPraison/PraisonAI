"""
Email tools for PraisonAI Agents.

Generic tools (send_email, list_emails, etc.) auto-detect the backend:
  - If AGENTMAIL_API_KEY is set → uses AgentMail API
  - If EMAIL_ADDRESS + EMAIL_PASSWORD is set → uses IMAP/SMTP
  - If both are set → prefers AgentMail

Backend-specific tools are also available:
  - AgentMail: agentmail_send_email, agentmail_list_emails, etc.
  - SMTP/IMAP: smtp_send_email, smtp_read_inbox, smtp_search_inbox, etc.

Example:
    from praisonaiagents.tools.email_tools import send_email, list_emails, search_emails
    agent = Agent(tools=[send_email, list_emails, search_emails])
    # Works with either AgentMail or Gmail/Outlook — auto-detected from env vars
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded AgentMail client (module-level singleton)
_client = None


def _detect_backend() -> str:
    """Detect which email backend is available.

    Returns 'agentmail' or 'smtp'. Prefers AgentMail if both configured.
    """
    if os.environ.get("AGENTMAIL_API_KEY"):
        return "agentmail"
    if os.environ.get("EMAIL_ADDRESS") and os.environ.get("EMAIL_PASSWORD"):
        return "smtp"
    raise ValueError(
        "No email backend configured. Set either:\n"
        "  - AGENTMAIL_API_KEY (+ AGENTMAIL_INBOX_ID) for AgentMail, or\n"
        "  - EMAIL_ADDRESS + EMAIL_PASSWORD for IMAP/SMTP (Gmail, Outlook, etc.)"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AgentMail Backend
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


def _normalize_message_id(message_id: str) -> str:
    """LLMs often strip angle brackets from message IDs — restore them."""
    if message_id and "@" in message_id and not message_id.startswith("<"):
        return f"<{message_id}>"
    return message_id


def _agentmail_send_email(to: str, subject: str, body: str) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    try:
        result = client.inboxes.messages.send(inbox_id, to=to, subject=subject, text=body)
        msg_id = getattr(result, "message_id", "unknown")
        thread_id = getattr(result, "thread_id", "")
        logger.info(f"Email sent to {to}: {msg_id}")
        return f"Email sent successfully to {to}. Message ID: {msg_id}, Thread ID: {thread_id}"
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return f"Failed to send email: {e}"


def _agentmail_list_emails(limit: int = 10) -> str:
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
        return f"Found {count_info} email(s) (showing up to {limit}):\n\n" + "\n\n".join(results)
    except Exception as e:
        logger.error(f"Failed to list emails: {e}")
        return f"Failed to list emails: {e}"


def _agentmail_read_email(message_id: str) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    message_id = _normalize_message_id(message_id)
    try:
        msg = client.inboxes.messages.get(inbox_id, message_id)
        sender = getattr(msg, "from_", "") or "unknown"
        to = getattr(msg, "to", []) or []
        subject = getattr(msg, "subject", "(no subject)") or "(no subject)"
        body = getattr(msg, "extracted_text", "") or getattr(msg, "text", "") or ""
        timestamp = getattr(msg, "timestamp", "") or getattr(msg, "created_at", "")
        in_reply_to = getattr(msg, "in_reply_to", "")
        to_str = ", ".join(to) if isinstance(to, list) else str(to)
        result = f"From: {sender}\nTo: {to_str}\nSubject: {subject}\nDate: {timestamp}\n"
        if in_reply_to:
            result += f"In-Reply-To: {in_reply_to}\n"
        result += f"\n{body}"
        return result
    except Exception as e:
        logger.error(f"Failed to read email {message_id}: {e}")
        return f"Failed to read email: {e}"


def _agentmail_reply_email(message_id: str, body: str) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    message_id = _normalize_message_id(message_id)
    try:
        result = client.inboxes.messages.reply(inbox_id, message_id, text=body)
        reply_id = getattr(result, "message_id", "unknown")
        logger.info(f"Reply sent: {reply_id}")
        return f"Reply sent successfully (ID: {reply_id})"
    except Exception as e:
        logger.error(f"Failed to reply to {message_id}: {e}")
        return f"Failed to reply: {e}"


def _agentmail_search_emails(
    label: Optional[str] = None,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    limit: int = 20,
) -> str:
    from datetime import datetime as _dt
    client = _get_client()
    inbox_id = _get_inbox_id()
    try:
        kwargs = {"limit": min(limit, 50)}
        if label:
            kwargs["labels"] = [label]
        if after_date:
            kwargs["after"] = _dt.fromisoformat(after_date)
        if before_date:
            kwargs["before"] = _dt.fromisoformat(before_date)
        response = client.inboxes.messages.list(inbox_id, **kwargs)
        msg_list = response.messages if hasattr(response, "messages") else response
        if not msg_list:
            return "No emails matched the search criteria."
        results = []
        for msg in msg_list:
            sender = getattr(msg, "from_", "") or "unknown"
            subject = getattr(msg, "subject", "(no subject)") or "(no subject)"
            preview = getattr(msg, "preview", "") or ""
            msg_id = getattr(msg, "message_id", "")
            timestamp = getattr(msg, "timestamp", "") or getattr(msg, "created_at", "")
            labels = getattr(msg, "labels", []) or []
            results.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Preview: {preview[:100]}{'...' if len(preview) > 100 else ''}\n"
                f"  Labels: {', '.join(labels) if labels else 'none'}\n"
                f"  ID: {msg_id}\n"
                f"  Date: {timestamp}"
            )
        return f"Found {len(results)} email(s):\n\n" + "\n\n".join(results)
    except Exception as e:
        logger.error(f"Failed to search emails: {e}")
        return f"Failed to search emails: {e}"


def _agentmail_archive_email(message_id: str) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    message_id = _normalize_message_id(message_id)
    try:
        client.inboxes.messages.update(
            inbox_id, message_id,
            add_labels=["ARCHIVED"], remove_labels=["INBOX"],
        )
        logger.info(f"Email archived: {message_id}")
        return f"Email archived successfully (ID: {message_id})"
    except Exception as e:
        logger.error(f"Failed to archive email {message_id}: {e}")
        return f"Failed to archive email: {e}"


def _agentmail_forward_email(message_id: str, to: str, note: Optional[str] = None) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    message_id = _normalize_message_id(message_id)
    try:
        kwargs = {"to": to}
        if note:
            kwargs["text"] = note
        result = client.inboxes.messages.forward(inbox_id, message_id, **kwargs)
        fwd_id = getattr(result, "message_id", "unknown")
        logger.info(f"Email forwarded to {to}: {fwd_id}")
        return f"Email forwarded to {to} (ID: {fwd_id})"
    except Exception as e:
        logger.error(f"Failed to forward email {message_id}: {e}")
        return f"Failed to forward email: {e}"


def _agentmail_draft_email(to: str, subject: str, body: str) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    try:
        result = client.inboxes.drafts.create(inbox_id, to=[to], subject=subject, text=body)
        draft_id = getattr(result, "draft_id", "unknown")
        logger.info(f"Draft created: {draft_id}")
        return f"Draft created (ID: {draft_id}). Use send_draft to send it."
    except Exception as e:
        logger.error(f"Failed to create draft: {e}")
        return f"Failed to create draft: {e}"


def _agentmail_send_draft(draft_id: str) -> str:
    client = _get_client()
    inbox_id = _get_inbox_id()
    try:
        result = client.inboxes.drafts.send(inbox_id, draft_id)
        msg_id = getattr(result, "message_id", "unknown")
        logger.info(f"Draft sent: {msg_id}")
        return f"Draft sent successfully (Message ID: {msg_id})"
    except Exception as e:
        logger.error(f"Failed to send draft {draft_id}: {e}")
        return f"Failed to send draft: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SMTP/IMAP Backend — uses standard mailbox credentials
# Zero external dependencies (Python stdlib smtplib + imaplib)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


def _imap_connect(readonly: bool = True):
    """Connect to IMAP and select INBOX. Returns (mail, email_addr)."""
    import imaplib
    email_addr, password, imap_server, imap_port = _get_imap_config()
    mail = imaplib.IMAP4_SSL(imap_server, imap_port)
    mail.login(email_addr, password)
    mail.select("INBOX", readonly=readonly)
    return mail, email_addr


def _decode_header_value(raw_value: str) -> str:
    """Decode a MIME-encoded header value."""
    from email.header import decode_header
    parts = decode_header(raw_value)
    result = ""
    for part, charset in parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += part
    return result


def _extract_body_preview(msg, max_len: int = 100) -> str:
    """Extract plain text body preview from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )[:max_len]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )[:max_len]
    return ""


def _smtp_send_email(to: str, subject: str, body: str) -> str:
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


def _smtp_list_emails(limit: int = 10) -> str:
    import email as email_lib
    try:
        mail, _ = _imap_connect(readonly=True)
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0]:
            mail.logout()
            return "No emails found in inbox."
        msg_ids = data[0].split()
        latest_ids = msg_ids[-limit:]
        latest_ids.reverse()
        results = []
        for uid in latest_ids:
            status, msg_data = mail.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            msg = email_lib.message_from_bytes(msg_data[0][1])
            subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            sender = msg.get("From", "unknown")
            date = msg.get("Date", "")
            preview = _extract_body_preview(msg)
            results.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Preview: {preview}{'...' if len(preview) >= 100 else ''}\n"
                f"  Date: {date}"
            )
        mail.logout()
        if not results:
            return "No emails found in inbox."
        return f"Found {len(results)} email(s):\n\n" + "\n\n".join(results)
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to read inbox: {e}")
        return f"Failed to read inbox: {e}"


def _smtp_read_email(message_id: str) -> str:
    import email as email_lib
    try:
        mail, _ = _imap_connect(readonly=True)
        # Search by Message-ID header
        search_id = message_id if message_id.startswith("<") else f"<{message_id}>"
        status, data = mail.search(None, f'HEADER Message-ID "{search_id}"')
        if status != "OK" or not data[0]:
            mail.logout()
            return f"Email not found with Message-ID: {message_id}"
        uid = data[0].split()[0]
        status, msg_data = mail.fetch(uid, "(RFC822)")
        mail.logout()
        if status != "OK":
            return f"Failed to fetch email: {message_id}"
        msg = email_lib.message_from_bytes(msg_data[0][1])
        subject = _decode_header_value(msg.get("Subject", "(no subject)"))
        sender = msg.get("From", "unknown")
        to = msg.get("To", "")
        date = msg.get("Date", "")
        body = _extract_body_preview(msg, max_len=10000)
        result = f"From: {sender}\nTo: {to}\nSubject: {subject}\nDate: {date}\n\n{body}"
        return result
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to read email {message_id}: {e}")
        return f"Failed to read email: {e}"


def _smtp_reply_email(message_id: str, body: str) -> str:
    import smtplib
    import email as email_lib
    from email.mime.text import MIMEText
    try:
        # Read original email to get sender and subject
        mail, email_addr = _imap_connect(readonly=True)
        search_id = message_id if message_id.startswith("<") else f"<{message_id}>"
        status, data = mail.search(None, f'HEADER Message-ID "{search_id}"')
        if status != "OK" or not data[0]:
            mail.logout()
            return f"Original email not found: {message_id}"
        uid = data[0].split()[0]
        status, msg_data = mail.fetch(uid, "(RFC822)")
        mail.logout()
        if status != "OK":
            return f"Failed to fetch original email: {message_id}"
        original = email_lib.message_from_bytes(msg_data[0][1])
        reply_to = original.get("Reply-To") or original.get("From", "")
        subject = original.get("Subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        # Send reply
        _, password, smtp_server, smtp_port = _get_smtp_config()
        msg = MIMEText(body, "plain")
        msg["From"] = email_addr
        msg["To"] = reply_to
        msg["Subject"] = subject
        msg["In-Reply-To"] = search_id
        msg["References"] = search_id
        msg["Auto-Submitted"] = "auto-replied"
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_addr, password)
            server.send_message(msg)
        logger.info(f"Reply sent to {reply_to}")
        return f"Reply sent to {reply_to}"
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to reply to {message_id}: {e}")
        return f"Failed to reply: {e}"


def _smtp_search_emails(
    query: Optional[str] = None,
    from_addr: Optional[str] = None,
    subject: Optional[str] = None,
    limit: int = 20,
) -> str:
    import email as email_lib
    try:
        mail, _ = _imap_connect(readonly=True)
        # Build IMAP search criteria
        criteria = []
        if from_addr:
            criteria.append(f'FROM "{from_addr}"')
        if subject:
            criteria.append(f'SUBJECT "{subject}"')
        if query:
            criteria.append(f'TEXT "{query}"')
        if not criteria:
            criteria.append("ALL")
        search_str = " ".join(criteria)
        status, data = mail.search(None, search_str)
        if status != "OK" or not data[0]:
            mail.logout()
            return "No emails matched the search criteria."
        msg_ids = data[0].split()
        latest_ids = msg_ids[-min(limit, 50):]
        latest_ids.reverse()
        results = []
        for uid in latest_ids:
            status, msg_data = mail.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            msg = email_lib.message_from_bytes(msg_data[0][1])
            msg_subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            sender = msg.get("From", "unknown")
            date = msg.get("Date", "")
            mid = msg.get("Message-ID", "")
            preview = _extract_body_preview(msg)
            results.append(
                f"- From: {sender}\n"
                f"  Subject: {msg_subject}\n"
                f"  Preview: {preview}{'...' if len(preview) >= 100 else ''}\n"
                f"  ID: {mid}\n"
                f"  Date: {date}"
            )
        mail.logout()
        if not results:
            return "No emails matched the search criteria."
        return f"Found {len(results)} email(s):\n\n" + "\n\n".join(results)
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to search emails: {e}")
        return f"Failed to search emails: {e}"


def _smtp_archive_email(message_id: str) -> str:
    try:
        import imaplib
        mail, email_addr = _imap_connect(readonly=False)
        search_id = message_id if message_id.startswith("<") else f"<{message_id}>"
        status, data = mail.search(None, f'HEADER Message-ID "{search_id}"')
        if status != "OK" or not data[0]:
            mail.logout()
            return f"Email not found: {message_id}"
        uid = data[0].split()[0]
        # Gmail: copy to All Mail, then delete from INBOX
        # Other: just mark as \Seen and \Deleted
        domain = email_addr.split("@")[-1].lower()
        if domain in ("gmail.com", "googlemail.com") or os.environ.get("EMAIL_IMAP_SERVER", "").endswith("gmail.com"):
            mail.copy(uid, "[Gmail]/All Mail")
            mail.store(uid, "+FLAGS", "\\Deleted")
        else:
            mail.store(uid, "+FLAGS", "(\\Seen \\Deleted)")
        mail.expunge()
        mail.logout()
        logger.info(f"Email archived: {message_id}")
        return f"Email archived successfully (ID: {message_id})"
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to archive email {message_id}: {e}")
        return f"Failed to archive email: {e}"


def _smtp_draft_email(to: str, subject: str, body: str) -> str:
    import imaplib
    import time
    from email.mime.text import MIMEText
    try:
        email_addr, password, imap_server, imap_port = _get_imap_config()
        msg = MIMEText(body, "plain")
        msg["From"] = email_addr
        msg["To"] = to
        msg["Subject"] = subject
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_addr, password)
        # Gmail uses [Gmail]/Drafts, others use Drafts or DRAFTS
        domain = email_addr.split("@")[-1].lower()
        if domain in ("gmail.com", "googlemail.com") or imap_server.endswith("gmail.com"):
            drafts_folder = "[Gmail]/Drafts"
        else:
            drafts_folder = "Drafts"
        mail.append(drafts_folder, "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        mail.logout()
        logger.info(f"Draft saved to {drafts_folder}")
        return f"Draft saved to {drafts_folder} (To: {to}, Subject: {subject})"
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Failed to save draft: {e}")
        return f"Failed to save draft: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Generic Tools — Auto-detect backend
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to someone.

    Auto-detects backend: AgentMail (if AGENTMAIL_API_KEY set) or
    SMTP (if EMAIL_ADDRESS + EMAIL_PASSWORD set).

    Args:
        to: Recipient email address (e.g. bob@example.com)
        subject: Email subject line
        body: Email body text content

    Returns:
        Confirmation message with the sent message ID
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_send_email(to, subject, body)
    return _smtp_send_email(to, subject, body)


def list_emails(limit: int = 10) -> str:
    """List recent emails in the inbox.

    Auto-detects backend: AgentMail or IMAP.

    Args:
        limit: Maximum number of emails to return (default 10)

    Returns:
        Summary of recent emails with sender, subject, and preview
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_list_emails(limit)
    return _smtp_list_emails(limit)


def read_email(message_id: str) -> str:
    """Read the full content of a specific email.

    Auto-detects backend: AgentMail or IMAP.

    Args:
        message_id: The message ID to read (get this from list_emails)

    Returns:
        Full email content including sender, subject, and body
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_read_email(message_id)
    return _smtp_read_email(message_id)


def reply_email(message_id: str, body: str) -> str:
    """Reply to an email message.

    Auto-detects backend: AgentMail or SMTP.

    Args:
        message_id: The message ID to reply to (get this from list_emails)
        body: Reply body text

    Returns:
        Confirmation with the reply message ID
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_reply_email(message_id, body)
    return _smtp_reply_email(message_id, body)


def search_emails(
    query: Optional[str] = None,
    from_addr: Optional[str] = None,
    subject: Optional[str] = None,
    label: Optional[str] = None,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Search emails by keyword, sender, subject, label, or date range.

    Auto-detects backend: AgentMail or IMAP.
    AgentMail supports: label, after_date, before_date.
    IMAP supports: query (text search), from_addr, subject.

    Args:
        query: Search text in email body (IMAP only)
        from_addr: Filter by sender email (IMAP only)
        subject: Filter by subject text (IMAP only)
        label: Filter by label (AgentMail only, e.g. "INBOX", "SENT")
        after_date: Only emails after this date (ISO format, e.g. "2025-01-15")
        before_date: Only emails before this date (ISO format, e.g. "2025-03-01")
        limit: Maximum number of results (default 20, max 50)

    Returns:
        Matching emails with sender, subject, preview, and ID
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_search_emails(label, after_date, before_date, limit)
    return _smtp_search_emails(query, from_addr, subject, limit)


def archive_email(message_id: str) -> str:
    """Archive an email (remove from inbox, keep in archive).

    Auto-detects backend: AgentMail or IMAP.
    Gmail: moves to All Mail. Other providers: marks as deleted from inbox.

    Args:
        message_id: The message ID to archive (get this from list_emails or search_emails)

    Returns:
        Confirmation message
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_archive_email(message_id)
    return _smtp_archive_email(message_id)


def forward_email(message_id: str, to: str, note: Optional[str] = None) -> str:
    """Forward an email to another recipient.

    Requires AgentMail backend. IMAP/SMTP does not support forwarding
    (workaround: read_email + send_email).

    Args:
        message_id: The message ID to forward (get this from list_emails)
        to: Recipient email address to forward to
        note: Optional note to include above the forwarded message

    Returns:
        Confirmation with the forwarded message ID
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_forward_email(message_id, to, note)
    return "Forward not supported with IMAP. Use read_email + send_email as a workaround."


def draft_email(to: str, subject: str, body: str) -> str:
    """Create an email draft without sending it.

    Auto-detects backend: AgentMail or IMAP.
    AgentMail: use send_draft() to send later.
    IMAP: saves to Drafts folder (send from your email client).

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body text

    Returns:
        Confirmation with draft details
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_draft_email(to, subject, body)
    return _smtp_draft_email(to, subject, body)


def send_draft(draft_id: str) -> str:
    """Send a previously created email draft.

    AgentMail only. IMAP drafts must be sent from your email client.

    Args:
        draft_id: The draft ID to send (get this from draft_email)

    Returns:
        Confirmation with the sent message ID
    """
    backend = _detect_backend()
    if backend == "agentmail":
        return _agentmail_send_draft(draft_id)
    return "send_draft requires AgentMail. IMAP drafts must be sent from your email client."


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AgentMail-only tools (no IMAP equivalent)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def list_inboxes() -> str:
    """List all email inboxes available (AgentMail only).

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


def create_inbox(display_name: Optional[str] = None) -> str:
    """Create a new email inbox (AgentMail only).

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
# Backward-compatible aliases (smtp_ prefix)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def smtp_send_email(to: str, subject: str, body: str) -> str:
    """Send an email using SMTP (Gmail, Outlook, etc.).

    Uses EMAIL_ADDRESS and EMAIL_PASSWORD env vars.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body text

    Returns:
        Confirmation message
    """
    return _smtp_send_email(to, subject, body)


def smtp_read_inbox(limit: int = 10, folder: str = "INBOX") -> str:
    """Read recent emails from your mailbox using IMAP.

    Uses EMAIL_ADDRESS and EMAIL_PASSWORD env vars.

    Args:
        limit: Maximum number of emails to return (default 10)
        folder: Mailbox folder to read from (default INBOX)

    Returns:
        Summary of recent emails with sender, subject, and preview
    """
    return _smtp_list_emails(limit)


def smtp_search_inbox(
    query: Optional[str] = None,
    from_addr: Optional[str] = None,
    subject: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Search emails using IMAP SEARCH.

    Uses EMAIL_ADDRESS and EMAIL_PASSWORD env vars.

    Args:
        query: Search text in email body
        from_addr: Filter by sender email address
        subject: Filter by subject text
        limit: Maximum number of results (default 20)

    Returns:
        Matching emails with sender, subject, preview
    """
    return _smtp_search_emails(query, from_addr, subject, limit)


def smtp_archive_email(message_id: str) -> str:
    """Archive an email using IMAP.

    Gmail: moves to All Mail. Other providers: marks as deleted.

    Args:
        message_id: The Message-ID header value

    Returns:
        Confirmation message
    """
    return _smtp_archive_email(message_id)


def smtp_draft_email(to: str, subject: str, body: str) -> str:
    """Save an email draft using IMAP APPEND.

    Saves to Drafts folder ([Gmail]/Drafts for Gmail).

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body text

    Returns:
        Confirmation message
    """
    return _smtp_draft_email(to, subject, body)
