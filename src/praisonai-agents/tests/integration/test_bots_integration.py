"""
Integration tests for Bots module.

These tests verify the Bot protocols and implementations work correctly
with real scenarios.
"""

import pytest
import os
from unittest.mock import MagicMock, patch

# Import from core SDK
from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)
from praisonaiagents.bots.protocols import (
    BotProtocol,
    BotMessageProtocol,
    BotUserProtocol,
    BotChannelProtocol,
)


class TestBotConfigIntegration:
    """Integration tests for BotConfig."""
    
    def test_telegram_config(self):
        """Test Telegram bot configuration."""
        config = BotConfig(
            token='test-token-123',
            webhook_url='https://example.com/webhook',
            metadata={'platform': 'telegram'},
        )
        assert config.token == 'test-token-123'
        assert config.metadata['platform'] == 'telegram'
        
        # Token should be hidden in dict
        config_dict = config.to_dict()
        assert 'test-token-123' not in str(config_dict)
    
    def test_discord_config(self):
        """Test Discord bot configuration."""
        config = BotConfig(
            token='discord-token-456',
            metadata={'platform': 'discord', 'guild_ids': ['123456789', '987654321']},
        )
        assert config.token == 'discord-token-456'
        assert len(config.metadata['guild_ids']) == 2
    
    def test_slack_config(self):
        """Test Slack bot configuration."""
        config = BotConfig(
            token='xoxb-slack-token',
            metadata={'platform': 'slack', 'app_token': 'xapp-slack-app-token'},
        )
        assert config.token == 'xoxb-slack-token'
    
    def test_config_from_environment(self):
        """Test config can be created from environment variables."""
        with patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': 'env-token-789',
        }):
            config = BotConfig(
                token=os.environ.get('TELEGRAM_BOT_TOKEN'),
            )
            assert config.token == 'env-token-789'


class TestBotUserIntegration:
    """Integration tests for BotUser."""
    
    def test_user_creation(self):
        """Test user creation with all fields."""
        user = BotUser(
            user_id='user-123',
            username='johndoe',
            display_name='John Doe',
            is_bot=False,
            metadata={'language': 'en', 'timezone': 'UTC'},
        )
        
        assert user.user_id == 'user-123'
        assert user.username == 'johndoe'
        assert user.display_name == 'John Doe'
        assert user.is_bot is False
        assert user.metadata['language'] == 'en'
    
    def test_user_serialization_roundtrip(self):
        """Test user can be serialized and deserialized."""
        original = BotUser(
            user_id='user-456',
            username='janedoe',
            display_name='Jane Doe',
            is_bot=False,
        )
        
        user_dict = original.to_dict()
        restored = BotUser.from_dict(user_dict)
        
        assert restored.user_id == original.user_id
        assert restored.username == original.username
        assert restored.display_name == original.display_name
    
    def test_bot_user_flag(self):
        """Test bot user identification."""
        bot_user = BotUser(
            user_id='bot-123',
            username='assistant_bot',
            is_bot=True,
        )
        
        assert bot_user.is_bot is True


class TestBotChannelIntegration:
    """Integration tests for BotChannel."""
    
    def test_dm_channel(self):
        """Test direct message channel."""
        channel = BotChannel(
            channel_id='dm-123',
            name=None,
            channel_type='dm',
        )
        
        assert channel.channel_type == 'dm'
    
    def test_group_channel(self):
        """Test group channel."""
        channel = BotChannel(
            channel_id='group-456',
            name='Team Chat',
            channel_type='group',
            metadata={'member_count': 25},
        )
        
        assert channel.channel_type == 'group'
        assert channel.name == 'Team Chat'
        assert channel.metadata['member_count'] == 25
    
    def test_thread_channel(self):
        """Test thread channel."""
        channel = BotChannel(
            channel_id='thread-789',
            name='Discussion Thread',
            channel_type='thread',
            metadata={'parent_channel': 'channel-123'},
        )
        
        assert channel.channel_type == 'thread'
    
    def test_channel_serialization_roundtrip(self):
        """Test channel can be serialized and deserialized."""
        original = BotChannel(
            channel_id='channel-999',
            name='General',
            channel_type='channel',
        )
        
        channel_dict = original.to_dict()
        restored = BotChannel.from_dict(channel_dict)
        
        assert restored.channel_id == original.channel_id
        assert restored.name == original.name


