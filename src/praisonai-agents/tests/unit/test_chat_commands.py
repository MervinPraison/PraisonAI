"""
Tests for Chat Command protocols and BotMessage command properties.

TDD: Tests for ChatCommandProtocol, ChatCommandInfo,
and BotMessage.is_command / .command / .command_args properties.
"""

from praisonaiagents.bots import BotMessage, MessageType


class TestBotMessageCommandDetection:
    """Tests for BotMessage command-related properties."""

    def test_is_command_with_slash(self):
        """Test that messages starting with / are detected as commands."""
        msg = BotMessage(content="/status")
        assert msg.is_command is True

    def test_is_command_with_args(self):
        """Test command detection with arguments."""
        msg = BotMessage(content="/help topic")
        assert msg.is_command is True

    def test_is_command_normal_message(self):
        """Test that normal messages are not commands."""
        msg = BotMessage(content="Hello, how are you?")
        assert msg.is_command is False

    def test_is_command_with_command_type(self):
        """Test command detection via message_type."""
        msg = BotMessage(content="status", message_type=MessageType.COMMAND)
        assert msg.is_command is True

    def test_is_command_empty(self):
        """Test command detection with empty content."""
        msg = BotMessage(content="")
        assert msg.is_command is False

    def test_command_name_status(self):
        """Test extracting /status command name."""
        msg = BotMessage(content="/status")
        assert msg.command == "status"

    def test_command_name_new(self):
        """Test extracting /new command name."""
        msg = BotMessage(content="/new")
        assert msg.command == "new"

    def test_command_name_help(self):
        """Test extracting /help command name."""
        msg = BotMessage(content="/help")
        assert msg.command == "help"

    def test_command_name_with_args(self):
        """Test command name extraction ignores arguments."""
        msg = BotMessage(content="/help commands")
        assert msg.command == "help"

    def test_command_name_none_for_normal_message(self):
        """Test command returns None for non-command messages."""
        msg = BotMessage(content="Hello")
        assert msg.command is None

    def test_command_args_empty(self):
        """Test command_args with no arguments."""
        msg = BotMessage(content="/status")
        assert msg.command_args == []

    def test_command_args_single(self):
        """Test command_args with single argument."""
        msg = BotMessage(content="/help commands")
        assert msg.command_args == ["commands"]

    def test_command_args_multiple(self):
        """Test command_args with multiple arguments."""
        msg = BotMessage(content="/set model gpt-4o")
        assert msg.command_args == ["model", "gpt-4o"]

    def test_command_args_normal_message(self):
        """Test command_args returns empty for non-commands."""
        msg = BotMessage(content="Hello world")
        assert msg.command_args == []


class TestBotMessageText:
    """Tests for BotMessage text property."""

    def test_text_string_content(self):
        """Test text property with string content."""
        msg = BotMessage(content="Hello")
        assert msg.text == "Hello"

    def test_text_dict_content(self):
        """Test text property with dict content."""
        msg = BotMessage(content={"text": "Hello", "extra": "data"})
        assert msg.text == "Hello"

    def test_text_dict_no_text_key(self):
        """Test text property with dict lacking text key."""
        msg = BotMessage(content={"type": "image", "url": "http://example.com"})
        assert msg.text == ""


class TestBotMessageSerialization:
    """Tests for BotMessage to_dict / from_dict."""

    def test_to_dict(self):
        """Test BotMessage serialization."""
        msg = BotMessage(content="/status", message_type=MessageType.COMMAND)
        d = msg.to_dict()
        assert d["content"] == "/status"
        assert d["message_type"] == "command"
        assert "message_id" in d
        assert "timestamp" in d

    def test_from_dict(self):
        """Test BotMessage deserialization."""
        d = {
            "message_id": "test-123",
            "content": "/help",
            "message_type": "command",
            "timestamp": 1234567890.0,
        }
        msg = BotMessage.from_dict(d)
        assert msg.message_id == "test-123"
        assert msg.content == "/help"
        assert msg.message_type == MessageType.COMMAND
        assert msg.is_command is True
        assert msg.command == "help"

    def test_from_dict_defaults(self):
        """Test BotMessage deserialization with minimal data."""
        d = {}
        msg = BotMessage.from_dict(d)
        assert msg.content == ""
        assert msg.message_type == MessageType.TEXT


class TestChatCommandProtocol:
    """Tests for ChatCommandProtocol (added by Agent 3)."""

    def test_import(self):
        """Test ChatCommandProtocol can be imported."""
        from praisonaiagents.bots import ChatCommandProtocol
        assert ChatCommandProtocol is not None

    def test_runtime_checkable(self):
        """Test ChatCommandProtocol is runtime_checkable."""
        from praisonaiagents.bots import ChatCommandProtocol, ChatCommandInfo

        class MockBot:
            def register_command(self, name, handler, description="", usage=None):
                pass

            def list_commands(self):
                return [ChatCommandInfo(name="status")]

        bot = MockBot()
        assert isinstance(bot, ChatCommandProtocol)

    def test_not_matching(self):
        """Test that random classes don't match ChatCommandProtocol."""
        from praisonaiagents.bots import ChatCommandProtocol

        class NotABot:
            pass

        assert not isinstance(NotABot(), ChatCommandProtocol)


class TestChatCommandInfoFields:
    """Tests for ChatCommandInfo field completeness."""

    def test_all_standard_commands(self):
        """Test creating all standard bot commands."""
        from praisonaiagents.bots import ChatCommandInfo

        commands = [
            ChatCommandInfo(name="status", description="Show bot status info", usage="/status"),
            ChatCommandInfo(name="new", description="Reset conversation session", usage="/new"),
            ChatCommandInfo(name="help", description="Show available commands", usage="/help"),
        ]

        assert len(commands) == 3
        assert commands[0].name == "status"
        assert commands[1].name == "new"
        assert commands[2].name == "help"

    def test_command_names(self):
        """Test that command names are simple strings."""
        from praisonaiagents.bots import ChatCommandInfo
        cmd = ChatCommandInfo(name="status")
        assert isinstance(cmd.name, str)
        assert "/" not in cmd.name
