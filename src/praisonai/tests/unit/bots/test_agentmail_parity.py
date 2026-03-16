"""
AgentMail Parity Tests — YAML Config, Python API, and AIUI Channel.

Verifies that all three usage paths produce consistent, working results:
1. YAML parity: agentmail-bot.yaml → BotYamlSchema → BotOS
2. Python parity: Bot("agentmail") and AgentMailBot() direct
3. AIUI parity: SUPPORTED_PLATFORMS, _create_bot_direct, token resolution
"""

import os
import sys
import tempfile
import textwrap

import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════
#  YAML PARITY (6 tests)
# ═══════════════════════════════════════════════════════════════════

class TestYamlParityAgentMail:
    """Verify YAML config files work for agentmail platform."""

    def test_yaml_schema_accepts_agentmail(self):
        """BotYamlSchema should accept agentmail as a valid channel."""
        from praisonai.bots._config_schema import BotYamlSchema

        schema = BotYamlSchema(channels={"agentmail": {"token": "am_test"}})
        assert "agentmail" in schema.channels

    def test_yaml_schema_rejects_unknown_platform(self):
        """BotYamlSchema should reject platforms not in valid set."""
        from praisonai.bots._config_schema import BotYamlSchema
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Unknown channel"):
            BotYamlSchema(channels={"fakeplatform": {"token": "x"}})

    def test_yaml_schema_resolves_env_var(self):
        """Token with ${ENV_VAR} syntax should be resolved."""
        from praisonai.bots._config_schema import BotYamlSchema

        os.environ["_TEST_AM_KEY"] = "am_resolved_key"
        try:
            schema = BotYamlSchema(
                channels={"agentmail": {"token": "${_TEST_AM_KEY}"}}
            )
            assert schema.channels["agentmail"].token == "am_resolved_key"
        finally:
            del os.environ["_TEST_AM_KEY"]

    def test_yaml_file_loads_agentmail_config(self):
        """load_and_validate_bot_yaml should parse agentmail YAML."""
        from praisonai.bots._config_schema import load_and_validate_bot_yaml

        yaml_content = textwrap.dedent("""\
            channels:
              agentmail:
                token: "am_test_token"
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                config = load_and_validate_bot_yaml(f.name)
                assert "agentmail" in config.channels
                assert config.channels["agentmail"].token == "am_test_token"
            finally:
                os.unlink(f.name)

    def test_yaml_multi_channel_agentmail_with_telegram(self):
        """YAML with agentmail + telegram should validate both."""
        from praisonai.bots._config_schema import BotYamlSchema

        schema = BotYamlSchema(channels={
            "agentmail": {"token": "am_test"},
            "telegram": {"token": "tg_test"},
        })
        assert "agentmail" in schema.channels
        assert "telegram" in schema.channels

    def test_yaml_multi_channel_agentmail_with_email(self):
        """YAML with both agentmail + email should validate."""
        from praisonai.bots._config_schema import BotYamlSchema

        schema = BotYamlSchema(channels={
            "agentmail": {"token": "am_test"},
            "email": {"token": "email_test"},
        })
        assert "agentmail" in schema.channels
        assert "email" in schema.channels


# ═══════════════════════════════════════════════════════════════════
#  PYTHON CODE PARITY (8 tests)
# ═══════════════════════════════════════════════════════════════════

class TestPythonCodeParity:
    """Verify Bot() wrapper and AgentMailBot direct usage are equivalent."""

    def test_bot_wrapper_resolves_to_agentmail(self):
        """Bot('agentmail') should resolve adapter to AgentMailBot."""
        from praisonai.bots import Bot
        from praisonai.bots.agentmail import AgentMailBot

        bot = Bot("agentmail", token="am_test")
        assert bot._platform == "agentmail"
        # Adapter is lazy-built; call _build_adapter() to resolve it
        adapter = bot._build_adapter()
        assert isinstance(adapter, AgentMailBot)

    def test_bot_wrapper_reads_api_key_env(self):
        """Bot('agentmail') should read AGENTMAIL_API_KEY env var."""
        from praisonai.bots.bot import _TOKEN_ENV_MAP

        assert _TOKEN_ENV_MAP["agentmail"] == "AGENTMAIL_API_KEY"

    def test_bot_wrapper_extra_env_has_inbox_id_and_domain(self):
        """Extra env should include inbox_id and domain for agentmail."""
        from praisonai.bots.bot import _EXTRA_ENV_MAP

        extra = _EXTRA_ENV_MAP["agentmail"]
        assert "inbox_id" in extra
        assert "domain" in extra

    def test_direct_agentmail_bot_platform(self):
        """AgentMailBot(token=...).platform should be 'agentmail'."""
        from praisonai.bots import AgentMailBot

        bot = AgentMailBot(token="am_test")
        assert bot.platform == "agentmail"

    def test_direct_agentmail_bot_has_inbox_methods(self):
        """AgentMailBot should have create_inbox, list_inboxes, delete_inbox."""
        from praisonai.bots import AgentMailBot

        bot = AgentMailBot(token="am_test")
        assert callable(getattr(bot, "create_inbox", None))
        assert callable(getattr(bot, "list_inboxes", None))
        assert callable(getattr(bot, "delete_inbox", None))

    def test_direct_agentmail_on_command_and_on_message(self):
        """AgentMailBot should support on_command / on_message decorators."""
        from praisonai.bots import AgentMailBot

        bot = AgentMailBot(token="am_test")

        @bot.on_command("test")
        async def handle_test(msg):
            pass

        @bot.on_message
        async def handle_msg(msg):
            pass

        assert "test" in bot._command_handlers
        assert len(bot._message_handlers) == 1

    @pytest.mark.asyncio
    async def test_direct_agentmail_probe_type(self):
        """probe() should return ProbeResult with correct platform."""
        from praisonai.bots import AgentMailBot
        from praisonaiagents.bots import ProbeResult

        bot = AgentMailBot(token="am_test")

        with patch.object(bot, "_get_client") as mock:
            mock_client = MagicMock()
            mock_client.inboxes.list.return_value = []
            mock.return_value = mock_client
            result = await bot.probe()

        assert isinstance(result, ProbeResult)
        assert result.platform == "agentmail"

    def test_email_protocol_structural_match(self):
        """AgentMailBot should structurally match EmailProtocol."""
        from praisonai.bots import AgentMailBot
        from praisonaiagents.bots import EmailProtocol

        # EmailProtocol is @runtime_checkable, so isinstance with structural
        # typing works — the bot has create_inbox, list_inboxes, delete_inbox
        bot = AgentMailBot(token="am_test")

        # Verify the 3 required methods exist with correct signatures
        import inspect
        sig_create = inspect.signature(bot.create_inbox)
        sig_list = inspect.signature(bot.list_inboxes)
        sig_delete = inspect.signature(bot.delete_inbox)

        # create_inbox takes optional domain + **kwargs
        assert "domain" in sig_create.parameters
        # list_inboxes takes no args
        assert len(sig_list.parameters) == 0
        # delete_inbox takes inbox_id
        assert "inbox_id" in sig_delete.parameters


# ═══════════════════════════════════════════════════════════════════
#  AIUI CHANNEL PARITY (6 tests)
# ═══════════════════════════════════════════════════════════════════

class TestAIUIChannelParity:
    """Verify AIUI channels.py supports email and agentmail correctly."""

    def test_supported_platforms_includes_email(self):
        """SUPPORTED_PLATFORMS must include 'email'."""
        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "..", "..",
            "PraisonAIUI", "src"
        ))
        try:
            from praisonaiui.features.channels import SUPPORTED_PLATFORMS
            assert "email" in SUPPORTED_PLATFORMS
        except ImportError:
            pytest.skip("praisonaiui not installed")

    def test_supported_platforms_includes_agentmail(self):
        """SUPPORTED_PLATFORMS must include 'agentmail'."""
        try:
            from praisonaiui.features.channels import SUPPORTED_PLATFORMS
            assert "agentmail" in SUPPORTED_PLATFORMS
        except ImportError:
            pytest.skip("praisonaiui not installed")

    def test_create_bot_direct_has_agentmail_mapping(self):
        """_create_bot_direct source must reference AgentMailBot."""
        import inspect
        try:
            from praisonaiui.features.channels import ChannelsFeature
            src = inspect.getsource(ChannelsFeature._create_bot_direct)
            assert "praisonai.bots.agentmail.AgentMailBot" in src
        except ImportError:
            pytest.skip("praisonaiui not installed")

    def test_create_bot_direct_has_email_mapping(self):
        """_create_bot_direct source must reference EmailBot."""
        import inspect
        try:
            from praisonaiui.features.channels import ChannelsFeature
            src = inspect.getsource(ChannelsFeature._create_bot_direct)
            assert "praisonai.bots.email.EmailBot" in src
        except ImportError:
            pytest.skip("praisonaiui not installed")

    def test_token_resolution_agentmail_uses_api_key(self):
        """_start_channel_bot must resolve agentmail via api_key / AGENTMAIL_API_KEY."""
        import inspect
        try:
            from praisonaiui.features.channels import ChannelsFeature
            src = inspect.getsource(ChannelsFeature._start_channel_bot)
            assert "AGENTMAIL_API_KEY" in src
            assert "api_key" in src
        except ImportError:
            pytest.skip("praisonaiui not installed")

    def test_token_resolution_email_uses_app_password(self):
        """_start_channel_bot must resolve email via app_password / EMAIL_APP_PASSWORD."""
        import inspect
        try:
            from praisonaiui.features.channels import ChannelsFeature
            src = inspect.getsource(ChannelsFeature._start_channel_bot)
            assert "EMAIL_APP_PASSWORD" in src
            assert "app_password" in src
        except ImportError:
            pytest.skip("praisonaiui not installed")
