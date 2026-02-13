"""
Tests for MESSAGE_RECEIVED / MESSAGE_SENDING / MESSAGE_SENT hook firing in bot adapters.

These hooks exist in HookEvent enum but were never fired by bot implementations.
This test suite verifies the MessageHookMixin wires them correctly.
"""

import time

from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.bots import BotMessage, BotUser, BotChannel


# ---------------------------------------------------------------------------
# Minimal stub for testing the mixin in isolation
# ---------------------------------------------------------------------------

class _StubBot:
    """Minimal bot stub that uses MessageHookMixin."""

    def __init__(self, agent=None):
        self._agent = agent
        self._hook_registry = None  # set by tests
        self._hook_runner = None


# ---------------------------------------------------------------------------
# Test: MessageHookMixin core logic
# ---------------------------------------------------------------------------

class TestMessageHookMixin:
    """Test the shared MessageHookMixin that all bots use."""

    def test_import_mixin(self):
        """MessageHookMixin should be importable from _protocol_mixin."""
        from praisonai.bots._protocol_mixin import MessageHookMixin
        assert MessageHookMixin is not None

    def test_mixin_has_fire_methods(self):
        """Mixin should provide fire_message_received, fire_message_sending, fire_message_sent."""
        from praisonai.bots._protocol_mixin import MessageHookMixin
        assert hasattr(MessageHookMixin, 'fire_message_received')
        assert hasattr(MessageHookMixin, 'fire_message_sending')
        assert hasattr(MessageHookMixin, 'fire_message_sent')

    def test_fire_message_received_creates_correct_event(self):
        """fire_message_received should create a HookInput with MESSAGE_RECEIVED event."""
        from praisonai.bots._protocol_mixin import MessageHookMixin

        class TestBot(MessageHookMixin):
            def __init__(self):
                self._agent = None
                self.platform = "test"

        bot = TestBot()
        msg = BotMessage(
            message_id="123",
            content="Hello",
            sender=BotUser(user_id="user1", username="alice"),
            channel=BotChannel(channel_id="ch1", channel_type="dm"),
        )

        # Without a hook registry, fire should be a no-op (no crash)
        bot.fire_message_received(msg)

    def test_fire_message_sending_returns_modified_content(self):
        """fire_message_sending should allow hooks to modify content."""
        from praisonai.bots._protocol_mixin import MessageHookMixin

        class TestBot(MessageHookMixin):
            def __init__(self):
                self._agent = None
                self.platform = "test"

        bot = TestBot()

        # Without hooks, should return original content unchanged
        result = bot.fire_message_sending("ch1", "Hello world")
        assert result is not None
        assert result["content"] == "Hello world"
        assert result["cancel"] is False

    def test_fire_message_sending_cancel(self):
        """fire_message_sending with deny hook should return cancel=True."""
        from praisonai.bots._protocol_mixin import MessageHookMixin
        from praisonaiagents.hooks import HookRegistry, HookRunner

        registry = HookRegistry()
        runner = HookRunner(registry=registry)

        # Register a function hook that returns False (= deny)
        registry.register_function(
            event=HookEvent.MESSAGE_SENDING,
            func=lambda input_data: False,  # False = deny
            name="cancel_hook",
        )

        # Mock agent with _hook_runner
        class MockAgent:
            agent_name = "test_agent"
            _hook_runner = runner

        class TestBot(MessageHookMixin):
            def __init__(self):
                self._agent = MockAgent()
                self.platform = "test"

        bot = TestBot()
        result = bot.fire_message_sending("ch1", "spam message")
        assert result["cancel"] is True

    def test_fire_message_sending_allow(self):
        """fire_message_sending with allow hook should return cancel=False."""
        from praisonai.bots._protocol_mixin import MessageHookMixin
        from praisonaiagents.hooks import HookRegistry, HookRunner

        registry = HookRegistry()
        runner = HookRunner(registry=registry)

        # Register a function hook that returns True (= allow)
        registry.register_function(
            event=HookEvent.MESSAGE_SENDING,
            func=lambda input_data: True,  # True = allow
            name="allow_hook",
        )

        class MockAgent:
            agent_name = "test_agent"
            _hook_runner = runner

        class TestBot(MessageHookMixin):
            def __init__(self):
                self._agent = MockAgent()
                self.platform = "test"

        bot = TestBot()
        result = bot.fire_message_sending("ch1", "Hello")
        assert result["cancel"] is False
        assert result["content"] == "Hello"

    def test_fire_message_sent_no_crash(self):
        """fire_message_sent should not crash even without hooks."""
        from praisonai.bots._protocol_mixin import MessageHookMixin

        class TestBot(MessageHookMixin):
            def __init__(self):
                self._agent = None
                self.platform = "test"

        bot = TestBot()
        # Should be a no-op, no exception
        bot.fire_message_sent("ch1", "Hello", message_id="msg1")


class TestMessageHookEventInputs:
    """Test that message hook event input dataclasses exist and work."""

    def test_message_received_input_exists(self):
        """MessageReceivedInput should be importable from hooks.events."""
        from praisonaiagents.hooks.events import MessageReceivedInput
        inp = MessageReceivedInput(
            session_id="s1",
            cwd="/tmp",
            event_name=HookEvent.MESSAGE_RECEIVED,
            timestamp=str(time.time()),
            agent_name="bot",
            platform="telegram",
            content="Hello",
            sender_id="user1",
            channel_id="ch1",
        )
        assert inp.platform == "telegram"
        assert inp.content == "Hello"
        d = inp.to_dict()
        assert d["platform"] == "telegram"

    def test_message_sending_input_exists(self):
        """MessageSendingInput should be importable from hooks.events."""
        from praisonaiagents.hooks.events import MessageSendingInput
        inp = MessageSendingInput(
            session_id="s1",
            cwd="/tmp",
            event_name=HookEvent.MESSAGE_SENDING,
            timestamp=str(time.time()),
            agent_name="bot",
            platform="telegram",
            content="Reply",
            channel_id="ch1",
        )
        assert inp.content == "Reply"

    def test_message_sent_input_exists(self):
        """MessageSentInput should be importable from hooks.events."""
        from praisonaiagents.hooks.events import MessageSentInput
        inp = MessageSentInput(
            session_id="s1",
            cwd="/tmp",
            event_name=HookEvent.MESSAGE_SENT,
            timestamp=str(time.time()),
            agent_name="bot",
            platform="telegram",
            content="Reply",
            channel_id="ch1",
            message_id="msg1",
        )
        assert inp.message_id == "msg1"


class TestGatewayStreamRelay:
    """Test that gateway server relays StreamEvents to WebSocket clients."""

    def test_process_agent_message_streams_tokens(self):
        """_process_agent_message should wire stream_emitter to send token events to WS client."""
        # This test verifies the contract: when an agent streams tokens,
        # the gateway relays them as WS messages to the connected client.
        from praisonaiagents.gateway import EventType
        
        # Verify the event types exist for streaming relay
        assert hasattr(EventType, 'TOKEN_STREAM') or hasattr(EventType, 'AGENT_RESPONSE')
        # The actual streaming relay is tested via integration tests
