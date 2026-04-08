"""Integration tests for ChatCommandProtocol implementation across all bots."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai'))

from praisonaiagents.bots import ChatCommandInfo, ChatCommandProtocol


class MockAgent:
    def __init__(self, name="test-agent", llm="gpt-4o-mini"):
        self.name = name
        self.llm = llm
        self.chat_history = []

    def chat(self, prompt):
        return f"Reply: {prompt}"


class TestChatCommandProtocolTelegram:
    """Test TelegramBot satisfies ChatCommandProtocol."""

    def _make_bot(self):
        from praisonai.bots.telegram import TelegramBot
        return TelegramBot(token="fake-token", agent=MockAgent())

    def test_has_register_command(self):
        bot = self._make_bot()
        assert hasattr(bot, 'register_command')

    def test_has_list_commands(self):
        bot = self._make_bot()
        assert hasattr(bot, 'list_commands')

    def test_isinstance_protocol(self):
        bot = self._make_bot()
        assert isinstance(bot, ChatCommandProtocol)

    def test_list_commands_builtins(self):
        bot = self._make_bot()
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "status" in names
        assert "new" in names
        assert "help" in names

    def test_register_custom_command(self):
        bot = self._make_bot()
        bot.register_command("stats", lambda m: None, description="Show stats")
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "stats" in names

    def test_command_info_type(self):
        bot = self._make_bot()
        commands = bot.list_commands()
        for cmd in commands:
            assert isinstance(cmd, ChatCommandInfo)


class TestChatCommandProtocolDiscord:
    """Test DiscordBot satisfies ChatCommandProtocol."""

    def _make_bot(self):
        from praisonai.bots.discord import DiscordBot
        return DiscordBot(token="fake-token", agent=MockAgent())

    def test_isinstance_protocol(self):
        bot = self._make_bot()
        assert isinstance(bot, ChatCommandProtocol)

    def test_list_commands_builtins(self):
        bot = self._make_bot()
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "status" in names
        assert "new" in names
        assert "help" in names

    def test_register_and_list(self):
        bot = self._make_bot()
        bot.register_command("ping", lambda m: None, description="Ping")
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "ping" in names


class TestChatCommandProtocolSlack:
    """Test SlackBot satisfies ChatCommandProtocol."""

    def _make_bot(self):
        from praisonai.bots.slack import SlackBot
        return SlackBot(token="fake-token", agent=MockAgent())

    def test_isinstance_protocol(self):
        bot = self._make_bot()
        assert isinstance(bot, ChatCommandProtocol)

    def test_list_commands_builtins(self):
        bot = self._make_bot()
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "status" in names
        assert "new" in names
        assert "help" in names

    def test_register_and_list(self):
        bot = self._make_bot()
        bot.register_command("deploy", lambda m: None, description="Deploy")
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "deploy" in names


class TestChatCommandProtocolWhatsApp:
    """Test WhatsAppBot satisfies ChatCommandProtocol."""

    def _make_bot(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        return WhatsAppBot(token="fake-token", phone_number_id="123", agent=MockAgent(), verify_token="v")

    def test_isinstance_protocol(self):
        bot = self._make_bot()
        assert isinstance(bot, ChatCommandProtocol)

    def test_list_commands_builtins(self):
        bot = self._make_bot()
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "status" in names
        assert "new" in names
        assert "help" in names

    def test_register_and_list(self):
        bot = self._make_bot()
        bot.register_command("wa_test", lambda m: None, description="WA Test")
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "wa_test" in names

    def test_platform_property(self):
        bot = self._make_bot()
        assert bot.platform == "whatsapp"

    def test_set_and_get_agent(self):
        bot = self._make_bot()
        new_agent = MockAgent(name="new")
        bot.set_agent(new_agent)
        assert bot.get_agent().name == "new"


class TestCrossplatformConsistency:
    """Verify all 4 bots return consistent command lists."""

    def test_same_builtin_commands(self):
        from praisonai.bots.telegram import TelegramBot
        from praisonai.bots.discord import DiscordBot
        from praisonai.bots.slack import SlackBot
        from praisonai.bots.whatsapp import WhatsAppBot

        agent = MockAgent()
        tg = TelegramBot(token="fake", agent=agent)
        dc = DiscordBot(token="fake", agent=agent)
        sl = SlackBot(token="fake", agent=agent)
        wa = WhatsAppBot(token="fake", phone_number_id="123", agent=agent, verify_token="v")

        tg_names = sorted([c.name for c in tg.list_commands()])
        dc_names = sorted([c.name for c in dc.list_commands()])
        sl_names = sorted([c.name for c in sl.list_commands()])
        wa_names = sorted([c.name for c in wa.list_commands()])

        assert tg_names == dc_names == sl_names == wa_names

    def test_session_manager_exists(self):
        from praisonai.bots.telegram import TelegramBot
        from praisonai.bots.discord import DiscordBot
        from praisonai.bots.slack import SlackBot
        from praisonai.bots.whatsapp import WhatsAppBot

        agent = MockAgent()
        for BotClass in [TelegramBot, DiscordBot, SlackBot]:
            bot = BotClass(token="fake", agent=agent)
            assert hasattr(bot, '_session'), f"{BotClass.__name__} missing _session"
        wa = WhatsAppBot(token="fake", phone_number_id="123", agent=agent, verify_token="v")
        assert hasattr(wa, '_session_mgr'), "WhatsAppBot missing _session_mgr"
