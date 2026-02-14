"""
TDD Tests for SessionStoreProtocol.

Tests protocol conformance for DefaultSessionStore, HierarchicalSessionStore,
and a mock implementation to prove swappability.
"""

import tempfile
from typing import Any, Dict, List, Optional


class MockSessionStore:
    """Minimal mock that implements SessionStoreProtocol interface.
    
    Proves that any class matching the protocol shape is accepted.
    """
    
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append({"role": role, "content": content})
        return True
    
    def get_chat_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        msgs = self._sessions.get(session_id, [])
        if max_messages:
            msgs = msgs[-max_messages:]
        return msgs
    
    def clear_session(self, session_id: str) -> bool:
        self._sessions[session_id] = []
        return True
    
    def delete_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True
    
    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions


class TestSessionStoreProtocolExists:
    """Test that SessionStoreProtocol can be imported."""
    
    def test_import_protocol(self):
        """SessionStoreProtocol must be importable from session.protocols."""
        from praisonaiagents.session.protocols import SessionStoreProtocol
        assert SessionStoreProtocol is not None
    
    def test_protocol_is_runtime_checkable(self):
        """Protocol must be @runtime_checkable for isinstance() checks."""
        from praisonaiagents.session.protocols import SessionStoreProtocol
        # Should not raise
        isinstance(object(), SessionStoreProtocol)
    
    def test_import_from_session_package(self):
        """SessionStoreProtocol must be importable from session package."""
        from praisonaiagents.session import SessionStoreProtocol
        assert SessionStoreProtocol is not None


class TestDefaultSessionStoreConformance:
    """DefaultSessionStore must satisfy SessionStoreProtocol."""
    
    def test_isinstance_check(self):
        """DefaultSessionStore must pass isinstance(store, SessionStoreProtocol)."""
        from praisonaiagents.session.protocols import SessionStoreProtocol
        from praisonaiagents.session.store import DefaultSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            assert isinstance(store, SessionStoreProtocol)
    
    def test_has_add_message(self):
        """DefaultSessionStore must have add_message method."""
        from praisonaiagents.session.store import DefaultSessionStore
        assert hasattr(DefaultSessionStore, 'add_message')
        assert callable(getattr(DefaultSessionStore, 'add_message'))
    
    def test_has_get_chat_history(self):
        """DefaultSessionStore must have get_chat_history method."""
        from praisonaiagents.session.store import DefaultSessionStore
        assert hasattr(DefaultSessionStore, 'get_chat_history')
        assert callable(getattr(DefaultSessionStore, 'get_chat_history'))
    
    def test_has_clear_session(self):
        """DefaultSessionStore must have clear_session method."""
        from praisonaiagents.session.store import DefaultSessionStore
        assert hasattr(DefaultSessionStore, 'clear_session')
        assert callable(getattr(DefaultSessionStore, 'clear_session'))
    
    def test_has_delete_session(self):
        """DefaultSessionStore must have delete_session method."""
        from praisonaiagents.session.store import DefaultSessionStore
        assert hasattr(DefaultSessionStore, 'delete_session')
        assert callable(getattr(DefaultSessionStore, 'delete_session'))
    
    def test_has_session_exists(self):
        """DefaultSessionStore must have session_exists method."""
        from praisonaiagents.session.store import DefaultSessionStore
        assert hasattr(DefaultSessionStore, 'session_exists')
        assert callable(getattr(DefaultSessionStore, 'session_exists'))


class TestHierarchicalSessionStoreConformance:
    """HierarchicalSessionStore must also satisfy SessionStoreProtocol."""
    
    def test_isinstance_check(self):
        """HierarchicalSessionStore must pass isinstance check."""
        from praisonaiagents.session.protocols import SessionStoreProtocol
        from praisonaiagents.session.hierarchy import HierarchicalSessionStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HierarchicalSessionStore(session_dir=tmpdir)
            assert isinstance(store, SessionStoreProtocol)


class TestMockStoreConformance:
    """Mock store implementing protocol interface must pass isinstance check."""
    
    def test_mock_isinstance_check(self):
        """MockSessionStore must pass isinstance(mock, SessionStoreProtocol)."""
        from praisonaiagents.session.protocols import SessionStoreProtocol
        
        mock = MockSessionStore()
        assert isinstance(mock, SessionStoreProtocol)
    
    def test_mock_add_and_get(self):
        """Mock store must support add_message and get_chat_history."""
        mock = MockSessionStore()
        mock.add_message("s1", "user", "Hello")
        mock.add_message("s1", "assistant", "Hi!")
        
        history = mock.get_chat_history("s1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
    
    def test_mock_clear_session(self):
        """Mock store must support clear_session."""
        mock = MockSessionStore()
        mock.add_message("s1", "user", "Hello")
        mock.clear_session("s1")
        assert mock.get_chat_history("s1") == []
    
    def test_mock_delete_session(self):
        """Mock store must support delete_session."""
        mock = MockSessionStore()
        mock.add_message("s1", "user", "Hello")
        mock.delete_session("s1")
        assert not mock.session_exists("s1")
    
    def test_mock_session_exists(self):
        """Mock store must support session_exists."""
        mock = MockSessionStore()
        assert not mock.session_exists("s1")
        mock.add_message("s1", "user", "Hello")
        assert mock.session_exists("s1")


class TestProtocolSwappability:
    """Test that protocol enables swapping stores without code changes."""
    
    def _use_store(self, store):
        """Helper that only depends on SessionStoreProtocol interface."""
        from praisonaiagents.session.protocols import SessionStoreProtocol
        assert isinstance(store, SessionStoreProtocol)
        
        store.add_message("test-swap", "user", "Hello from protocol")
        history = store.get_chat_history("test-swap")
        assert len(history) >= 1
        assert history[-1]["content"] == "Hello from protocol"
        
        store.clear_session("test-swap")
        assert store.get_chat_history("test-swap") == []
        
        store.delete_session("test-swap")
    
    def test_swap_default_store(self):
        """DefaultSessionStore works through protocol interface."""
        from praisonaiagents.session.store import DefaultSessionStore
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            self._use_store(store)
    
    def test_swap_hierarchical_store(self):
        """HierarchicalSessionStore works through protocol interface."""
        from praisonaiagents.session.hierarchy import HierarchicalSessionStore
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HierarchicalSessionStore(session_dir=tmpdir)
            self._use_store(store)
    
    def test_swap_mock_store(self):
        """MockSessionStore works through protocol interface."""
        mock = MockSessionStore()
        self._use_store(mock)


class TestSessionExports:
    """Test that all session components are properly exported."""
    
    def test_hierarchy_exports(self):
        """HierarchicalSessionStore must be importable from session package."""
        from praisonaiagents.session import HierarchicalSessionStore
        assert HierarchicalSessionStore is not None
    
    def test_hierarchy_store_getter(self):
        """get_hierarchical_session_store must be importable from session package."""
        from praisonaiagents.session import get_hierarchical_session_store
        assert callable(get_hierarchical_session_store)
    
    def test_session_snapshot_export(self):
        """SessionSnapshot must be importable from session package."""
        from praisonaiagents.session import SessionSnapshot
        assert SessionSnapshot is not None
    
    def test_extended_session_data_export(self):
        """ExtendedSessionData must be importable from session package."""
        from praisonaiagents.session import ExtendedSessionData
        assert ExtendedSessionData is not None
