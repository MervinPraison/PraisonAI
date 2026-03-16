"""
Unit tests for EmailBot implementation.

Tests cover:
- Platform registry resolution
- Lazy import
- YAML config validation
- EmailBot class structure and BotProtocol compliance
- Auto-reply detection
- Blocked sender detection
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import email
from email.mime.text import MIMEText


class TestEmailPlatformRegistry:
    """Test email platform registration in SDK."""
    
    def test_email_in_builtin_platforms(self):
        """Verify email is registered in _BUILTIN_PLATFORMS."""
        from praisonai.bots._registry import _BUILTIN_PLATFORMS
        
        assert "email" in _BUILTIN_PLATFORMS
        assert _BUILTIN_PLATFORMS["email"] == ("praisonai.bots.email", "EmailBot")
    
    def test_resolve_adapter_returns_email_bot(self):
        """Verify resolve_adapter('email') returns EmailBot class."""
        from praisonai.bots._registry import resolve_adapter
        
        EmailBot = resolve_adapter("email")
        assert EmailBot.__name__ == "EmailBot"
    
    def test_list_platforms_includes_email(self):
        """Verify list_platforms() includes email."""
        from praisonai.bots._registry import list_platforms
        
        platforms = list_platforms()
        assert "email" in platforms


class TestEmailLazyImport:
    """Test lazy import of EmailBot."""
    
    def test_lazy_import_from_bots_module(self):
        """Verify EmailBot can be imported from praisonai.bots."""
        from praisonai.bots import EmailBot
        
        assert EmailBot is not None
        assert EmailBot.__name__ == "EmailBot"
    
    def test_email_bot_in_all(self):
        """Verify EmailBot is in __all__."""
        from praisonai.bots import __all__
        
        assert "EmailBot" in __all__


class TestEmailTokenEnvMap:
    """Test email token environment variable mapping."""
    
    def test_email_in_token_env_map(self):
        """Verify email is in _TOKEN_ENV_MAP."""
        from praisonai.bots.bot import _TOKEN_ENV_MAP
        
        assert "email" in _TOKEN_ENV_MAP
        assert _TOKEN_ENV_MAP["email"] == "EMAIL_APP_PASSWORD"
    
    def test_email_in_extra_env_map(self):
        """Verify email extras are in _EXTRA_ENV_MAP."""
        from praisonai.bots.bot import _EXTRA_ENV_MAP
        
        assert "email" in _EXTRA_ENV_MAP
        assert "email_address" in _EXTRA_ENV_MAP["email"]
        assert "imap_server" in _EXTRA_ENV_MAP["email"]
        assert "smtp_server" in _EXTRA_ENV_MAP["email"]


class TestEmailYamlValidation:
    """Test YAML config validation for email platform."""
    
    def test_valid_platforms_includes_email(self):
        """Verify email is in valid_platforms set."""
        from praisonai.bots._config_schema import validate_bot_config
        
        # This should not raise
        config = validate_bot_config({
            "channels": {
                "email": {"token": "test_token"}
            }
        })
        assert "email" in config.channels
    
    def test_yaml_schema_accepts_email_channel(self):
        """Verify BotYamlSchema accepts email channel."""
        from praisonai.bots._config_schema import BotYamlSchema
        
        schema = BotYamlSchema(
            channels={"email": {"token": "test"}}
        )
        assert "email" in schema.channels


class TestEmailBotStructure:
    """Test EmailBot class structure and properties."""
    
    def test_email_bot_has_required_properties(self):
        """Verify EmailBot has required BotProtocol properties."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(
            token="test_token",
            email_address="test@example.com",
        )
        
        assert hasattr(bot, "is_running")
        assert hasattr(bot, "platform")
        assert hasattr(bot, "bot_user")
        assert bot.platform == "email"
        assert bot.is_running is False
    
    def test_email_bot_has_required_methods(self):
        """Verify EmailBot has required BotProtocol methods."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(
            token="test_token",
            email_address="test@example.com",
        )
        
        # Lifecycle
        assert hasattr(bot, "start")
        assert hasattr(bot, "stop")
        
        # Agent management
        assert hasattr(bot, "set_agent")
        assert hasattr(bot, "get_agent")
        
        # Messaging
        assert hasattr(bot, "send_message")
        assert hasattr(bot, "edit_message")
        assert hasattr(bot, "delete_message")
        
        # Events
        assert hasattr(bot, "on_message")
        assert hasattr(bot, "on_command")
        
        # Health
        assert hasattr(bot, "probe")
        assert hasattr(bot, "health")
    
    def test_email_bot_accepts_config(self):
        """Verify EmailBot accepts BotConfig."""
        from praisonai.bots import EmailBot
        from praisonaiagents.bots import BotConfig
        
        config = BotConfig(
            token="test_token",
            polling_interval=60.0,
        )
        
        bot = EmailBot(
            token="test_token",
            email_address="test@example.com",
            config=config,
        )
        
        assert bot.config.polling_interval == 60.0


class TestEmailBotAutoReplyDetection:
    """Test auto-reply email detection."""
    
    def test_detects_auto_submitted_header(self):
        """Verify bot detects Auto-Submitted header."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        msg = MIMEText("Test body")
        msg["Auto-Submitted"] = "auto-replied"
        
        assert bot._is_auto_reply(msg) is True
    
    def test_detects_x_auto_reply_header(self):
        """Verify bot detects X-Auto-Reply header."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        msg = MIMEText("Test body")
        msg["X-AutoReply"] = "yes"
        
        assert bot._is_auto_reply(msg) is True
    
    def test_normal_email_not_auto_reply(self):
        """Verify normal email is not detected as auto-reply."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        msg = MIMEText("Test body")
        msg["From"] = "user@example.com"
        msg["Subject"] = "Hello"
        
        assert bot._is_auto_reply(msg) is False


