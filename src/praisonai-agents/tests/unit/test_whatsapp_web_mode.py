"""
Unit tests for WhatsAppBot dual-mode (cloud/web) support.

Tests backward compatibility with existing Cloud API mode and
new Web mode constructor/lifecycle.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Ensure the wrapper package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "praisonai"))


# ── Mode constructor ──────────────────────────────────────────────

class TestModeConstructor:
    """Test WhatsAppBot mode parameter."""

    def test_default_mode_is_cloud(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="test-token", phone_number_id="123")
        assert bot.mode == "cloud"
        assert bot._mode == "cloud"

    def test_explicit_cloud_mode(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="test-token", mode="cloud")
        assert bot.mode == "cloud"

    def test_web_mode(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        assert bot.mode == "web"

    def test_web_mode_no_token_required(self):
        """Web mode should not require token or phone_number_id."""
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        assert bot._token == ""
        assert bot._phone_number_id == ""

    def test_invalid_mode_raises(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        with pytest.raises(ValueError, match="Invalid mode"):
            WhatsAppBot(mode="invalid")

    def test_mode_case_insensitive(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="WEB")
        assert bot.mode == "web"

    def test_mode_whitespace_stripped(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode=" web ")
        assert bot.mode == "web"


# ── Backward compatibility ────────────────────────────────────────

class TestBackwardCompatibility:
    """Ensure existing Cloud API usage is unchanged."""

    def test_cloud_mode_with_all_params(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(
            token="EAA-test",
            phone_number_id="123456",
            verify_token="my-verify",
            app_secret="my-secret",
            webhook_port=9090,
            webhook_path="/hook",
        )
        assert bot._token == "EAA-test"
        assert bot._phone_number_id == "123456"
        assert bot._verify_token == "my-verify"
        assert bot._app_secret == "my-secret"
        assert bot._webhook_port == 9090
        assert bot._webhook_path == "/hook"
        assert bot.mode == "cloud"

    def test_token_from_env_var(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        with patch.dict(os.environ, {"WHATSAPP_ACCESS_TOKEN": "env-token"}):
            bot = WhatsAppBot()
            assert bot._token == "env-token"

    def test_phone_id_from_env_var(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        with patch.dict(os.environ, {"WHATSAPP_PHONE_NUMBER_ID": "env-phone"}):
            bot = WhatsAppBot()
            assert bot._phone_number_id == "env-phone"

    def test_platform_property(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="t")
        assert bot.platform == "whatsapp"

    def test_is_running_initially_false(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="t")
        assert bot.is_running is False


# ── Web mode properties ───────────────────────────────────────────

class TestWebModeProperties:
    """Test Web mode specific behavior."""

    def test_creds_dir_param(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web", creds_dir="/tmp/wa-creds")
        assert bot._creds_dir == "/tmp/wa-creds"

    def test_creds_dir_default_none(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        assert bot._creds_dir is None  # adapter will use its own default

    def test_web_adapter_initially_none(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        assert bot._web_adapter is None

    def test_web_mode_has_session_manager(self):
        """Web mode still uses BotSessionManager for per-user isolation."""
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        assert bot._session_mgr is not None


# ── Start delegation ──────────────────────────────────────────────

class TestStartDelegation:
    """Test that start() delegates to correct mode handler."""

    @pytest.mark.asyncio
    async def test_cloud_mode_calls_start_cloud(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="test", phone_number_id="123", mode="cloud")
        bot._start_cloud_mode = AsyncMock()
        await bot.start()
        bot._start_cloud_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_web_mode_calls_start_web(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        bot._start_web_mode = AsyncMock()
        await bot.start()
        bot._start_web_mode.assert_called_once()


# ── Stop handles both modes ───────────────────────────────────────

class TestStop:
    """Test stop() cleanup for both modes."""

    @pytest.mark.asyncio
    async def test_stop_cloud_mode(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="t", mode="cloud")
        bot._is_running = True
        bot._site = AsyncMock()
        bot._runner = AsyncMock()
        await bot.stop()
        assert bot._is_running is False
        bot._site.stop.assert_called_once()
        bot._runner.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_web_mode(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        bot._is_running = True
        mock_adapter = AsyncMock()
        bot._web_adapter = mock_adapter
        await bot.stop()
        assert bot._is_running is False
        mock_adapter.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_web_mode_adapter_error_handled(self):
        """Stop should not raise even if adapter disconnect fails."""
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        bot._is_running = True
        mock_adapter = AsyncMock()
        mock_adapter.disconnect.side_effect = Exception("disconnect error")
        bot._web_adapter = mock_adapter
        # Should not raise
        await bot.stop()
        assert bot._is_running is False


# ── Command registration ──────────────────────────────────────────

class TestCommandRegistration:
    """Test that built-in commands work in both modes."""

    def test_cloud_mode_has_builtins(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="t", mode="cloud")
        cmds = bot.list_commands()
        cmd_names = [c.name for c in cmds]
        assert "status" in cmd_names
        assert "new" in cmd_names
        assert "help" in cmd_names

    def test_web_mode_has_builtins(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        cmds = bot.list_commands()
        cmd_names = [c.name for c in cmds]
        assert "status" in cmd_names
        assert "new" in cmd_names
        assert "help" in cmd_names

    def test_custom_command_in_web_mode(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")

        async def my_cmd(msg):
            return "custom!"

        bot.register_command("mycommand", my_cmd, description="Test")
        cmds = bot.list_commands()
        cmd_names = [c.name for c in cmds]
        assert "mycommand" in cmd_names


# ── Web send helper ───────────────────────────────────────────────

class TestWebSend:
    """Test _web_send helper method."""

    @pytest.mark.asyncio
    async def test_web_send_when_adapter_connected(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        mock_adapter = AsyncMock()
        mock_adapter.is_connected = True
        bot._web_adapter = mock_adapter
        await bot._web_send("1234@s.whatsapp.net", "hello")
        mock_adapter.send_message.assert_called_once_with("1234@s.whatsapp.net", "hello")

    @pytest.mark.asyncio
    async def test_web_send_when_adapter_not_connected(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        mock_adapter = AsyncMock()
        mock_adapter.is_connected = False
        bot._web_adapter = mock_adapter
        await bot._web_send("1234@s.whatsapp.net", "hello")
        mock_adapter.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_web_send_when_no_adapter(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(mode="web")
        # Should not raise
        await bot._web_send("1234@s.whatsapp.net", "hello")