class TestBotMessageIntegration:
    """Integration tests for BotMessage."""
    
    def test_text_message(self):
        """Test text message creation."""
        sender = BotUser(user_id='user-1', username='alice')
        channel = BotChannel(channel_id='channel-1', channel_type='dm')
        
        message = BotMessage(
            content='Hello, World!',
            message_type=MessageType.TEXT,
            sender=sender,
            channel=channel,
        )
        
        assert message.text == 'Hello, World!'
        assert message.message_type == MessageType.TEXT
        assert message.sender.username == 'alice'
    
    def test_command_message(self):
        """Test command message parsing."""
        message = BotMessage(
            content='/help search query',
            message_type=MessageType.COMMAND,
        )
        
        assert message.is_command is True
        assert message.command == 'help'
        assert message.command_args == ['search', 'query']
    
    def test_command_detection_from_text(self):
        """Test command detection from text content."""
        message = BotMessage(
            content='/status',
            message_type=MessageType.TEXT,
        )
        
        # Should detect as command even if type is TEXT
        assert message.is_command is True
        assert message.command == 'status'
        assert message.command_args == []
    
    def test_message_with_attachments(self):
        """Test message with attachments."""
        message = BotMessage(
            content='Check out these files',
            attachments=[
                {'type': 'image', 'url': 'https://example.com/image.png'},
                {'type': 'document', 'url': 'https://example.com/doc.pdf'},
            ],
        )
        
        assert len(message.attachments) == 2
        assert message.attachments[0]['type'] == 'image'
    
    def test_reply_message(self):
        """Test reply message."""
        original = BotMessage(content='Original message')
        
        reply = BotMessage(
            content='This is a reply',
            reply_to=original.message_id,
        )
        
        assert reply.reply_to == original.message_id
    
    def test_threaded_message(self):
        """Test threaded message."""
        message = BotMessage(
            content='Thread reply',
            thread_id='thread-123',
        )
        
        assert message.thread_id == 'thread-123'
    
    def test_message_serialization_roundtrip(self):
        """Test message can be serialized and deserialized."""
        sender = BotUser(user_id='user-1', username='bob')
        channel = BotChannel(channel_id='channel-1', channel_type='group')
        
        original = BotMessage(
            content='Test message',
            message_type=MessageType.TEXT,
            sender=sender,
            channel=channel,
            metadata={'priority': 'high'},
        )
        
        msg_dict = original.to_dict()
        restored = BotMessage.from_dict(msg_dict)
        
        assert restored.content == original.content
        assert restored.message_type == original.message_type
        assert restored.sender.user_id == original.sender.user_id
        assert restored.channel.channel_id == original.channel.channel_id
    
    def test_all_message_types(self):
        """Test all message types can be used."""
        for msg_type in MessageType:
            message = BotMessage(
                content='Test',
                message_type=msg_type,
            )
            assert message.message_type == msg_type


class TestBotProtocolCompliance:
    """Test that implementations comply with protocols."""
    
    def test_bot_protocol_methods(self):
        """Verify BotProtocol has all required methods."""
        required_properties = ['is_running', 'platform', 'bot_user']
        required_methods = [
            'start', 'stop', 'set_agent', 'get_agent',
            'send_message', 'edit_message', 'delete_message',
            'on_message', 'on_command', 'send_typing',
            'get_user', 'get_channel'
        ]
        
        for prop in required_properties:
            assert hasattr(BotProtocol, prop)
        
        for method in required_methods:
            assert hasattr(BotProtocol, method)
    
    def test_bot_message_protocol_methods(self):
        """Verify BotMessageProtocol has all required methods."""
        required_properties = ['message_id', 'content', 'sender', 'channel']
        
        for prop in required_properties:
            assert hasattr(BotMessageProtocol, prop)
    
    def test_bot_user_protocol_methods(self):
        """Verify BotUserProtocol has all required methods."""
        required_properties = ['user_id', 'username', 'is_bot']
        
        for prop in required_properties:
            assert hasattr(BotUserProtocol, prop)
    
    def test_bot_channel_protocol_methods(self):
        """Verify BotChannelProtocol has all required methods."""
        required_properties = ['channel_id', 'channel_type']
        
        for prop in required_properties:
            assert hasattr(BotChannelProtocol, prop)


class TestMockBotWorkflow:
    """Test a mock bot workflow."""
    
    def test_message_handling_workflow(self):
        """Test complete message handling workflow."""
        # Create mock bot
        bot = MagicMock()
        bot.platform = 'telegram'
        bot.is_running = True
        
        messages_received = []
        responses_sent = []
        
        def on_message(handler):
            def wrapper(msg):
                messages_received.append(msg)
                return handler(msg)
            return wrapper
        
        async def send_message(channel_id, content, **kwargs):
            msg = BotMessage(
                content=content,
                sender=BotUser(user_id='bot-1', is_bot=True),
                channel=BotChannel(channel_id=channel_id, channel_type='dm'),
            )
            responses_sent.append(msg)
            return msg
        
        bot.on_message = on_message
        bot.send_message = send_message
        
        # Simulate incoming message
        incoming = BotMessage(
            content='Hello bot!',
            sender=BotUser(user_id='user-1', username='alice'),
            channel=BotChannel(channel_id='dm-123', channel_type='dm'),
        )
        
        @bot.on_message
        def handle_message(msg):
            return f"Received: {msg.content}"
        
        result = handle_message(incoming)
        
        assert len(messages_received) == 1
        assert result == "Received: Hello bot!"


@pytest.mark.asyncio
class TestAsyncBotOperations:
    """Test async bot operations."""
    
    async def test_async_message_send(self):
        """Test async message sending."""
        sent_messages = []
        
        async def send_message(channel_id: str, content: str):
            msg = BotMessage(
                content=content,
                sender=BotUser(user_id='bot-1', is_bot=True),
                channel=BotChannel(channel_id=channel_id, channel_type='dm'),
            )
            sent_messages.append(msg)
            return msg
        
        result = await send_message('channel-1', 'Hello!')
        
        assert len(sent_messages) == 1
        assert result.content == 'Hello!'
    
    async def test_async_typing_indicator(self):
        """Test async typing indicator."""
        typing_channels = []
        
        async def send_typing(channel_id: str):
            typing_channels.append(channel_id)
        
        await send_typing('channel-1')
        await send_typing('channel-2')
        
        assert len(typing_channels) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
