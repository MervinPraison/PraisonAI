"""
Live integration tests for Turso/libSQL.

Requires:
  - TURSO_DATABASE_URL and TURSO_AUTH_TOKEN env vars set
  - libsql installed (pip install libsql-experimental)

Run: TURSO_DATABASE_URL="libsql://..." TURSO_AUTH_TOKEN="..." pytest tests/integration/test_turso_live.py -v
"""

import os
import sys
import time
import uuid
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


@unittest.skipUnless(TURSO_URL and TURSO_TOKEN, "TURSO_DATABASE_URL/TURSO_AUTH_TOKEN not set")
class TestTursoLive(unittest.TestCase):
    """Live tests against a real Turso database."""

    def setUp(self):
        from praisonai.persistence.conversation.turso import TursoConversationStore
        self.prefix = f"test_{uuid.uuid4().hex[:8]}_"
        self.store = TursoConversationStore(
            url=TURSO_URL,
            auth_token=TURSO_TOKEN,
            table_prefix=self.prefix,
            auto_create_tables=True,
        )

    def tearDown(self):
        try:
            cur = self.store._conn.cursor()
            cur.execute(f"DROP TABLE IF EXISTS {self.store.messages_table}")
            cur.execute(f"DROP TABLE IF EXISTS {self.store.sessions_table}")
            self.store._conn.commit()
            self.store._sync()
        except Exception:
            pass
        self.store.close()

    def test_session_crud(self):
        from praisonai.persistence.conversation.base import ConversationSession
        session = ConversationSession(
            session_id=f"turso-test-{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            agent_id="test_agent",
            name="Turso Test Session",
        )
        created = self.store.create_session(session)
        self.assertEqual(created.session_id, session.session_id)

        fetched = self.store.get_session(session.session_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Turso Test Session")

        fetched.name = "Updated Turso Session"
        fetched.updated_at = time.time()
        self.store.update_session(fetched)
        updated = self.store.get_session(session.session_id)
        self.assertEqual(updated.name, "Updated Turso Session")

        deleted = self.store.delete_session(session.session_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_session(session.session_id))

    def test_message_crud(self):
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage
        session = ConversationSession(
            session_id=f"turso-msg-{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            agent_id="test_agent",
            name="Turso Message Test",
        )
        self.store.create_session(session)

        msg = ConversationMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            session_id=session.session_id,
            role="user",
            content="Hello from Turso!",
        )
        self.store.add_message(session.session_id, msg)

        messages = self.store.get_messages(session.session_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "Hello from Turso!")

        self.store.delete_session(session.session_id)

    def test_list_sessions(self):
        from praisonai.persistence.conversation.base import ConversationSession
        for i in range(3):
            session = ConversationSession(
                session_id=f"turso-list-{uuid.uuid4().hex[:8]}",
                user_id="list_user",
                agent_id="test_agent",
                name=f"List Session {i}",
            )
            self.store.create_session(session)

        sessions = self.store.list_sessions(user_id="list_user")
        self.assertGreaterEqual(len(sessions), 3)


if __name__ == "__main__":
    unittest.main()
