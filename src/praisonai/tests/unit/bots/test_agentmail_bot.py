"""
Unit tests for AgentMailBot implementation.

Tests cover:
- Registry integration
- Lazy import
- YAML validation
- Bot structure and properties
- Email utilities (shared with EmailBot)
- Command and message handlers
"""

import pytest
from unittest.mock import MagicMock, patch


class TestAgentMailPlatformRegistry:
    """Test AgentMail platform registration in SDK."""
    
    def test_agentmail_in_builtin_platforms(self):
        """AgentMail should be in _BUILTIN_PLATFORMS."""
        from praisonai.bots._registry import _BUILTIN_PLATFORMS
        
        assert "agentmail" in _BUILTIN_PLATFORMS
        assert _BUILTIN_PLATFORMS["agentmail"] == ("praisonai.bots.agentmail", "AgentMailBot")
    
    def test_resolve_adapter_returns_agentmail_bot(self):
        """resolve_adapter('agentmail') should return AgentMailBot class."""
        from praisonai.bots._registry import resolve_adapter
        
        cls = resolve_adapter("agentmail")
        assert cls.__name__ == "AgentMailBot"
    
    def test_list_platforms_includes_agentmail(self):
        """list_platforms() should include 'agentmail'."""
        from praisonai.bots._registry import list_platforms
        
        platforms = list_platforms()
        assert "agentmail" in platforms


class TestAgentMailLazyImport:
    """Test lazy import of AgentMailBot."""
    
    def test_lazy_import_from_bots_module(self):
        """AgentMailBot should be importable from praisonai.bots."""
        from praisonai.bots import AgentMailBot
        
        assert AgentMailBot is not None
        assert AgentMailBot.__name__ == "AgentMailBot"
    
    def test_agentmail_bot_in_all(self):
        """AgentMailBot should be in __all__."""
        from praisonai.bots import __all__
        
        assert "AgentMailBot" in __all__


class TestAgentMailTokenEnvMap:
    """Test AgentMail environment variable mappings."""
    
    def test_agentmail_in_token_env_map(self):
        """AgentMail should have token env mapping."""
        from praisonai.bots.bot import _TOKEN_ENV_MAP
        
        assert "agentmail" in _TOKEN_ENV_MAP
        assert _TOKEN_ENV_MAP["agentmail"] == "AGENTMAIL_API_KEY"
    
    def test_agentmail_in_extra_env_map(self):
        """AgentMail should have extra env mappings."""
        from praisonai.bots.bot import _EXTRA_ENV_MAP
        
        assert "agentmail" in _EXTRA_ENV_MAP
        assert "inbox_id" in _EXTRA_ENV_MAP["agentmail"]
        assert "domain" in _EXTRA_ENV_MAP["agentmail"]


class TestAgentMailYamlValidation:
    """Test YAML schema validation for AgentMail channel."""
    
    def test_valid_platforms_includes_agentmail(self):
        """valid_platforms should include 'agentmail'."""
        from praisonai.bots._config_schema import BotYamlSchema
        
        # Create a valid config with agentmail channel
        config = {
            "channels": {
                "agentmail": {
                    "bot_token": "am_test_key"
                }
            }
        }
        
        # Should not raise
        schema = BotYamlSchema(**config)
        assert "agentmail" in schema.channels
    
    def test_yaml_schema_accepts_agentmail_channel(self):
        """BotYamlSchema should accept agentmail as a valid channel."""
        from praisonai.bots._config_schema import BotYamlSchema
        
        config = {
            "channels": {
                "agentmail": {"bot_token": "test"}
            }
        }
        
        schema = BotYamlSchema(**config)
        assert schema.channels is not None


class TestAgentMailBotStructure:
    """Test AgentMailBot class structure."""
    
    def test_agentmail_bot_has_required_properties(self):
        """AgentMailBot should have required properties."""
        from praisonai.bots import AgentMailBot
        
        bot = AgentMailBot(token="test_token")
        
        assert hasattr(bot, 'platform')
        assert hasattr(bot, 'is_running')
        assert hasattr(bot, 'bot_user')
        assert hasattr(bot, 'email_address')
        assert bot.platform == "agentmail"
    
    def test_agentmail_bot_has_required_methods(self):
        """AgentMailBot should have required BotProtocol methods."""
        from praisonai.bots import AgentMailBot
        
        bot = AgentMailBot(token="test_token")
        
        assert hasattr(bot, 'start')
        assert hasattr(bot, 'stop')
        assert hasattr(bot, 'send_message')
        assert hasattr(bot, 'probe')
        assert hasattr(bot, 'health')
        assert hasattr(bot, 'on_message')
        assert hasattr(bot, 'on_command')
    
    def test_agentmail_bot_has_inbox_methods(self):
        """AgentMailBot should have inbox lifecycle methods."""
        from praisonai.bots import AgentMailBot
        
        bot = AgentMailBot(token="test_token")
        
        assert hasattr(bot, 'create_inbox')
        assert hasattr(bot, 'list_inboxes')
        assert hasattr(bot, 'delete_inbox')
    
    def test_agentmail_bot_accepts_config(self):
        """AgentMailBot should accept BotConfig."""
        from praisonai.bots import AgentMailBot
        from praisonaiagents.bots import BotConfig
        
        config = BotConfig(polling_interval=15)
        bot = AgentMailBot(token="test_token", config=config)
        
        assert bot.config == config


