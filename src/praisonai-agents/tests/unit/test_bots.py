"""
Unit tests for Bot protocols and components.
"""

from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)


class TestBotConfig:
    """Tests for BotConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = BotConfig()
        assert config.command_prefix == "/"
        assert config.mention_required is True
        assert config.typing_indicator is True
        assert config.max_message_length == 4096
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = BotConfig(
            token="test-token",
            command_prefix="!",
            mention_required=False,
        )
        assert config.token == "test-token"
        assert config.command_prefix == "!"
        assert config.mention_required is False
    
    def test_webhook_mode(self):
        """Test webhook mode detection."""
        config = BotConfig()
        assert config.is_webhook_mode is False
        
        config = BotConfig(webhook_url="https://example.com/webhook")
        assert config.is_webhook_mode is True
    
    def test_user_allowed(self):
        """Test user allowlist."""
        config = BotConfig()
        assert config.is_user_allowed("any-user") is True
        
        config = BotConfig(allowed_users=["user-1", "user-2"])
        assert config.is_user_allowed("user-1") is True
        assert config.is_user_allowed("user-3") is False
    
    def test_channel_allowed(self):
        """Test channel allowlist."""
        config = BotConfig()
        assert config.is_channel_allowed("any-channel") is True
        
        config = BotConfig(allowed_channels=["channel-1"])
        assert config.is_channel_allowed("channel-1") is True
        assert config.is_channel_allowed("channel-2") is False
    
    def test_to_dict_hides_token(self):
        """Test that to_dict hides sensitive data."""
        config = BotConfig(token="secret-token")
        data = config.to_dict()
        assert data["token"] == "***"


class TestBotUser:
    """Tests for BotUser."""
    
    def test_user_creation(self):
        """Test user creation."""
        user = BotUser(
            user_id="123",
            username="testuser",
            display_name="Test User",
        )
        assert user.user_id == "123"
        assert user.username == "testuser"
        assert user.display_name == "Test User"
        assert user.is_bot is False
    
    def test_bot_user(self):
        """Test bot user flag."""
        user = BotUser(user_id="bot-1", is_bot=True)
        assert user.is_bot is True
    
    def test_to_dict(self):
        """Test user serialization."""
        user = BotUser(user_id="123", username="test")
        data = user.to_dict()
        assert data["user_id"] == "123"
        assert data["username"] == "test"
    
    def test_from_dict(self):
        """Test user deserialization."""
        data = {"user_id": "456", "username": "user", "is_bot": True}
        user = BotUser.from_dict(data)
        assert user.user_id == "456"
        assert user.username == "user"
        assert user.is_bot is True


class TestBotChannel:
    """Tests for BotChannel."""
    
    def test_channel_creation(self):
        """Test channel creation."""
        channel = BotChannel(
            channel_id="ch-1",
            name="general",
            channel_type="channel",
        )
        assert channel.channel_id == "ch-1"
        assert channel.name == "general"
        assert channel.channel_type == "channel"
    
    def test_dm_channel(self):
        """Test DM channel type."""
        channel = BotChannel(channel_id="dm-1", channel_type="dm")
        assert channel.channel_type == "dm"
    
    def test_to_dict(self):
        """Test channel serialization."""
        channel = BotChannel(channel_id="123", name="test")
        data = channel.to_dict()
        assert data["channel_id"] == "123"
        assert data["name"] == "test"
    
    def test_from_dict(self):
        """Test channel deserialization."""
        data = {"channel_id": "789", "name": "chat", "channel_type": "group"}
        channel = BotChannel.from_dict(data)
        assert channel.channel_id == "789"
        assert channel.name == "chat"
        assert channel.channel_type == "group"


class TestBotMessage:
    """Tests for BotMessage."""
    
    def test_message_creation(self):
        """Test message creation."""
        msg = BotMessage(
            content="Hello!",
            sender=BotUser(user_id="user-1"),
            channel=BotChannel(channel_id="ch-1"),
        )
        assert msg.content == "Hello!"
        assert msg.message_id is not None
        assert msg.message_type == MessageType.TEXT
    
    def test_text_property(self):
        """Test text property."""
        msg = BotMessage(content="Hello")
        assert msg.text == "Hello"
        
        msg = BotMessage(content={"text": "World"})
        assert msg.text == "World"
    
    def test_command_detection(self):
        """Test command detection."""
        msg = BotMessage(content="/help")
        assert msg.is_command is True
        assert msg.command == "help"
        
        msg = BotMessage(content="Hello")
        assert msg.is_command is False
        assert msg.command is None
    
    def test_command_args(self):
        """Test command arguments extraction."""
        msg = BotMessage(content="/search python tutorial")
        assert msg.command == "search"
        assert msg.command_args == ["python", "tutorial"]
        
        msg = BotMessage(content="/help")
        assert msg.command_args == []
    
    def test_to_dict(self):
        """Test message serialization."""
        msg = BotMessage(
            content="Test",
            sender=BotUser(user_id="user-1"),
            channel=BotChannel(channel_id="ch-1"),
        )
        data = msg.to_dict()
        assert data["content"] == "Test"
        assert data["sender"]["user_id"] == "user-1"
        assert data["channel"]["channel_id"] == "ch-1"
    
    def test_from_dict(self):
        """Test message deserialization."""
        data = {
            "content": "Hello",
            "message_type": "text",
            "sender": {"user_id": "u1"},
            "channel": {"channel_id": "c1"},
        }
        msg = BotMessage.from_dict(data)
        assert msg.content == "Hello"
        assert msg.sender.user_id == "u1"
        assert msg.channel.channel_id == "c1"


class TestMessageType:
    """Tests for MessageType enum."""
    
    def test_message_types(self):
        """Test message type values."""
        assert MessageType.TEXT.value == "text"
        assert MessageType.IMAGE.value == "image"
        assert MessageType.COMMAND.value == "command"
        assert MessageType.REPLY.value == "reply"
        assert MessageType.EDIT.value == "edit"
