"""
TDD Tests for Bot Session Persistence.

Tests that BotSessionManager uses SessionStoreProtocol for persistent
per-user session isolation instead of in-memory-only storage.
"""

import asyncio
import tempfile

import pytest
from typing import Any, Dict, List

from praisonaiagents.session.store import DefaultSessionStore


class FakeAgent:
    """Minimal Agent mock for testing BotSessionManager."""
    
    def __init__(self, name: str = "TestAgent"):
        self.name = name
        self.chat_history: List[Dict[str, Any]] = []
    
    def chat(self, prompt: str) -> str:
        self.chat_history.append({"role": "user", "content": prompt})
        response = f"Response to: {prompt}"
        self.chat_history.append({"role": "assistant", "content": response})
        return response


def _run_async(coro):
    """Helper to run async coroutines in tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _import_bot_session_manager():
    """Return ``BotSessionManager`` from the optional ``praisonai-bot`` package.

    Skip only when the top-level ``praisonai_bot`` package is unavailable, then
    import ``_session`` normally. Targeting the deep module with
    ``importorskip`` would turn a genuine ``ImportError`` *inside* an installed
    package into a skip, silently dropping these tests from CI instead of
    surfacing the regression.
    """
    pytest.importorskip(
        "praisonai_bot",
        reason="praisonai-bot is not installed",
    )
    from praisonai_bot.bots._session import BotSessionManager

    return BotSessionManager


class TestBotSessionManagerWithStore:
    """Tests for BotSessionManager using persistent session store."""
    
    def _make_manager(self, tmpdir: str, platform: str = "test"):
        """Create a BotSessionManager with a persistent store.

        Imported as a package rather than by pushing a directory onto sys.path.
        The old helper walked five levels up to ``praisonai/praisonai/bots`` and
        imported a bare ``_session``; the bots code has since moved to the
        ``praisonai-bot`` package, that directory no longer exists, and all
        eleven tests in this class had been failing with
        ``ModuleNotFoundError: No module named '_session'`` ever since.
        """
        BotSessionManager = _import_bot_session_manager()
        store = DefaultSessionStore(session_dir=tmpdir)
        return BotSessionManager(store=store, platform=platform)
    
    def test_constructor_accepts_store(self):
        """BotSessionManager must accept a store parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            assert mgr is not None
    
    def test_constructor_accepts_platform(self):
        """BotSessionManager must accept a platform parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir, platform="telegram")
            assert mgr._platform == "telegram"
    
    def test_chat_persists_to_store(self):
        """After chat(), messages must be persisted in the store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            agent = FakeAgent()
            
            _run_async(mgr.chat(agent, "user1", "Hello"))
            
            store = DefaultSessionStore(session_dir=tmpdir)
            key = "bot_test_user1"
            history = store.get_chat_history(key)
            assert len(history) >= 2
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "Hello"
    
    def test_chat_restores_from_store(self):
        """On second call, history must be loaded from store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            agent = FakeAgent()
            
            _run_async(mgr.chat(agent, "user1", "Hello"))
            _run_async(mgr.chat(agent, "user1", "How are you?"))
            
            store = DefaultSessionStore(session_dir=tmpdir)
            key = "bot_test_user1"
            history = store.get_chat_history(key)
            # Should have 4 messages: user+assistant from each call
            assert len(history) >= 4
    
    def test_multi_user_isolation(self):
        """Different users must have isolated sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            agent = FakeAgent()
            
            _run_async(mgr.chat(agent, "alice", "Hi from Alice"))
            _run_async(mgr.chat(agent, "bob", "Hi from Bob"))
            
            store = DefaultSessionStore(session_dir=tmpdir)
            alice_history = store.get_chat_history("bot_test_alice")
            bob_history = store.get_chat_history("bot_test_bob")
            
            assert len(alice_history) >= 2
            assert len(bob_history) >= 2
            assert alice_history[0]["content"] == "Hi from Alice"
            assert bob_history[0]["content"] == "Hi from Bob"
    
    def test_agent_history_not_corrupted(self):
        """Agent's own chat_history must not be corrupted by bot sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            agent = FakeAgent()
            agent.chat_history = [{"role": "system", "content": "Original"}]
            
            _run_async(mgr.chat(agent, "user1", "Hello"))
            
            # Agent's history must be restored to original
            assert len(agent.chat_history) == 1
            assert agent.chat_history[0]["content"] == "Original"
    
    def test_reset_clears_store(self):
        """reset() must clear user's session from the store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            agent = FakeAgent()
            
            _run_async(mgr.chat(agent, "user1", "Hello"))
            mgr.reset("user1")
            
            store = DefaultSessionStore(session_dir=tmpdir)
            key = "bot_test_user1"
            history = store.get_chat_history(key)
            assert len(history) == 0
    
    def test_reset_all_clears_all_store_sessions(self):
        """reset_all() must clear all bot sessions from the store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            agent = FakeAgent()
            
            _run_async(mgr.chat(agent, "user1", "Hi"))
            _run_async(mgr.chat(agent, "user2", "Hey"))
            
            count = mgr.reset_all()
            assert count == 2
    
    def test_persistence_across_manager_instances(self):
        """Sessions must survive across BotSessionManager instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First manager instance
            mgr1 = self._make_manager(tmpdir)
            agent = FakeAgent()
            _run_async(mgr1.chat(agent, "user1", "Remember this"))
            
            # Second manager instance (simulates restart)
            mgr2 = self._make_manager(tmpdir)
            agent2 = FakeAgent()
            _run_async(mgr2.chat(agent2, "user1", "What did I say?"))
            
            # Check agent2's chat_history during the call had previous context
            store = DefaultSessionStore(session_dir=tmpdir)
            key = "bot_test_user1"
            history = store.get_chat_history(key)
            # Should have messages from both sessions
            assert len(history) >= 4
            assert history[0]["content"] == "Remember this"
    
    def test_backward_compat_no_store(self):
        """BotSessionManager must still work without a store (in-memory fallback)."""
        BotSessionManager = _import_bot_session_manager()
        # No store parameter = backward compatible in-memory mode
        mgr = BotSessionManager()
        agent = FakeAgent()
        
        _run_async(mgr.chat(agent, "user1", "Hello"))
        assert mgr.active_sessions >= 1
    
    def test_session_key_format(self):
        """Session key must follow bot_{platform}_{user_id} format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir, platform="telegram")
            agent = FakeAgent()
            
            _run_async(mgr.chat(agent, "12345", "Hello"))
            
            store = DefaultSessionStore(session_dir=tmpdir)
            assert store.session_exists("bot_telegram_12345")
