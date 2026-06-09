"""
Tests for email CC/BCC functionality in PraisonAI email tools.
"""

import pytest
from unittest.mock import patch, MagicMock
from praisonaiagents.tools.email_tools import (
    _parse_email_list,
    send_email, 
    draft_email,
    smtp_send_email, 
    smtp_draft_email,
    _agentmail_send_email,
    _smtp_send_email,
    _agentmail_draft_email,
    _smtp_draft_email,
)


class TestEmailParsing:
    """Test email address parsing functionality."""
    
    def test_parse_single_email(self):
        """Test parsing a single email address."""
        result = _parse_email_list("test@example.com")
        assert result == ["test@example.com"]
    
    def test_parse_comma_separated_emails(self):
        """Test parsing comma-separated email addresses."""
        result = _parse_email_list("test1@example.com, test2@example.com")
        assert result == ["test1@example.com", "test2@example.com"]
    
    def test_parse_email_list(self):
        """Test parsing list of email addresses."""
        result = _parse_email_list(["test1@example.com", "test2@example.com"])
        assert result == ["test1@example.com", "test2@example.com"]
    
    def test_parse_empty_input(self):
        """Test parsing empty input."""
        assert _parse_email_list("") == []
        assert _parse_email_list(None) == []
    
    def test_parse_emails_with_whitespace(self):
        """Test parsing emails with extra whitespace."""
        result = _parse_email_list("  test1@example.com  ,  test2@example.com  ")
        assert result == ["test1@example.com", "test2@example.com"]


class TestFunctionSignatures:
    """Test that all email functions have CC/BCC parameters."""
    
    def test_send_email_has_cc_bcc(self):
        """Test send_email function has CC and BCC parameters."""
        import inspect
        sig = inspect.signature(send_email)
        assert 'cc' in sig.parameters
        assert 'bcc' in sig.parameters
    
    def test_draft_email_has_cc_bcc(self):
        """Test draft_email function has CC and BCC parameters."""
        import inspect
        sig = inspect.signature(draft_email)
        assert 'cc' in sig.parameters
        assert 'bcc' in sig.parameters
    
    def test_smtp_functions_have_cc_bcc(self):
        """Test SMTP functions have CC and BCC parameters."""
        import inspect
        
        sig = inspect.signature(smtp_send_email)
        assert 'cc' in sig.parameters
        assert 'bcc' in sig.parameters
        
        sig = inspect.signature(smtp_draft_email)
        assert 'cc' in sig.parameters
        assert 'bcc' in sig.parameters


class TestAgentMailBackend:
    """Test AgentMail backend CC/BCC functionality."""
    
    @patch('praisonaiagents.tools.email_tools._get_client')
    @patch('praisonaiagents.tools.email_tools._get_inbox_id')
    def test_agentmail_send_with_cc_bcc(self, mock_inbox, mock_client):
        """Test AgentMail send with CC and BCC."""
        # Mock the client and response
        mock_response = MagicMock()
        mock_response.message_id = "test-msg-id"
        mock_response.thread_id = "test-thread-id"
        
        mock_client_instance = MagicMock()
        mock_client_instance.inboxes.messages.send.return_value = mock_response
        mock_client.return_value = mock_client_instance
        mock_inbox.return_value = "test@inbox.com"
        
        result = _agentmail_send_email(
            to="primary@example.com",
            subject="Test Subject",
            body="Test body",
            cc="cc@example.com",
            bcc="bcc@example.com"
        )
        
        # Verify the call was made with correct parameters
        mock_client_instance.inboxes.messages.send.assert_called_once()
        call_args = mock_client_instance.inboxes.messages.send.call_args
        kwargs = call_args[1]
        
        assert kwargs["to"] == "primary@example.com"
        assert kwargs["subject"] == "Test Subject"
        assert kwargs["text"] == "Test body"
        assert kwargs["cc"] == ["cc@example.com"]
        assert kwargs["bcc"] == ["bcc@example.com"]
        
        # Verify success message includes all recipients
        assert "primary@example.com, cc@example.com, bcc@example.com" in result
        assert "test-msg-id" in result


class TestSMTPBackend:
    """Test SMTP backend CC/BCC functionality."""
    
    @patch('praisonaiagents.tools.email_tools._get_smtp_config')
    @patch('smtplib.SMTP')
    def test_smtp_send_with_cc_bcc(self, mock_smtp, mock_config):
        """Test SMTP send with CC and BCC."""
        # Mock configuration
        mock_config.return_value = ("test@example.com", "password", "smtp.example.com", 587)
        
        # Mock SMTP server
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        result = _smtp_send_email(
            to="primary@example.com",
            subject="Test Subject", 
            body="Test body",
            cc="cc@example.com",
            bcc="bcc@example.com"
        )
        
        # Verify SMTP send_message was called with all recipients
        mock_server.send_message.assert_called_once()
        call_args = mock_server.send_message.call_args
        
        # Check that to_addrs includes all recipients
        assert "to_addrs" in call_args[1]
        recipients = call_args[1]["to_addrs"]
        assert "primary@example.com" in recipients
        assert "cc@example.com" in recipients
        assert "bcc@example.com" in recipients
        
        # Verify success message
        assert "Email sent successfully" in result
        assert "primary@example.com, cc@example.com, bcc@example.com" in result


class TestHighLevelFunctions:
    """Test high-level email functions with CC/BCC."""
    
    @patch.dict('os.environ', {}, clear=True)
    def test_send_email_no_backend_configured(self):
        """Test send_email with no backend configured."""
        result = send_email(
            to="test@example.com",
            subject="Test",
            body="Test body",
            cc="cc@example.com"
        )
        assert "No email backend configured" in result
    
    @patch.dict('os.environ', {}, clear=True)  
    def test_draft_email_no_backend_configured(self):
        """Test draft_email with no backend configured."""
        result = draft_email(
            to="test@example.com",
            subject="Test",
            body="Test body",
            bcc="bcc@example.com"
        )
        assert "No email backend configured" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])