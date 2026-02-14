"""
Integration tests verifying that debounce, chunking, ack, and session reaper
are properly wired into the bot adapters (not just tested in isolation).
"""

import time

import pytest


class TestDebounceWiring:
    """Verify InboundDebouncer is instantiated in all 3 adapters."""

    def _make_config(self, debounce_ms=1500):
        from praisonaiagents.bots import BotConfig
        return BotConfig(token="test-token", debounce_ms=debounce_ms)

    def test_telegram_has_debouncer(self):
        from praisonai.bots.telegram import TelegramBot
        bot = TelegramBot(token="test", config=self._make_config())
        assert hasattr(bot, '_debouncer')
        assert bot._debouncer._debounce_s > 0

    def test_discord_has_debouncer(self):
        from praisonai.bots.discord import DiscordBot
        bot = DiscordBot(token="test", config=self._make_config())
        assert hasattr(bot, '_debouncer')
        assert bot._debouncer._debounce_s > 0

    def test_slack_has_debouncer(self):
        from praisonai.bots.slack import SlackBot
        bot = SlackBot(token="test", config=self._make_config())
        assert hasattr(bot, '_debouncer')
        assert bot._debouncer._debounce_s > 0

    def test_debounce_zero_disables(self):
        from praisonai.bots.telegram import TelegramBot
        bot = TelegramBot(token="test", config=self._make_config(debounce_ms=0))
        assert bot._debouncer._debounce_s == 0

    def test_default_config_no_debounce(self):
        from praisonai.bots.telegram import TelegramBot
        from praisonaiagents.bots import BotConfig
        bot = TelegramBot(token="test", config=BotConfig(token="test"))
        assert bot._debouncer._debounce_s == 0


class TestChunkingWiring:
    """Verify smart chunking is used in all 3 adapters."""

    def test_telegram_uses_chunk_message(self):
        """Telegram._send_long_message imports chunk_message."""
        import inspect
        from praisonai.bots.telegram import TelegramBot
        source = inspect.getsource(TelegramBot._send_long_message)
        assert "chunk_message" in source

    def test_discord_uses_chunk_message(self):
        """Discord._send_long_message imports chunk_message."""
        import inspect
        from praisonai.bots.discord import DiscordBot
        source = inspect.getsource(DiscordBot._send_long_message)
        assert "chunk_message" in source

    def test_slack_uses_chunk_message(self):
        """Slack._send_long_message imports chunk_message."""
        import inspect
        from praisonai.bots.slack import SlackBot
        source = inspect.getsource(SlackBot._send_long_message)
        assert "chunk_message" in source

    def test_no_naive_splitting_discord(self):
        """Discord should NOT have naive text[i:i+max_len] splitting."""
        import inspect
        from praisonai.bots.discord import DiscordBot
        source = inspect.getsource(DiscordBot._send_long_message)
        assert "text[i:i+" not in source

    def test_no_naive_splitting_slack(self):
        """Slack should NOT have naive text[i:i+max_len] splitting."""
        import inspect
        from praisonai.bots.slack import SlackBot
        source = inspect.getsource(SlackBot._send_long_message)
        assert "text[i:i+" not in source


class TestAckWiring:
    """Verify AckReactor is instantiated and configurable."""

    def test_telegram_has_ack_reactor(self):
        from praisonai.bots.telegram import TelegramBot
        from praisonaiagents.bots import BotConfig
        config = BotConfig(token="test", ack_emoji="⏳")
        bot = TelegramBot(token="test", config=config)
        assert hasattr(bot, '_ack')
        assert bot._ack.enabled is True

    def test_ack_disabled_by_default(self):
        from praisonai.bots.telegram import TelegramBot
        from praisonaiagents.bots import BotConfig
        bot = TelegramBot(token="test", config=BotConfig(token="test"))
        assert bot._ack.enabled is False

    def test_botconfig_ack_fields(self):
        from praisonaiagents.bots import BotConfig
        cfg = BotConfig(ack_emoji="⏳", done_emoji="✅")
        assert cfg.ack_emoji == "⏳"
        assert cfg.done_emoji == "✅"
        d = cfg.to_dict()
        assert d["ack_emoji"] == "⏳"
        assert d["done_emoji"] == "✅"

    @pytest.mark.asyncio
    async def test_ack_reactor_lifecycle(self):
        """AckReactor.ack() + done() complete without error."""
        from praisonai.bots._ack import AckReactor

        reactor = AckReactor(ack_emoji="⏳", done_emoji="✅")
        reacted = []

        async def mock_react(emoji, **kw):
            reacted.append(("react", emoji))

        async def mock_unreact(emoji, **kw):
            reacted.append(("unreact", emoji))

        ctx = await reactor.ack(react_fn=mock_react)
        assert ctx.acked is True
        await reactor.done(ctx, react_fn=mock_react, unreact_fn=mock_unreact)
        assert ("react", "⏳") in reacted
        assert ("unreact", "⏳") in reacted
        assert ("react", "✅") in reacted


class TestSessionReaperWiring:
    """Verify session reaper works end-to-end."""

    def test_reap_stale_removes_old_sessions(self):
        from praisonai.bots._session import BotSessionManager
        mgr = BotSessionManager()
        # Manually seed old sessions
        mgr._histories["user1"] = [{"role": "user", "content": "old"}]
        mgr._last_active["user1"] = time.monotonic() - 100

        mgr._histories["user2"] = [{"role": "user", "content": "recent"}]
        mgr._last_active["user2"] = time.monotonic()

        reaped = mgr.reap_stale(max_age_seconds=50)
        assert reaped == 1
        assert "user1" not in mgr._histories
        assert "user2" in mgr._histories

    def test_reap_stale_zero_ttl_disabled(self):
        from praisonai.bots._session import BotSessionManager
        mgr = BotSessionManager()
        mgr._histories["user1"] = [{"role": "user", "content": "old"}]
        mgr._last_active["user1"] = time.monotonic() - 9999

        reaped = mgr.reap_stale(max_age_seconds=0)
        assert reaped == 0
        assert "user1" in mgr._histories

    def test_botconfig_session_ttl(self):
        from praisonaiagents.bots import BotConfig
        cfg = BotConfig(session_ttl=86400)
        assert cfg.session_ttl == 86400
        d = cfg.to_dict()
        assert d["session_ttl"] == 86400

    def test_reset_clears_last_active(self):
        from praisonai.bots._session import BotSessionManager
        mgr = BotSessionManager()
        mgr._histories["user1"] = [{"role": "user", "content": "hi"}]
        mgr._last_active["user1"] = time.monotonic()

        mgr.reset("user1")
        assert "user1" not in mgr._histories
        assert "user1" not in mgr._last_active


class TestSessionIdLeak:
    """Verify the session_id leak fix (F1)."""

    def _make_mock_agent(self):
        class Agent:
            def __init__(self):
                self.name = "test"
                self.tools = []
                self.memory = None
                self.chat_history = []
                self.llm = "gpt-4o-mini"
                self._approval_backend = None
            def chat(self, prompt):
                return f"echo: {prompt}"
        return Agent()

    def test_no_shared_session_id(self):
        """Memory injected by Bot should NOT contain session_id."""
        from praisonai.bots.bot import Bot
        agent = self._make_mock_agent()
        bot = Bot("telegram", agent=agent)
        enhanced = bot._apply_smart_defaults(agent)
        mem = getattr(enhanced, "memory", None)
        assert isinstance(mem, dict)
        assert "session_id" not in mem
        assert mem["history"] is True
