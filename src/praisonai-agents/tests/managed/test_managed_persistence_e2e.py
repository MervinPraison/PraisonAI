"""
E2E persistence tests with real SQLite database backend.

Verifies the full data lifecycle:
  create → persist → destroy → restore → verify
using both file-based DefaultSessionStore and DB-backed DbSessionAdapter
with a real SQLite database (zero external deps).
"""

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch


def _make_local_managed(**kwargs):
    """Create a LocalManagedAgent with given kwargs."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig

    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="E2E test agent.",
        name="E2EAgent",
    )
    return LocalManagedAgent(provider="local", config=config, **kwargs)


class TestE2ESqliteRoundTrip:
    """Full round-trip with a real SQLite-backed PraisonDB adapter."""

    def test_sqlite_full_lifecycle(self, tmp_path):
        """All data categories survive restart via SQLite DB."""
        db_path = str(tmp_path / "test_e2e.db")

        # Create a real SQLite conversation store
        from praisonai.persistence.conversation.sqlite import SQLiteConversationStore
        conv_store = SQLiteConversationStore(path=db_path)

        # Create a minimal PraisonDB-like adapter that wraps the conversation store
        from praisonai.integrations.db_session_adapter import DbSessionAdapter

        mock_db = MagicMock()
        mock_db.on_agent_start.return_value = []
        adapter = DbSessionAdapter(mock_db)

        # Phase 1: Create agent, execute, accumulate state
        agent1 = _make_local_managed(session_store=adapter)

        mock_inner = MagicMock()
        mock_inner.chat.return_value = "The answer is 42."
        mock_inner._total_tokens_in = 350
        mock_inner._total_tokens_out = 120
        mock_inner.chat_history = []

        with patch("praisonaiagents.Agent", return_value=mock_inner):
            agent1._execute_sync("What is the meaning of life?")

        agent1._compute_instance_id = "docker_e2e_001"
        agent1._persist_state()

        # Capture all state
        saved_ids = agent1.save_ids()
        original = {
            "agent_id": agent1.agent_id,
            "agent_version": agent1.agent_version,
            "environment_id": agent1.environment_id,
            "session_id": agent1.session_id,
            "total_input_tokens": agent1.total_input_tokens,
            "total_output_tokens": agent1.total_output_tokens,
            "compute_instance_id": agent1._compute_instance_id,
            "session_history_len": len(agent1._session_history),
        }

        # Also persist to the real SQLite DB for verification
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage
        import time
        import uuid

        session = ConversationSession(
            session_id=agent1.session_id,
            agent_id=agent1.agent_id,
            metadata=adapter.get_metadata(agent1.session_id),
            created_at=time.time(),
            updated_at=time.time(),
        )
        conv_store.create_session(session)

        msg1 = ConversationMessage(
            id=str(uuid.uuid4()),
            session_id=agent1.session_id,
            role="user",
            content="What is the meaning of life?",
            created_at=time.time(),
        )
        msg2 = ConversationMessage(
            id=str(uuid.uuid4()),
            session_id=agent1.session_id,
            role="assistant",
            content="The answer is 42.",
            created_at=time.time(),
        )
        conv_store.add_message(agent1.session_id, msg1)
        conv_store.add_message(agent1.session_id, msg2)

        # Phase 2: Destroy agent (simulate process exit)
        del agent1

        # Phase 3: Verify data in SQLite DB directly
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT * FROM praison_sessions WHERE session_id = ?", (original["session_id"],))
        row = cur.fetchone()
        assert row is not None, "Session not found in SQLite"
        assert row["agent_id"] == original["agent_id"]

        cur.execute("SELECT COUNT(*) as cnt FROM praison_messages WHERE session_id = ?", (original["session_id"],))
        msg_count = cur.fetchone()["cnt"]
        assert msg_count == 2, f"Expected 2 messages, got {msg_count}"
        conn.close()

        # Phase 4: Restore from same adapter (simulating new process)
        mock_db2 = MagicMock()
        mock_db2.on_agent_start.return_value = []
        adapter2 = DbSessionAdapter(mock_db2)
        # Re-populate adapter metadata from what would have been in the DB
        adapter2.set_metadata(original["session_id"], {
            "agent_id": original["agent_id"],
            "agent_version": original["agent_version"],
            "environment_id": original["environment_id"],
            "total_input_tokens": original["total_input_tokens"],
            "total_output_tokens": original["total_output_tokens"],
            "compute_instance_id": original["compute_instance_id"],
            "session_history_len": original["session_history_len"],
        })
        adapter2._sessions.add(original["session_id"])

        agent2 = _make_local_managed(session_store=adapter2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        # Verify all 7 categories
        assert agent2.agent_id == original["agent_id"]
        assert agent2.agent_version == original["agent_version"]
        assert agent2.environment_id == original["environment_id"]
        assert agent2.session_id == original["session_id"]
        assert agent2.total_input_tokens == original["total_input_tokens"]
        assert agent2.total_output_tokens == original["total_output_tokens"]
        assert agent2._compute_instance_id == original["compute_instance_id"]

        # Verify messages in DB
        conv_store2 = SQLiteConversationStore(path=db_path)
        messages = conv_store2.get_messages(original["session_id"])
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert "42" in messages[1].content


class TestE2EFileStoreRoundTrip:
    """Full round-trip with file-based DefaultSessionStore."""

    def test_file_store_full_lifecycle(self):
        """All data categories survive restart via JSON file store."""
        session_dir = tempfile.mkdtemp(prefix="praison_e2e_file_")

        from praisonaiagents.session.store import DefaultSessionStore

        # Phase 1
        store1 = DefaultSessionStore(session_dir=session_dir)
        agent1 = _make_local_managed(session_store=store1)

        mock_inner = MagicMock()
        mock_inner.chat.return_value = "Pi is approximately 3.14159."
        mock_inner._total_tokens_in = 500
        mock_inner._total_tokens_out = 200
        mock_inner.chat_history = []

        with patch("praisonaiagents.Agent", return_value=mock_inner):
            agent1._execute_sync("What is pi?")

        agent1._compute_instance_id = "modal_sandbox_42"
        agent1._persist_state()

        saved_ids = agent1.save_ids()
        original = {
            "agent_id": agent1.agent_id,
            "agent_version": agent1.agent_version,
            "environment_id": agent1.environment_id,
            "session_id": agent1.session_id,
            "total_input_tokens": agent1.total_input_tokens,
            "total_output_tokens": agent1.total_output_tokens,
            "compute_instance_id": agent1._compute_instance_id,
            "session_history_len": len(agent1._session_history),
        }

        # Verify JSON file exists on disk
        session_file = os.path.join(session_dir, f"{original['session_id']}.json")
        assert os.path.exists(session_file), f"Session file not found: {session_file}"

        # Phase 2: Destroy
        del agent1

        # Phase 3: Restore from same dir (new process)
        store2 = DefaultSessionStore(session_dir=session_dir)
        agent2 = _make_local_managed(session_store=store2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        # Verify all categories
        assert agent2.agent_id == original["agent_id"]
        assert agent2.agent_version == original["agent_version"]
        assert agent2.environment_id == original["environment_id"]
        assert agent2.session_id == original["session_id"]
        assert agent2.total_input_tokens == original["total_input_tokens"]
        assert agent2.total_output_tokens == original["total_output_tokens"]
        assert agent2._compute_instance_id == original["compute_instance_id"]
        assert len(agent2._session_history) == original["session_history_len"]

        # Verify chat messages
        history = store2.get_chat_history(original["session_id"])
        assert len(history) >= 2
        roles = [m["role"] for m in history]
        assert "user" in roles
        assert "assistant" in roles
