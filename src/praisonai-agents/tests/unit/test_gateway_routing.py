"""Unit tests for gateway routing: _determine_routing_context, _resolve_agent_for_message, _inject_routing_handler."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai'))


class MockAgent:
    def __init__(self, name="agent"):
        self.name = name
        self.chat_history = []

    def chat(self, prompt):
        return f"[{self.name}] {prompt}"


class MockBot:
    """Minimal mock bot that supports on_message / set_agent."""

    def __init__(self, agent=None):
        self._agent = agent
        self._message_handlers = []
        self.is_running = True
        self.platform = "mock"

    def on_message(self, handler):
        self._message_handlers.append(handler)
        return handler

    def set_agent(self, agent):
        self._agent = agent


class TestDetermineRoutingContext:
    """Test _determine_routing_context logic."""

    def _get_gateway(self):
        from praisonai.gateway.server import WebSocketGateway
        return WebSocketGateway()

    def test_private_chat_maps_to_dm(self):
        gw = self._get_gateway()
        ctx = gw._determine_routing_context("telegram", {"chat_type": "private"})
        assert ctx == "dm"

    def test_group_chat_maps_to_group(self):
        gw = self._get_gateway()
        ctx = gw._determine_routing_context("telegram", {"chat_type": "group"})
        assert ctx == "group"

    def test_supergroup_maps_to_group(self):
        gw = self._get_gateway()
        ctx = gw._determine_routing_context("telegram", {"chat_type": "supergroup"})
        assert ctx == "group"

    def test_channel_maps_to_channel(self):
        gw = self._get_gateway()
        ctx = gw._determine_routing_context("telegram", {"chat_type": "channel"})
        assert ctx == "channel"

    def test_unknown_maps_to_default(self):
        gw = self._get_gateway()
        ctx = gw._determine_routing_context("telegram", {"chat_type": "unknown_type"})
        assert ctx == "default"

    def test_dm_flag_override(self):
        gw = self._get_gateway()
        ctx = gw._determine_routing_context("discord", {"chat_type": "", "is_dm": True})
        assert ctx == "dm"


class TestResolveAgentForMessage:
    """Test _resolve_agent_for_message with routing rules."""

    def _get_gateway(self):
        from praisonai.gateway.server import WebSocketGateway
        gw = WebSocketGateway()
        return gw

    def test_no_routing_rules_returns_none(self):
        gw = self._get_gateway()
        result = gw._resolve_agent_for_message("telegram", "dm")
        assert result is None

    def test_exact_route_match(self):
        gw = self._get_gateway()
        agent = MockAgent("personal")
        gw._agents["personal"] = agent
        gw._routing_rules["telegram"] = {"dm": "personal"}
        result = gw._resolve_agent_for_message("telegram", "dm")
        assert result is agent

    def test_default_fallback(self):
        gw = self._get_gateway()
        agent = MockAgent("fallback")
        gw._agents["fallback"] = agent
        gw._routing_rules["telegram"] = {"default": "fallback"}
        result = gw._resolve_agent_for_message("telegram", "unknown_context")
        assert result is agent

    def test_no_matching_channel(self):
        gw = self._get_gateway()
        gw._routing_rules["telegram"] = {"dm": "agent1"}
        result = gw._resolve_agent_for_message("discord", "dm")
        assert result is None

    def test_agent_not_registered(self):
        gw = self._get_gateway()
        gw._routing_rules["telegram"] = {"dm": "nonexistent"}
        result = gw._resolve_agent_for_message("telegram", "dm")
        assert result is None


class TestInjectRoutingHandler:
    """Test _inject_routing_handler injects on_message handler."""

    def _get_gateway(self):
        from praisonai.gateway.server import WebSocketGateway
        return WebSocketGateway()

    def test_handler_injected(self):
        gw = self._get_gateway()
        bot = MockBot()
        assert len(bot._message_handlers) == 0
        gw._inject_routing_handler("discord", bot)
        assert len(bot._message_handlers) == 1

    @pytest.mark.asyncio
    async def test_handler_sets_agent_based_on_route(self):
        gw = self._get_gateway()
        personal_agent = MockAgent("personal")
        support_agent = MockAgent("support")
        gw._agents["personal"] = personal_agent
        gw._agents["support"] = support_agent
        gw._routing_rules["discord"] = {"dm": "personal", "channel": "support"}

        bot = MockBot(agent=support_agent)
        gw._inject_routing_handler("discord", bot)

        # Simulate a DM message
        class FakeSender:
            user_id = "user1"
        class FakeChannel:
            channel_type = "dm"
        class FakeMessage:
            sender = FakeSender()
            channel = FakeChannel()
            text = "hello"

        handler = bot._message_handlers[0]
        await handler(FakeMessage())
        # Bot's agent should now be personal (DM route)
        assert bot._agent is personal_agent


class TestHealthEndpointChannels:
    """Test that health() includes per-channel status."""

    def test_health_empty_channels(self):
        from praisonai.gateway.server import WebSocketGateway
        gw = WebSocketGateway()
        h = gw.health()
        assert "channels" in h
        assert h["channels"] == {}

    def test_health_with_channel_bots(self):
        from praisonai.gateway.server import WebSocketGateway
        gw = WebSocketGateway()
        bot = MockBot()
        gw._channel_bots["telegram"] = bot
        h = gw.health()
        assert "telegram" in h["channels"]
        assert h["channels"]["telegram"]["platform"] == "mock"
        assert h["channels"]["telegram"]["running"] is True
