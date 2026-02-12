"""Unit tests for BotSessionManager (per-user session isolation)."""

import asyncio
import pytest
import sys
import os

# Add wrapper to path so we can import bots._session
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai'))


class MockAgent:
    """Minimal mock of Agent for testing session isolation."""

    def __init__(self, name="test-agent"):
        self.name = name
        self.chat_history = []

    def chat(self, prompt):
        self.chat_history.append({"role": "user", "content": prompt})
        response = f"Reply to: {prompt}"
        self.chat_history.append({"role": "assistant", "content": response})
        return response


class TestBotSessionManagerImport:
    """Test that BotSessionManager can be imported."""

    def test_import(self):
        from praisonai.bots._session import BotSessionManager
        assert BotSessionManager is not None

    def test_instantiation(self):
        from praisonai.bots._session import BotSessionManager
        mgr = BotSessionManager()
        assert mgr.active_sessions == 0
        assert mgr.get_user_ids() == []

    def test_instantiation_with_max_history(self):
        from praisonai.bots._session import BotSessionManager
        mgr = BotSessionManager(max_history=50)
        assert mgr._max_history == 50


class TestBotSessionManagerChat:
    """Test per-user chat isolation."""

    @pytest.fixture
    def mgr(self):
        from praisonai.bots._session import BotSessionManager
        return BotSessionManager()

    @pytest.fixture
    def agent(self):
        return MockAgent()

    @pytest.mark.asyncio
    async def test_single_user_chat(self, mgr, agent):
        response = await mgr.chat(agent, "user1", "Hello")
        assert response == "Reply to: Hello"
        assert mgr.active_sessions == 1
        assert "user1" in mgr.get_user_ids()

    @pytest.mark.asyncio
    async def test_two_users_isolated(self, mgr, agent):
        await mgr.chat(agent, "alice", "I am Alice")
        await mgr.chat(agent, "bob", "I am Bob")

        assert mgr.active_sessions == 2
        # Each user should have 2 messages (user + assistant)
        assert len(mgr._histories["alice"]) == 2
        assert len(mgr._histories["bob"]) == 2
        # Alice's history should not contain Bob's message
        alice_msgs = [m["content"] for m in mgr._histories["alice"]]
        assert "I am Bob" not in alice_msgs
        bob_msgs = [m["content"] for m in mgr._histories["bob"]]
        assert "I am Alice" not in bob_msgs

    @pytest.mark.asyncio
    async def test_agent_history_restored(self, mgr, agent):
        """Agent's original chat_history should be restored after each call."""
        agent.chat_history = [{"role": "system", "content": "original"}]
        await mgr.chat(agent, "user1", "test")
        # Agent's history should be restored to original
        assert len(agent.chat_history) == 1
        assert agent.chat_history[0]["content"] == "original"

    @pytest.mark.asyncio
    async def test_conversation_continuity(self, mgr, agent):
        """Same user's messages should accumulate in their session."""
        await mgr.chat(agent, "user1", "First message")
        await mgr.chat(agent, "user1", "Second message")
        # Should have 4 messages: 2 user + 2 assistant
        assert len(mgr._histories["user1"]) == 4

    @pytest.mark.asyncio
    async def test_max_history_truncation(self, agent):
        from praisonai.bots._session import BotSessionManager
        mgr = BotSessionManager(max_history=4)
        await mgr.chat(agent, "user1", "msg1")
        await mgr.chat(agent, "user1", "msg2")
        await mgr.chat(agent, "user1", "msg3")  # This would make 6 messages
        # Should be truncated to last 4
        assert len(mgr._histories["user1"]) == 4


class TestBotSessionManagerReset:
    """Test session reset functionality."""

    @pytest.fixture
    def mgr(self):
        from praisonai.bots._session import BotSessionManager
        return BotSessionManager()

    @pytest.fixture
    def agent(self):
        return MockAgent()

    @pytest.mark.asyncio
    async def test_reset_existing_user(self, mgr, agent):
        await mgr.chat(agent, "user1", "Hello")
        assert mgr.active_sessions == 1
        result = mgr.reset("user1")
        assert result is True
        assert mgr.active_sessions == 0

    def test_reset_nonexistent_user(self, mgr):
        result = mgr.reset("nobody")
        assert result is False

    @pytest.mark.asyncio
    async def test_reset_all(self, mgr, agent):
        await mgr.chat(agent, "user1", "Hello")
        await mgr.chat(agent, "user2", "World")
        count = mgr.reset_all()
        assert count == 2
        assert mgr.active_sessions == 0

    @pytest.mark.asyncio
    async def test_reset_then_chat_fresh(self, mgr, agent):
        """After reset, user should start with empty history."""
        await mgr.chat(agent, "user1", "old message")
        mgr.reset("user1")
        await mgr.chat(agent, "user1", "new message")
        assert len(mgr._histories["user1"]) == 2  # Only new conversation
        msgs = [m["content"] for m in mgr._histories["user1"]]
        assert "old message" not in msgs


class TestBotSessionManagerConcurrency:
    """Test concurrent access safety."""

    @pytest.mark.asyncio
    async def test_concurrent_same_user(self):
        """Two concurrent chats from same user should be serialized."""
        from praisonai.bots._session import BotSessionManager

        agent = MockAgent()
        mgr = BotSessionManager()

        async def slow_chat():
            return await mgr.chat(agent, "user1", "concurrent")

        results = await asyncio.gather(slow_chat(), slow_chat())
        assert len(results) == 2
        # Both should succeed
        assert all(r.startswith("Reply to:") for r in results)
        # Should have 4 messages total (2 calls × 2 messages each)
        assert len(mgr._histories["user1"]) == 4

    @pytest.mark.asyncio
    async def test_concurrent_different_users(self):
        """Two concurrent chats from different users should be independent."""
        from praisonai.bots._session import BotSessionManager

        agent = MockAgent()
        mgr = BotSessionManager()

        async def chat_as(user, msg):
            return await mgr.chat(agent, user, msg)

        results = await asyncio.gather(
            chat_as("alice", "I am Alice"),
            chat_as("bob", "I am Bob"),
        )
        assert len(results) == 2
        assert mgr.active_sessions == 2
