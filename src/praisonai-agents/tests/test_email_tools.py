"""Unit tests for email_tools.py — mocks AgentMail SDK, no real API calls."""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Ensure the SDK is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEmailTools(unittest.TestCase):
    """Tests for send_email, list_emails, read_email, list_inboxes."""

    def setUp(self):
        """Reset module-level client cache before each test."""
        import praisonaiagents.tools.email_tools as et
        et._client = None
        os.environ["AGENTMAIL_API_KEY"] = "am_test_key"
        os.environ["AGENTMAIL_INBOX_ID"] = "test@agentmail.to"

    def tearDown(self):
        import praisonaiagents.tools.email_tools as et
        et._client = None
        os.environ.pop("AGENTMAIL_API_KEY", None)
        os.environ.pop("AGENTMAIL_INBOX_ID", None)

    def _mock_agentmail_module(self):
        """Create a mock agentmail module with AgentMail class."""
        mock_client = MagicMock()
        mock_agentmail_cls = MagicMock(return_value=mock_client)
        
        mock_module = types.ModuleType("agentmail")
        mock_module.AgentMail = mock_agentmail_cls
        return mock_module, mock_client

    # ── send_email ──────────────────────────────────────────────

    def test_send_email_success(self):
        mock_mod, mock_client = self._mock_agentmail_module()
        
        # Mock the send response
        mock_result = MagicMock()
        mock_result.message_id = "msg_123"
        mock_result.thread_id = "thread_456"
        mock_client.inboxes.messages.send.return_value = mock_result
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import send_email
            import praisonaiagents.tools.email_tools as et
            et._client = None  # Force re-creation
            
            result = send_email(to="bob@example.com", subject="Hello", body="Hi there")
        
        self.assertIn("sent successfully", result)
        self.assertIn("msg_123", result)
        mock_client.inboxes.messages.send.assert_called_once_with(
            "test@agentmail.to",
            to="bob@example.com",
            subject="Hello",
            text="Hi there",
        )

    def test_send_email_uses_text_not_body(self):
        """Critical: SDK uses text= not body= parameter."""
        mock_mod, mock_client = self._mock_agentmail_module()
        mock_result = MagicMock()
        mock_result.message_id = "msg_1"
        mock_result.thread_id = "t1"
        mock_client.inboxes.messages.send.return_value = mock_result
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import send_email
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            send_email(to="x@y.z", subject="s", body="b")
        
        call_kwargs = mock_client.inboxes.messages.send.call_args
        # Must use text= keyword, never body=
        self.assertIn("text", call_kwargs.kwargs)
        self.assertNotIn("body", call_kwargs.kwargs)

    def test_send_email_failure_returns_error(self):
        mock_mod, mock_client = self._mock_agentmail_module()
        mock_client.inboxes.messages.send.side_effect = Exception("Network error")
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import send_email
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            result = send_email(to="x@y.z", subject="s", body="b")
        
        self.assertIn("Failed to send", result)
        self.assertIn("Network error", result)

    # ── list_emails ─────────────────────────────────────────────

    def test_list_emails_success(self):
        mock_mod, mock_client = self._mock_agentmail_module()
        
        mock_msg = MagicMock()
        mock_msg.from_ = "alice@example.com"
        mock_msg.subject = "Test Subject"
        mock_msg.preview = "Preview text"
        mock_msg.message_id = "msg_100"
        mock_msg.timestamp = "2026-03-16"
        
        mock_response = MagicMock()
        mock_response.messages = [mock_msg]
        mock_response.count = 1
        mock_client.inboxes.messages.list.return_value = mock_response
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import list_emails
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            result = list_emails(limit=5)
        
        self.assertIn("alice@example.com", result)
        self.assertIn("Test Subject", result)
        self.assertIn("msg_100", result)
        # Must use .messages attribute, not iterate response directly
        mock_client.inboxes.messages.list.assert_called_once_with(
            "test@agentmail.to", limit=5
        )

    def test_list_emails_uses_from_underscore(self):
        """Critical: SDK uses msg.from_ not msg.from_address."""
        mock_mod, mock_client = self._mock_agentmail_module()
        
        mock_msg = MagicMock(spec=["from_", "subject", "preview", "message_id", "timestamp"])
        mock_msg.from_ = "sender@test.com"
        mock_msg.subject = "Sub"
        mock_msg.preview = "Pre"
        mock_msg.message_id = "id1"
        mock_msg.timestamp = "now"
        
        mock_response = MagicMock()
        mock_response.messages = [mock_msg]
        mock_response.count = 1
        mock_client.inboxes.messages.list.return_value = mock_response
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import list_emails
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            result = list_emails()
        
        self.assertIn("sender@test.com", result)

    def test_list_emails_empty(self):
        mock_mod, mock_client = self._mock_agentmail_module()
        
        mock_response = MagicMock()
        mock_response.messages = []
        mock_client.inboxes.messages.list.return_value = mock_response
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import list_emails
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            result = list_emails()
        
        self.assertIn("No emails found", result)

    # ── read_email ──────────────────────────────────────────────

    def test_read_email_success(self):
        mock_mod, mock_client = self._mock_agentmail_module()
        
        mock_msg = MagicMock()
        mock_msg.from_ = "sender@test.com"
        mock_msg.to = ["recipient@test.com"]
        mock_msg.subject = "Full Read Test"
        mock_msg.extracted_text = "Full body content here"
        mock_msg.timestamp = "2026-03-16T12:00:00"
        mock_msg.in_reply_to = ""
        mock_client.inboxes.messages.get.return_value = mock_msg
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import read_email
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            result = read_email(message_id="msg_100")
        
        self.assertIn("sender@test.com", result)
        self.assertIn("Full Read Test", result)
        self.assertIn("Full body content here", result)

    # ── list_inboxes ────────────────────────────────────────────

    def test_list_inboxes_success(self):
        mock_mod, mock_client = self._mock_agentmail_module()
        
        mock_inbox = MagicMock()
        mock_inbox.inbox_id = "praison@agentmail.to"
        mock_inbox.display_name = "Praison"
        
        mock_response = MagicMock()
        mock_response.inboxes = [mock_inbox]
        mock_client.inboxes.list.return_value = mock_response
        
        with patch.dict("sys.modules", {"agentmail": mock_mod}):
            from praisonaiagents.tools.email_tools import list_inboxes
            import praisonaiagents.tools.email_tools as et
            et._client = None
            
            result = list_inboxes()
        
        self.assertIn("praison@agentmail.to", result)
        self.assertIn("Praison", result)

    # ── Missing env vars ────────────────────────────────────────

    def test_missing_api_key_raises(self):
        os.environ.pop("AGENTMAIL_API_KEY", None)
        
        import praisonaiagents.tools.email_tools as et
        et._client = None
        
        with self.assertRaises(ValueError) as ctx:
            et._get_client()
        self.assertIn("AGENTMAIL_API_KEY", str(ctx.exception))

    def test_missing_inbox_id_raises(self):
        os.environ.pop("AGENTMAIL_INBOX_ID", None)
        
        import praisonaiagents.tools.email_tools as et
        
        with self.assertRaises(ValueError) as ctx:
            et._get_inbox_id()
        self.assertIn("AGENTMAIL_INBOX_ID", str(ctx.exception))

    # ── Profile registration ────────────────────────────────────

    def test_email_profile_exists(self):
        from praisonaiagents.tools.profiles import get_profile
        profile = get_profile("email")
        self.assertEqual(profile.name, "email")
        self.assertIn("send_email", profile.tools)
        self.assertIn("list_emails", profile.tools)
        self.assertIn("read_email", profile.tools)

    # ── Lazy import via tools package ───────────────────────────

    def test_lazy_import_from_tools_package(self):
        from praisonaiagents.tools import send_email
        from praisonaiagents.tools.email_tools import send_email as direct
        self.assertIs(send_email, direct)


if __name__ == "__main__":
    unittest.main()
