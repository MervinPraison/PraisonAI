"""
Live integration tests for Supabase (REST API mode).

Requires:
  - SUPABASE_URL and SUPABASE_KEY env vars set
  - supabase-py installed
  - Tables created in Supabase dashboard (or auto_create_tables=True with service key)

Run: SUPABASE_URL="https://..." SUPABASE_KEY="..." pytest tests/integration/test_supabase_live.py -v
"""

import os
import sys
import time
import uuid
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


@unittest.skipUnless(SUPABASE_URL and SUPABASE_KEY, "SUPABASE_URL/SUPABASE_KEY not set")
class TestSupabaseLive(unittest.TestCase):
    """Live tests against a real Supabase project."""

    def setUp(self):
        from praisonai.persistence.conversation.supabase import SupabaseConversationStore
        self.store = SupabaseConversationStore(
            url=SUPABASE_URL,
            key=SUPABASE_KEY,
            table_prefix="praison_",
        )

    def test_session_crud(self):
        from praisonai.persistence.conversation.base import ConversationSession
        session = ConversationSession(
            session_id=f"sb-test-{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            agent_id="test_agent",
            name="Supabase Test Session",
        )
        created = self.store.create_session(session)
        self.assertEqual(created.session_id, session.session_id)

        fetched = self.store.get_session(session.session_id)
        self.assertIsNotNone(fetched)

        # Cleanup
        self.store.delete_session(session.session_id)

    def test_message_crud(self):
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage
        session = ConversationSession(
            session_id=f"sb-msg-{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            agent_id="test_agent",
            name="Supabase Msg Test",
        )
        self.store.create_session(session)

        msg = ConversationMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            session_id=session.session_id,
            role="user",
            content="Hello from Supabase!",
        )
        self.store.add_message(session.session_id, msg)

        messages = self.store.get_messages(session.session_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "Hello from Supabase!")

        self.store.delete_session(session.session_id)


if __name__ == "__main__":
    unittest.main()