class TestEmailUtilsShared:
    """Test shared email utilities work correctly."""
    
    def test_is_auto_reply_detects_auto_submitted(self):
        """is_auto_reply should detect Auto-Submitted header."""
        from praisonai.bots._email_utils import is_auto_reply
        
        headers = {"auto-submitted": "auto-replied"}
        assert is_auto_reply(headers) is True
    
    def test_is_auto_reply_ignores_no_value(self):
        """is_auto_reply should ignore auto-submitted: no."""
        from praisonai.bots._email_utils import is_auto_reply
        
        headers = {"auto-submitted": "no"}
        assert is_auto_reply(headers) is False
    
    def test_is_auto_reply_detects_x_autoreply(self):
        """is_auto_reply should detect X-Autoreply header."""
        from praisonai.bots._email_utils import is_auto_reply
        
        headers = {"x-autoreply": "yes"}
        assert is_auto_reply(headers) is True
    
    def test_is_auto_reply_normal_email(self):
        """is_auto_reply should return False for normal emails."""
        from praisonai.bots._email_utils import is_auto_reply
        
        headers = {"from": "user@example.com", "subject": "Hello"}
        assert is_auto_reply(headers) is False
    
    def test_is_blocked_sender_blocks_mailer_daemon(self):
        """is_blocked_sender should block mailer-daemon."""
        from praisonai.bots._email_utils import is_blocked_sender
        
        assert is_blocked_sender("MAILER-DAEMON@example.com") is True
    
    def test_is_blocked_sender_blocks_noreply(self):
        """is_blocked_sender should block noreply addresses."""
        from praisonai.bots._email_utils import is_blocked_sender
        
        assert is_blocked_sender("noreply@example.com") is True
        assert is_blocked_sender("no-reply@example.com") is True
    
    def test_is_blocked_sender_allows_normal(self):
        """is_blocked_sender should allow normal senders."""
        from praisonai.bots._email_utils import is_blocked_sender
        
        assert is_blocked_sender("user@example.com") is False
    
    def test_extract_email_address_simple(self):
        """extract_email_address should handle simple addresses."""
        from praisonai.bots._email_utils import extract_email_address
        
        assert extract_email_address("user@example.com") == "user@example.com"
    
    def test_extract_email_address_with_name(self):
        """extract_email_address should extract from 'Name <email>' format."""
        from praisonai.bots._email_utils import extract_email_address
        
        assert extract_email_address("John Doe <john@example.com>") == "john@example.com"
    
    def test_normalize_subject_strips_re(self):
        """normalize_subject should strip Re: prefix."""
        from praisonai.bots._email_utils import normalize_subject
        
        assert normalize_subject("Re: Hello") == "Hello"
        assert normalize_subject("RE: RE: Hello") == "Hello"
    
    def test_normalize_subject_strips_fwd(self):
        """normalize_subject should strip Fwd: prefix."""
        from praisonai.bots._email_utils import normalize_subject
        
        assert normalize_subject("Fwd: Hello") == "Hello"


class TestAgentMailBotCommandHandler:
    """Test AgentMailBot command and message handlers."""
    
    def test_on_command_decorator(self):
        """on_command should register command handlers."""
        from praisonai.bots import AgentMailBot
        
        bot = AgentMailBot(token="test_token")
        
        @bot.on_command("help")
        async def help_handler(message):
            pass
        
        assert "help" in bot._command_handlers
    
    def test_on_message_handler(self):
        """on_message should register message handlers."""
        from praisonai.bots import AgentMailBot
        
        bot = AgentMailBot(token="test_token")
        
        @bot.on_message
        def msg_handler(message):
            pass
        
        assert len(bot._message_handlers) == 1


class TestBotWrapperAgentMailSupport:
    """Test Bot wrapper supports agentmail platform."""
    
    def test_bot_wrapper_accepts_agentmail_platform(self):
        """Bot wrapper should accept 'agentmail' as platform."""
        from praisonai.bots import Bot
        
        bot = Bot("agentmail", token="test_token")
        assert bot._platform == "agentmail"


class TestAgentMailBotProbe:
    """Test AgentMailBot probe functionality."""
    
    @pytest.mark.asyncio
    async def test_probe_returns_probe_result(self):
        """probe() should return ProbeResult."""
        from praisonai.bots import AgentMailBot
        from praisonaiagents.bots import ProbeResult
        
        bot = AgentMailBot(token="test_token")
        
        # Mock the client to avoid actual API calls
        with patch.object(bot, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.inboxes.list.return_value = []
            mock_get_client.return_value = mock_client
            
            result = await bot.probe()
            
            assert isinstance(result, ProbeResult)
            assert result.platform == "agentmail"
            assert result.ok is True
    
    @pytest.mark.asyncio
    async def test_probe_handles_import_error(self):
        """probe() should handle missing agentmail package."""
        from praisonai.bots import AgentMailBot
        
        bot = AgentMailBot(token="test_token")
        
        with patch.object(bot, '_get_client', side_effect=ImportError("No module")):
            result = await bot.probe()
            
            assert result.ok is False
            assert "not installed" in result.error


class TestAgentMailBotHealth:
    """Test AgentMailBot health functionality."""
    
    @pytest.mark.asyncio
    async def test_health_returns_health_result(self):
        """health() should return HealthResult."""
        from praisonai.bots import AgentMailBot
        from praisonaiagents.bots import HealthResult
        
        bot = AgentMailBot(token="test_token")
        
        with patch.object(bot, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.inboxes.list.return_value = []
            mock_get_client.return_value = mock_client
            
            result = await bot.health()
            
            assert isinstance(result, HealthResult)
            assert result.platform == "agentmail"