class TestEmailBotBlockedSenders:
    """Test blocked sender detection."""
    
    def test_blocks_mailer_daemon(self):
        """Verify bot blocks MAILER-DAEMON."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        assert bot._is_blocked_sender("MAILER-DAEMON@example.com") is True
        assert bot._is_blocked_sender("mailer-daemon@example.com") is True
    
    def test_blocks_noreply(self):
        """Verify bot blocks noreply addresses."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        assert bot._is_blocked_sender("noreply@example.com") is True
        assert bot._is_blocked_sender("no-reply@example.com") is True
        assert bot._is_blocked_sender("donotreply@example.com") is True
    
    def test_allows_normal_sender(self):
        """Verify bot allows normal senders."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        assert bot._is_blocked_sender("user@example.com") is False
        assert bot._is_blocked_sender("support@company.com") is False


class TestEmailBotBodyExtraction:
    """Test email body extraction."""
    
    def test_extracts_plain_text_body(self):
        """Verify bot extracts plain text body."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        msg = MIMEText("Hello, this is a test email.")
        body = bot._extract_body(msg)
        
        assert "Hello, this is a test email." in body
    
    def test_extracts_plain_from_multipart(self):
        """Verify bot extracts plain text from multipart email."""
        from praisonai.bots import EmailBot
        from email.mime.multipart import MIMEMultipart
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("Plain text version", "plain"))
        msg.attach(MIMEText("<p>HTML version</p>", "html"))
        
        body = bot._extract_body(msg)
        
        assert "Plain text version" in body


class TestEmailBotCommandHandler:
    """Test command handler registration."""
    
    def test_on_command_decorator(self):
        """Verify on_command decorator registers handler."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        @bot.on_command("status")
        async def handle_status(message):
            pass
        
        assert "status" in bot._command_handlers
        assert bot._command_handlers["status"] == handle_status
    
    def test_on_message_handler(self):
        """Verify on_message registers handler."""
        from praisonai.bots import EmailBot
        
        bot = EmailBot(token="test", email_address="test@example.com")
        
        @bot.on_message
        def handle_message(message):
            pass
        
        assert handle_message in bot._message_handlers


class TestBotWrapperEmailSupport:
    """Test Bot wrapper supports email platform."""
    
    def test_bot_wrapper_accepts_email_platform(self):
        """Verify Bot('email', ...) works."""
        from praisonai.bots import Bot
        
        bot = Bot("email", token="test_token")
        assert bot.platform == "email"
