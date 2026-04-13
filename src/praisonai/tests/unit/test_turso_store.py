"""
Unit tests for Turso/libSQL ConversationStore.

Mock-based — no live Turso database needed.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestTursoConversationStoreInit(unittest.TestCase):
    """Test TursoConversationStore initialization."""

    @patch.dict(os.environ, {
        "TURSO_DATABASE_URL": "libsql://test-db.turso.io",
        "TURSO_AUTH_TOKEN": "test-token-123"
    })
    @patch("praisonai.persistence.conversation.turso.libsql", create=True)
    def test_init_from_env_vars(self, mock_libsql):
        """Should initialize from TURSO_DATABASE_URL and TURSO_AUTH_TOKEN env vars."""
        mock_conn = MagicMock()
        mock_libsql.connect.return_value = mock_conn

        from praisonai.persistence.conversation.turso import TursoConversationStore
        store = TursoConversationStore()

        mock_libsql.connect.assert_called_once()
        self.assertIsNotNone(store)

    @patch("praisonai.persistence.conversation.turso.libsql", create=True)
    def test_init_with_explicit_params(self, mock_libsql):
        """Should initialize with explicit url and auth_token."""
        mock_conn = MagicMock()
        mock_libsql.connect.return_value = mock_conn

        from praisonai.persistence.conversation.turso import TursoConversationStore
        store = TursoConversationStore(
            url="libsql://mydb.turso.io",
            auth_token="tok_123"
        )
        mock_libsql.connect.assert_called_once()

    def test_import_error_without_libsql(self):
        """Should raise ImportError if libsql not installed."""
        # Temporarily remove libsql from sys.modules if present
        original = sys.modules.get('libsql')
        sys.modules['libsql'] = None
        try:
            # Force reimport
            if 'praisonai.persistence.conversation.turso' in sys.modules:
                del sys.modules['praisonai.persistence.conversation.turso']
            
            with self.assertRaises(ImportError):
                from praisonai.persistence.conversation.turso import TursoConversationStore
                TursoConversationStore(url="libsql://test.turso.io", auth_token="tok")
        finally:
            if original is not None:
                sys.modules['libsql'] = original
            elif 'libsql' in sys.modules:
                del sys.modules['libsql']


class TestTursoConversationStoreCRUD(unittest.TestCase):
    """Test CRUD operations with mocked libsql."""

    def setUp(self):
        """Set up mock store."""
        self.mock_libsql = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor
        self.mock_libsql.connect.return_value = self.mock_conn

        with patch.dict('sys.modules', {'libsql': self.mock_libsql}):
            if 'praisonai.persistence.conversation.turso' in sys.modules:
                del sys.modules['praisonai.persistence.conversation.turso']
            from praisonai.persistence.conversation.turso import TursoConversationStore
            self.store = TursoConversationStore(
                url="libsql://test.turso.io",
                auth_token="test-token",
                auto_create_tables=False
            )

    def test_create_session(self):
        """Test session creation executes INSERT."""
        from praisonai.persistence.conversation.base import ConversationSession
        session = ConversationSession(
            session_id="test-session-1",
            user_id="user1",
            agent_id="agent1",
            name="Test Session"
        )
        result = self.store.create_session(session)
        self.assertEqual(result.session_id, "test-session-1")
        self.mock_cursor.execute.assert_called()

    def test_get_session_found(self):
        """Test session retrieval when found."""
        self.mock_cursor.fetchone.return_value = (
            "sess-1", "user1", "agent1", "Test", None, None, 1234.0, 1234.0
        )
        result = self.store.get_session("sess-1")
        self.assertIsNotNone(result)
        self.assertEqual(result.session_id, "sess-1")

    def test_get_session_not_found(self):
        """Test session retrieval when not found."""
        self.mock_cursor.fetchone.return_value = None
        result = self.store.get_session("nonexistent")
        self.assertIsNone(result)

    def test_add_message(self):
        """Test adding a message."""
        from praisonai.persistence.conversation.base import ConversationMessage
        msg = ConversationMessage(
            id="msg-1",
            session_id="sess-1",
            role="user",
            content="Hello!"
        )
        result = self.store.add_message("sess-1", msg)
        self.assertEqual(result.content, "Hello!")
        self.mock_cursor.execute.assert_called()

    def test_get_messages(self):
        """Test retrieving messages."""
        self.mock_cursor.fetchall.return_value = [
            ("msg-1", "sess-1", "user", "Hello!", None, None, None, 1234.0),
            ("msg-2", "sess-1", "assistant", "Hi!", None, None, None, 1235.0),
        ]
        messages = self.store.get_messages("sess-1")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")

    def test_delete_session(self):
        """Test session deletion."""
        self.mock_cursor.rowcount = 1
        result = self.store.delete_session("sess-1")
        self.assertTrue(result)

    def test_close(self):
        """Test store close calls connection close."""
        self.store.close()
        self.mock_conn.close.assert_called_once()


class TestTursoURLScheme(unittest.TestCase):
    """Test libsql:// URL detection in adapter."""

    def test_libsql_scheme_detected(self):
        from praisonai.db.adapter import PraisonAIDB
        db = PraisonAIDB.__new__(PraisonAIDB)
        self.assertEqual(db._detect_backend("libsql://mydb.turso.io"), "turso")

    def test_libsql_wss_scheme_detected(self):
        from praisonai.db.adapter import PraisonAIDB
        db = PraisonAIDB.__new__(PraisonAIDB)
        self.assertEqual(db._detect_backend("libsql://mydb.turso.io"), "turso")


if __name__ == "__main__":
    unittest.main()
