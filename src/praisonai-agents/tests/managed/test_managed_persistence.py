"""
Tests for managed agent data persistence — all 7 data categories.

Tests that agent_id, version, environment_id, session history, usage tokens,
compute instance refs, and chat messages all survive across process restarts.

Covers:
- File-based persistence (DefaultSessionStore)
- DB-backed persistence (DbSessionAdapter)
- Auto-detection (db= → DB, else → file)
- Full resume scenario: save → destroy → restore → verify
"""

import os
import tempfile
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_session_dir():
    """Create a temporary session directory."""
    return tempfile.mkdtemp(prefix="praison_test_sessions_")


def _make_local_managed(session_dir=None, session_store=None, db=None, **kwargs):
    """Create a LocalManagedAgent with optional persistence backends."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig

    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="Test agent.",
        name="TestAgent",
    )
    return LocalManagedAgent(
        provider="local",
        config=config,
        session_store=session_store,
        db=db,
        **kwargs,
    )


# ===========================================================================
# 1. Session store injection
# ===========================================================================

class TestSessionStoreInjection:
    """LocalManagedAgent accepts an external session store."""

    def test_accepts_session_store_param(self):
        """Constructor accepts session_store= param."""
        mock_store = MagicMock()
        agent = _make_local_managed(session_store=mock_store)
        assert agent._get_session_store() is mock_store

    def test_default_uses_file_store(self):
        """Without session_store=, uses DefaultSessionStore."""
        agent = _make_local_managed()
        store = agent._get_session_store()
        assert store is not None
        assert hasattr(store, "add_message")

    def test_db_creates_adapter(self):
        """When db= is passed, creates a DbSessionAdapter."""
        mock_db = MagicMock()
        agent = _make_local_managed(db=mock_db)
        store = agent._get_session_store()
        # Should be a DbSessionAdapter wrapping the mock_db
        assert store is not None
        assert hasattr(store, "add_message")


# ===========================================================================
# 2. Agent metadata persistence
# ===========================================================================

class TestAgentMetadataPersistence:
    """Agent IDs (agent_id, version, env_id) survive restarts."""

    def test_metadata_persisted_on_ensure_agent(self):
        """After _ensure_agent(), metadata is written to session store."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)
        # Trigger agent creation (mock the inner Agent to avoid LLM calls)
        with patch("praisonaiagents.Agent") as MockAgent:
            MockAgent.return_value = MagicMock()
            agent._ensure_agent()
            agent._ensure_session()

        # Verify metadata written to store
        session = store.get_session(agent.session_id)
        assert session is not None
        meta = session.metadata
        assert meta.get("agent_id") == agent.agent_id
        assert meta.get("agent_version") == agent.agent_version
        assert meta.get("environment_id") == agent.environment_id

    def test_metadata_survives_restart(self):
        """Metadata can be restored from session store after 'restart'."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        # Phase 1: Create and persist
        agent1 = _make_local_managed(session_store=store)
        with patch("praisonaiagents.Agent") as MockAgent:
            MockAgent.return_value = MagicMock()
            agent1._ensure_agent()
            agent1._ensure_session()

        saved_ids = agent1.save_ids()
        original_agent_id = agent1.agent_id
        original_version = agent1.agent_version
        original_env_id = agent1.environment_id

        # Phase 2: Simulate restart — new instance, same store
        store2 = DefaultSessionStore(session_dir=session_dir)
        agent2 = _make_local_managed(session_store=store2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        assert agent2.agent_id == original_agent_id
        assert agent2.agent_version == original_version
        assert agent2.environment_id == original_env_id


# ===========================================================================
# 3. Usage token persistence
# ===========================================================================

class TestUsageTokenPersistence:
    """Usage tokens survive restarts."""

    def test_usage_persisted_after_execute(self):
        """After execute, usage tokens are written to session store metadata."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)

        mock_inner = MagicMock()
        mock_inner.chat.return_value = "Hello!"
        mock_inner._total_tokens_in = 42
        mock_inner._total_tokens_out = 17

        with patch("praisonaiagents.Agent", return_value=mock_inner):
            agent._execute_sync("Hi")

        # Verify usage in store
        session = store.get_session(agent.session_id)
        assert session is not None
        meta = session.metadata
        assert meta.get("total_input_tokens") == 42
        assert meta.get("total_output_tokens") == 17

    def test_usage_restored_on_resume(self):
        """Usage tokens are restored when resuming a session."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)
        mock_inner = MagicMock()
        mock_inner.chat.return_value = "Hello!"
        mock_inner._total_tokens_in = 100
        mock_inner._total_tokens_out = 50

        with patch("praisonaiagents.Agent", return_value=mock_inner):
            agent._execute_sync("Hi")

        saved_ids = agent.save_ids()

        # Simulate restart
        store2 = DefaultSessionStore(session_dir=session_dir)
        agent2 = _make_local_managed(session_store=store2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        assert agent2.total_input_tokens == 100
        assert agent2.total_output_tokens == 50


# ===========================================================================
# 4. Session history persistence
# ===========================================================================

class TestSessionHistoryPersistence:
    """Session history list survives restarts."""

    def test_session_history_persisted(self):
        """Session history entries are written to store metadata."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)
        with patch("praisonaiagents.Agent") as MockAgent:
            MockAgent.return_value = MagicMock()
            agent._ensure_agent()
            agent._ensure_session()

        session = store.get_session(agent.session_id)
        meta = session.metadata
        assert "session_history" in meta
        assert len(meta["session_history"]) >= 1
        assert meta["session_history"][0]["id"] == agent.session_id

    def test_session_history_restored(self):
        """Session history is restored on resume."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)
        with patch("praisonaiagents.Agent") as MockAgent:
            MockAgent.return_value = MagicMock()
            agent._ensure_agent()
            agent._ensure_session()

        saved_ids = agent.save_ids()
        original_history = list(agent._session_history)

        store2 = DefaultSessionStore(session_dir=session_dir)
        agent2 = _make_local_managed(session_store=store2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        assert len(agent2._session_history) == len(original_history)


# ===========================================================================
# 5. Compute instance ref persistence
# ===========================================================================

class TestComputeInstanceRefPersistence:
    """Compute instance references survive restarts."""

    def test_compute_ref_persisted(self):
        """Compute instance ID is stored in session metadata."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)
        with patch("praisonaiagents.Agent") as MockAgent:
            MockAgent.return_value = MagicMock()
            agent._ensure_agent()
            agent._ensure_session()

        # Simulate compute provisioning
        agent._compute_instance_id = "docker_abc123"
        agent._persist_state()

        session = store.get_session(agent.session_id)
        meta = session.metadata
        assert meta.get("compute_instance_id") == "docker_abc123"

    def test_compute_ref_restored(self):
        """Compute instance ID is restored on resume."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore
        store = DefaultSessionStore(session_dir=session_dir)

        agent = _make_local_managed(session_store=store)
        with patch("praisonaiagents.Agent") as MockAgent:
            MockAgent.return_value = MagicMock()
            agent._ensure_agent()
            agent._ensure_session()

        agent._compute_instance_id = "e2b_xyz789"
        agent._persist_state()
        saved_ids = agent.save_ids()

        store2 = DefaultSessionStore(session_dir=session_dir)
        agent2 = _make_local_managed(session_store=store2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        assert agent2._compute_instance_id == "e2b_xyz789"


# ===========================================================================
# 6. DbSessionAdapter tests
# ===========================================================================

class TestDbSessionAdapter:
    """DbSessionAdapter bridges PraisonDB/ConversationStore → SessionStoreProtocol."""

    def test_adapter_satisfies_protocol(self):
        """DbSessionAdapter implements SessionStoreProtocol."""
        from praisonai.integrations.db_session_adapter import DbSessionAdapter
        from praisonaiagents.session.protocols import SessionStoreProtocol

        mock_db = MagicMock()
        adapter = DbSessionAdapter(mock_db)
        assert isinstance(adapter, SessionStoreProtocol)

    def test_add_message_delegates_to_db(self):
        """add_message calls db.on_user_message or db.on_agent_message."""
        from praisonai.integrations.db_session_adapter import DbSessionAdapter

        mock_db = MagicMock()
        adapter = DbSessionAdapter(mock_db)
        adapter.add_message("sess1", "user", "Hello")
        mock_db.on_user_message.assert_called_once()

    def test_get_chat_history_delegates_to_db(self):
        """get_chat_history retrieves from db."""
        from praisonai.integrations.db_session_adapter import DbSessionAdapter
        from praisonaiagents.db.protocol import DbMessage

        mock_db = MagicMock()
        mock_db.on_agent_start.return_value = [
            DbMessage(role="user", content="Hi"),
            DbMessage(role="assistant", content="Hello!"),
        ]
        adapter = DbSessionAdapter(mock_db)
        # Trigger init
        adapter._ensure_session("sess1", "TestAgent")
        history = adapter.get_chat_history("sess1")
        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_session_exists(self):
        """session_exists checks via db."""
        from praisonai.integrations.db_session_adapter import DbSessionAdapter

        mock_db = MagicMock()
        adapter = DbSessionAdapter(mock_db)
        adapter._sessions.add("sess1")
        assert adapter.session_exists("sess1") is True
        assert adapter.session_exists("nonexistent") is False

    def test_metadata_roundtrip(self):
        """set_metadata / get_metadata work for agent state."""
        from praisonai.integrations.db_session_adapter import DbSessionAdapter

        mock_db = MagicMock()
        adapter = DbSessionAdapter(mock_db)
        adapter.set_metadata("sess1", {"agent_id": "abc", "total_input_tokens": 42})
        meta = adapter.get_metadata("sess1")
        assert meta["agent_id"] == "abc"
        assert meta["total_input_tokens"] == 42


# ===========================================================================
# 7. ManagedAgent factory wiring
# ===========================================================================

class TestManagedAgentFactoryDb:
    """ManagedAgent factory passes db= through to LocalManagedAgent."""

    def test_factory_passes_db(self):
        """ManagedAgent(db=...) creates LocalManagedAgent with db adapter."""
        mock_db = MagicMock()
        with patch.dict(os.environ, {}, clear=False):
            # Remove anthropic key to force local
            env = dict(os.environ)
            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("CLAUDE_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                from praisonai.integrations.managed_agents import ManagedAgent
                managed = ManagedAgent(provider="local", db=mock_db)
                store = managed._get_session_store()
                assert store is not None


# ===========================================================================
# 8. Full round-trip: file store
# ===========================================================================

class TestFullRoundTripFileStore:
    """Full save → destroy → restore cycle with file store."""

    def test_full_roundtrip(self):
        """All 7 data categories survive a simulated restart."""
        session_dir = _make_temp_session_dir()
        from praisonaiagents.session.store import DefaultSessionStore

        # Phase 1: Create agent, run, accumulate state
        store1 = DefaultSessionStore(session_dir=session_dir)
        agent1 = _make_local_managed(session_store=store1)

        mock_inner = MagicMock()
        mock_inner.chat.return_value = "I computed 42."
        mock_inner._total_tokens_in = 200
        mock_inner._total_tokens_out = 100
        mock_inner.chat_history = []

        with patch("praisonaiagents.Agent", return_value=mock_inner):
            agent1._execute_sync("What is 6*7?")

        agent1._compute_instance_id = "docker_test123"
        agent1._persist_state()

        # Save everything we need to restore
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

        # Phase 2: Destroy agent (simulate process exit)
        del agent1

        # Phase 3: Restore from same session dir
        store2 = DefaultSessionStore(session_dir=session_dir)
        agent2 = _make_local_managed(session_store=store2)
        agent2.restore_ids(saved_ids)
        agent2.resume_session(saved_ids["session_id"])

        # Verify all 7 categories
        assert agent2.agent_id == original["agent_id"], "D1: agent_id"
        assert agent2.agent_version == original["agent_version"], "D1: agent_version"
        assert agent2.environment_id == original["environment_id"], "D1: environment_id"
        assert agent2.session_id == original["session_id"], "D2: session_id"
        assert len(agent2._session_history) == original["session_history_len"], "D3: session_history"
        assert agent2.total_input_tokens == original["total_input_tokens"], "D5: input_tokens"
        assert agent2.total_output_tokens == original["total_output_tokens"], "D5: output_tokens"
        assert agent2._compute_instance_id == original["compute_instance_id"], "D6: compute ref"

        # D4: Chat messages (already verified by existing session store tests)
        history = store2.get_chat_history(agent2.session_id)
        assert len(history) >= 2  # user + assistant
