"""Tests for praisonai.cli.features.approval — resolve_approval_backend."""

import os
import sys
import pytest

# Ensure praisonai wrapper package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "praisonai"))


class TestResolveApprovalBackend:
    """Test resolve_approval_backend() maps CLI strings to backend objects."""

    def _resolve(self, value):
        from praisonai.cli.features.approval import resolve_approval_backend
        return resolve_approval_backend(value)

    def test_none_returns_none(self):
        assert self._resolve(None) is None

    def test_none_string_returns_none(self):
        assert self._resolve("none") is None
        assert self._resolve("None") is None

    def test_console_returns_console_backend(self):
        b = self._resolve("console")
        assert type(b).__name__ == "ConsoleBackend"

    def test_true_returns_console_backend(self):
        b = self._resolve("true")
        assert type(b).__name__ == "ConsoleBackend"

    def test_auto_returns_auto_approve_backend(self):
        b = self._resolve("auto")
        assert type(b).__name__ == "AutoApproveBackend"

    def test_slack_returns_slack_approval(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_CHANNEL", "C123")
        b = self._resolve("slack")
        assert type(b).__name__ == "SlackApproval"

    def test_telegram_returns_telegram_approval(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
        b = self._resolve("telegram")
        assert type(b).__name__ == "TelegramApproval"

    def test_telegram_requires_chat_id(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            self._resolve("telegram")

    def test_discord_returns_discord_approval(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "789")
        b = self._resolve("discord")
        assert type(b).__name__ == "DiscordApproval"

    def test_discord_requires_channel_id(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        with pytest.raises(ValueError, match="DISCORD_CHANNEL_ID"):
            self._resolve("discord")

    def test_webhook_returns_webhook_approval(self, monkeypatch):
        monkeypatch.setenv("APPROVAL_WEBHOOK_URL", "http://localhost:8080")
        b = self._resolve("webhook")
        assert type(b).__name__ == "WebhookApproval"

    def test_http_returns_http_approval(self):
        b = self._resolve("http")
        assert type(b).__name__ == "HTTPApproval"

    def test_agent_returns_agent_approval(self):
        b = self._resolve("agent")
        assert type(b).__name__ == "AgentApproval"

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown approval backend"):
            self._resolve("foobar")

    def test_case_insensitive(self):
        b = self._resolve("Console")
        assert type(b).__name__ == "ConsoleBackend"
        b = self._resolve("AUTO")
        assert type(b).__name__ == "AutoApproveBackend"


class TestValidBackends:
    """Test VALID_BACKENDS constant."""

    def test_valid_backends_list(self):
        from praisonai.cli.features.approval import VALID_BACKENDS
        assert "console" in VALID_BACKENDS
        assert "slack" in VALID_BACKENDS
        assert "telegram" in VALID_BACKENDS
        assert "discord" in VALID_BACKENDS
        assert "webhook" in VALID_BACKENDS
        assert "http" in VALID_BACKENDS
        assert "agent" in VALID_BACKENDS
        assert "auto" in VALID_BACKENDS
        assert "none" in VALID_BACKENDS


class TestAgentApprovalIntegration:
    """Test Agent(approval=...) parameter with CLI-resolved backends."""

    def test_agent_with_console_backend(self):
        from praisonaiagents import Agent
        from praisonaiagents.approval.backends import ConsoleBackend
        agent = Agent(name="test", instructions="hi", approval=ConsoleBackend())
        assert agent._approval_backend is not None
        assert type(agent._approval_backend).__name__ == "ConsoleBackend"

    def test_agent_with_auto_backend(self):
        from praisonaiagents import Agent
        from praisonaiagents.approval.backends import AutoApproveBackend
        agent = Agent(name="test", instructions="hi", approval=AutoApproveBackend())
        assert agent._approval_backend is not None

    def test_agent_with_slack_backend(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_CHANNEL", "C123")
        from praisonaiagents import Agent
        from praisonai.bots import SlackApproval
        agent = Agent(name="test", instructions="hi", approval=SlackApproval())
        assert type(agent._approval_backend).__name__ == "SlackApproval"
