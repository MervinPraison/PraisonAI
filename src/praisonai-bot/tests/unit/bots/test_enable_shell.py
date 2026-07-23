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
                config=BotConfig(owner_user_id="UOWNER"),
                ch_cfg={
                    "allow_shell": True,
                    "auto_approve_shell": False,
                    "approval_channel": "UOWNER",
                    "approval_users": "UOWNER",
                },
                channel_type="slack",
            )

    slack_cls.assert_called_once()
    assert agent._approval_backend is slack_cls.return_value
