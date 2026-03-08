"""
TDD Tests for Bot Integration Gaps (B7, B9, B10).

Tests the fixes for low-priority bot integration gaps.
"""

from unittest.mock import Mock


class TestGapB7ChannelBotAccessors:
    """Test Gap B7: Public channel bot accessors in WebSocketGateway."""

    def test_list_channel_bots_empty(self):
        """list_channel_bots should return empty list when no bots registered."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        assert gw.list_channel_bots() == []

    def test_list_channel_bots_with_bots(self):
        """list_channel_bots should return all registered bot names."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        # Manually add bots to internal dict for testing
        gw._channel_bots["discord"] = Mock()
        gw._channel_bots["telegram"] = Mock()
        
        bots = gw.list_channel_bots()
        
        assert len(bots) == 2
        assert "discord" in bots
        assert "telegram" in bots

    def test_get_channel_bot_exists(self):
        """get_channel_bot should return bot instance when found."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        mock_bot = Mock()
        gw._channel_bots["discord"] = mock_bot
        
        result = gw.get_channel_bot("discord")
        
        assert result is mock_bot

    def test_get_channel_bot_not_found(self):
        """get_channel_bot should return None when not found."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        result = gw.get_channel_bot("nonexistent")
        
        assert result is None

    def test_has_channel_bot_true(self):
        """has_channel_bot should return True when bot exists."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        gw._channel_bots["telegram"] = Mock()
        
        assert gw.has_channel_bot("telegram") is True

    def test_has_channel_bot_false(self):
        """has_channel_bot should return False when bot doesn't exist."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        assert gw.has_channel_bot("nonexistent") is False


class TestGapB9BotKwargs:
    """Test Gap B9: Bot constructors accept **kwargs for forward compatibility."""

    def test_discord_bot_accepts_kwargs(self):
        """DiscordBot should accept **kwargs without error."""
        from praisonai.bots import DiscordBot
        
        # Should not raise
        bot = DiscordBot(
            token="test-token",
            future_param="some_value",
            another_param=123,
        )
        
        assert bot._extra_kwargs == {"future_param": "some_value", "another_param": 123}

    def test_telegram_bot_accepts_kwargs(self):
        """TelegramBot should accept **kwargs without error."""
        from praisonai.bots import TelegramBot
        
        bot = TelegramBot(
            token="test-token",
            future_param="some_value",
        )
        
        assert bot._extra_kwargs == {"future_param": "some_value"}

    def test_slack_bot_accepts_kwargs(self):
        """SlackBot should accept **kwargs without error."""
        from praisonai.bots import SlackBot
        
        bot = SlackBot(
            token="test-token",
            future_param="some_value",
        )
        
        assert bot._extra_kwargs == {"future_param": "some_value"}

    def test_whatsapp_bot_accepts_kwargs(self):
        """WhatsAppBot should accept **kwargs without error."""
        from praisonai.bots import WhatsAppBot
        
        bot = WhatsAppBot(
            token="test-token",
            future_param="some_value",
        )
        
        assert bot._extra_kwargs == {"future_param": "some_value"}


class TestGapB10DuplicateAgentHandling:
    """Test Gap B10: Duplicate agent registration handling."""

    def test_register_agent_overwrite_default(self):
        """register_agent should overwrite by default (backward compat)."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        agent1 = Mock()
        agent2 = Mock()
        
        gw.register_agent(agent1, "agent-001")
        gw.register_agent(agent2, "agent-001")  # Should overwrite
        
        assert gw.get_agent("agent-001") is agent2

    def test_register_agent_overwrite_explicit(self):
        """register_agent with overwrite=True should replace existing."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        agent1 = Mock()
        agent2 = Mock()
        
        gw.register_agent(agent1, "agent-001")
        gw.register_agent(agent2, "agent-001", overwrite=True)
        
        assert gw.get_agent("agent-001") is agent2

    def test_register_agent_no_overwrite_raises(self):
        """register_agent with overwrite=False should raise on duplicate."""
        from praisonai.gateway import WebSocketGateway
        import pytest
        
        gw = WebSocketGateway()
        agent1 = Mock()
        agent2 = Mock()
        
        gw.register_agent(agent1, "agent-001")
        
        with pytest.raises(ValueError, match="already registered"):
            gw.register_agent(agent2, "agent-001", overwrite=False)

    def test_register_agent_no_overwrite_new_agent_ok(self):
        """register_agent with overwrite=False should work for new agents."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        agent1 = Mock()
        
        # Should not raise for new agent
        aid = gw.register_agent(agent1, "agent-001", overwrite=False)
        
        assert aid == "agent-001"
        assert gw.get_agent("agent-001") is agent1
