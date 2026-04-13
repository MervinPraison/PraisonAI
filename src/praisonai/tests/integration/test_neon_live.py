"""
Live integration tests for Neon serverless PostgreSQL.

Requires:
  - NEON_DATABASE_URL env var set to a valid Neon connection string
  - psycopg2-binary installed

Run: NEON_DATABASE_URL="postgresql://..." pytest tests/integration/test_neon_live.py -v
"""

import os
import sys
import time
import uuid
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

NEON_URL = os.getenv("NEON_DATABASE_URL")


@unittest.skipUnless(NEON_URL, "NEON_DATABASE_URL not set")
class TestNeonLive(unittest.TestCase):
    """Live tests against a real Neon database."""

    def setUp(self):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        self.store = PostgresConversationStore(
            url=NEON_URL,
            table_prefix=f"test_{uuid.uuid4().hex[:8]}_",
            auto_create_tables=True,
        )

    def tearDown(self):
        # Clean up test tables
        try:
            conn = self.store._get_conn()
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {self.store.messages_table} CASCADE")
                cur.execute(f"DROP TABLE IF EXISTS {self.store.sessions_table} CASCADE")
                conn.commit()
            self.store._put_conn(conn)
        except Exception:
            pass
        self.store.close()

    def test_serverless_detected(self):
        self.assertTrue(self.store._serverless)

    def test_ssl_enforced(self):
        """Neon connection should have SSL enabled."""
        conn = self.store._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW ssl")
                result = cur.fetchone()
                self.assertEqual(result[0], "on")
        finally:
            self.store._put_conn(conn)

    def test_session_crud(self):
        from praisonai.persistence.conversation.base import ConversationSession
        session = ConversationSession(
            session_id=f"neon-test-{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            agent_id="test_agent",
            name="Neon Test Session",
        )
        # Create
        created = self.store.create_session(session)
        self.assertEqual(created.session_id, session.session_id)

        # Read
        fetched = self.store.get_session(session.session_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Neon Test Session")

        # Update
        fetched.name = "Updated Neon Session"
        fetched.updated_at = time.time()
        self.store.update_session(fetched)
        updated = self.store.get_session(session.session_id)
        self.assertEqual(updated.name, "Updated Neon Session")

        # Delete
        deleted = self.store.delete_session(session.session_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_session(session.session_id))

    def test_message_crud(self):
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage
        session = ConversationSession(
            session_id=f"neon-msg-{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            agent_id="test_agent",
            name="Neon Message Test",
        )
        self.store.create_session(session)

        msg = ConversationMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            session_id=session.session_id,
            role="user",
            content="Hello from Neon!",
        )
        self.store.add_message(session.session_id, msg)

        messages = self.store.get_messages(session.session_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "Hello from Neon!")

        # Cleanup
        self.store.delete_session(session.session_id)


if __name__ == "__main__":
    unittest.main()
