"""Tests for allow_shell channel opt-in."""

from unittest.mock import MagicMock, patch

import pytest

from praisonai_bot.bots._defaults import enable_shell_tools
from praisonaiagents.bots.config import BotConfig


def test_enable_shell_noop_when_disabled():
    agent = MagicMock()
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    enable_shell_tools(agent, ch_cfg={"allow_shell": False})

    assert agent.tools == []
    assert "execute_command" in agent._perm_deny


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_adds_tool_and_clears_deny(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.name = "assistant"
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command", "delete_file"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        enable_shell_tools(
            agent,
            config=BotConfig(),
            ch_cfg={"allow_shell": True, "auto_approve_shell": True},
            channel_type="slack",
        )

    assert mock_execute_command in agent.tools
    assert "execute_command" not in agent._perm_deny
    assert "delete_file" in agent._perm_deny
    assert agent._approval_backend is not None


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_slack_approval_when_not_auto(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.name = "assistant"
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        with patch("praisonai_bot.bots.SlackApproval") as slack_cls:
            slack_cls.return_value = object()
            enable_shell_tools(
                agent,
                config=BotConfig(owner_user_id="UOWNER", token="xoxb-test"),
                ch_cfg={
                    "allow_shell": True,
                    "auto_approve_shell": False,
                    "approval_channel": "UOWNER",
                    "approval_users": "UOWNER",
                },
                channel_type="slack",
            )

    slack_cls.assert_called_once_with(
        token="xoxb-test",
        channel="UOWNER",
        allowed_approvers=["UOWNER"],
    )
    assert agent._approval_backend is slack_cls.return_value


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_telegram_approval(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        with patch("praisonai_bot.bots.TelegramApproval") as tg_cls:
            tg_cls.return_value = object()
            enable_shell_tools(
                agent,
                config=BotConfig(token="tg-token"),
                ch_cfg={
                    "allow_shell": True,
                    "auto_approve_shell": False,
                    "approval_channel": "123456789",
                    "token": "tg-token",
                },
                channel_type="telegram",
            )

    tg_cls.assert_called_once_with(
        token="tg-token",
        chat_id="123456789",
        allowed_approvers=None,
    )


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_discord_approval(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        with patch("praisonai_bot.bots.DiscordApproval") as dc_cls:
            dc_cls.return_value = object()
            enable_shell_tools(
                agent,
                config=BotConfig(token="dc-token"),
                ch_cfg={
                    "allow_shell": True,
                    "auto_approve_shell": False,
                    "home_channel": "9876543210",
                    "token": "dc-token",
                },
                channel_type="discord",
            )

    dc_cls.assert_called_once_with(
        token="dc-token",
        channel_id="9876543210",
        allowed_approvers=None,
    )


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_gateway_approval_mode(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        with patch("praisonai_bot.gateway.gateway_approval.GatewayApprovalBackend") as gw_cls:
            gw_cls.return_value = object()
            enable_shell_tools(
                agent,
                config=BotConfig(),
                ch_cfg={
                    "allow_shell": True,
                    "auto_approve_shell": False,
                    "approval_mode": "gateway",
                },
                channel_type="whatsapp",
            )

    gw_cls.assert_called_once()
    assert agent._approval_backend is gw_cls.return_value


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_http_approval_mode(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        with patch("praisonai_bot.bots.HTTPApproval") as http_cls:
            http_cls.return_value = object()
            enable_shell_tools(
                agent,
                config=BotConfig(),
                ch_cfg={
                    "allow_shell": True,
                    "auto_approve_shell": False,
                    "approval_mode": "http",
                    "approval_http_host": "0.0.0.0",
                    "approval_http_port": 9000,
                },
                channel_type="email",
            )

    http_cls.assert_called_once_with(host="0.0.0.0", port=9000)


@patch("praisonaiagents.tools.execute_command", create=True)
def test_enable_shell_whatsapp_falls_back_to_gateway(mock_execute_command):
    mock_execute_command.name = "execute_command"
    agent = MagicMock()
    agent.tools = []
    agent._perm_deny = frozenset({"execute_command"})

    with patch("praisonaiagents.tools.execute_command", mock_execute_command):
        with patch("praisonai_bot.gateway.gateway_approval.GatewayApprovalBackend") as gw_cls:
            gw_cls.return_value = object()
            enable_shell_tools(
                agent,
                config=BotConfig(),
                ch_cfg={"allow_shell": True, "auto_approve_shell": False},
                channel_type="whatsapp",
            )

    gw_cls.assert_called_once()
    assert agent._approval_backend is gw_cls.return_value
