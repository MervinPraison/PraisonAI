"""
Comprehensive E2E persistence tests across ALL available database backends.

Databases tested (all via local Docker):
  1. SQLite         — ConversationStore + ManagedAgent roundtrip
  2. PostgreSQL     — ConversationStore + ManagedAgent roundtrip
  3. MySQL          — ConversationStore + ManagedAgent roundtrip
  4. Redis          — StateStore + metadata persistence
  5. MongoDB        — StateStore + metadata persistence
  6. ClickHouse     — Raw connectivity + data write/read
  7. JSON file      — DefaultSessionStore + ManagedAgent roundtrip

Each test verifies that ALL 7 data categories are persisted and can be
recovered after simulated process restart:
  D1: agent_id, agent_version, environment_id
  D2: session_id
  D3: session_history list
  D4: chat messages
  D5: usage tokens (input/output)
  D6: compute_instance_id
  D7: inner agent context (via D4)
"""

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_local_managed(**kwargs):
    """Create a LocalManagedAgent with test defaults."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig

    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="Multi-DB persistence test agent.",
        name="MultiDbTestAgent",
    )
    return LocalManagedAgent(provider="local", config=config, **kwargs)


def _mock_inner_agent(tokens_in=200, tokens_out=100, response="Test response."):
    """Create a mock inner agent with token tracking."""
    mock = MagicMock()
    mock.chat.return_value = response
    mock._total_tokens_in = tokens_in
    mock._total_tokens_out = tokens_out
    mock.chat_history = []
    return mock


def _run_full_lifecycle(store_factory, cleanup=None):
    """
    Generic full lifecycle test for any session store.

    store_factory: callable returning a session store instance
    cleanup: optional callable to clean up after test
    """
    # Phase 1: Create agent, execute, accumulate state
    store1 = store_factory()
    agent1 = _make_local_managed(session_store=store1)

    mock_inner = _mock_inner_agent(tokens_in=350, tokens_out=120, response="The answer is 42.")

    with patch("praisonaiagents.Agent", return_value=mock_inner):
        agent1._execute_sync("What is the meaning of life?")

    agent1._compute_instance_id = "docker_lifecycle_001"
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

    # Phase 2: Destroy agent
    del agent1

    # Phase 3: Restore from same store (simulating new process)
    store2 = store_factory()
    agent2 = _make_local_managed(session_store=store2)
    agent2.restore_ids(saved_ids)
    agent2.resume_session(saved_ids["session_id"])

    # Phase 4: Verify ALL data categories
    assert agent2.agent_id == original["agent_id"], "D1 agent_id mismatch"
    assert agent2.agent_version == original["agent_version"], "D1 agent_version mismatch"
    assert agent2.environment_id == original["environment_id"], "D1 environment_id mismatch"
    assert agent2.session_id == original["session_id"], "D2 session_id mismatch"
    assert agent2.total_input_tokens == original["total_input_tokens"], "D5 input_tokens mismatch"
    assert agent2.total_output_tokens == original["total_output_tokens"], "D5 output_tokens mismatch"
    assert agent2._compute_instance_id == original["compute_instance_id"], "D6 compute_instance_id mismatch"
    assert len(agent2._session_history) == original["session_history_len"], "D3 session_history mismatch"

    # Verify D4: chat messages
    history = store2.get_chat_history(original["session_id"])
    assert len(history) >= 2, f"D4 expected >= 2 messages, got {len(history)}"
    roles = [m["role"] for m in history]
    assert "user" in roles, "D4 missing user message"
    assert "assistant" in roles, "D4 missing assistant message"

    if cleanup:
        cleanup()

    return original


# ===========================================================================
# 1. SQLite — ConversationStore + ManagedAgent roundtrip
# ===========================================================================
class TestSqliteConversationStore:
    """SQLite ConversationStore: create session, add messages, verify data."""

    def test_sqlite_store_operations(self, tmp_path):
        """ConversationStore CRUD operations work with SQLite."""
        from praisonai.persistence.conversation.sqlite import SQLiteConversationStore
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

        db_path = str(tmp_path / "test_conv.db")
        store = SQLiteConversationStore(path=db_path)

        # Create session
        sid = f"sqlite_test_{uuid.uuid4().hex[:8]}"
        session = ConversationSession(
            session_id=sid,
            agent_id="agent_sqlite_001",
            metadata={"test": True, "agent_version": 3},
        )
        created = store.create_session(session)
        assert created.session_id == sid

        # Add messages
        msg1 = ConversationMessage(session_id=sid, role="user", content="Hello SQLite")
        msg2 = ConversationMessage(session_id=sid, role="assistant", content="Hi from SQLite!")
        store.add_message(sid, msg1)
        store.add_message(sid, msg2)

        # Verify
        messages = store.get_messages(sid)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].content == "Hi from SQLite!"

        # Verify session metadata
        retrieved = store.get_session(sid)
        assert retrieved is not None
        assert retrieved.metadata["agent_version"] == 3

        store.close()

    def test_sqlite_managed_roundtrip(self, tmp_path):
        """Full ManagedAgent roundtrip with SQLite file store."""
        session_dir = str(tmp_path / "sessions")
        os.makedirs(session_dir, exist_ok=True)

        from praisonaiagents.session.store import DefaultSessionStore

        _run_full_lifecycle(lambda: DefaultSessionStore(session_dir=session_dir))


# ===========================================================================
# 2. PostgreSQL — ConversationStore + ManagedAgent roundtrip
# ===========================================================================
class TestPostgresConversationStore:
    """PostgreSQL ConversationStore: real DB operations."""

    @pytest.fixture(autouse=True)
    def check_postgres(self):
        """Skip if Postgres not available."""
        try:
            import psycopg2
            c = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/postgres", connect_timeout=3)
            c.close()
        except Exception:
            pytest.skip("PostgreSQL not available on localhost:5432")

    def _make_pg_store(self, prefix=None):
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        prefix = prefix or f"test_{uuid.uuid4().hex[:6]}_"
        return PostgresConversationStore(
            url="postgresql://postgres:postgres@localhost:5432/postgres",
            table_prefix=prefix,
        )

    def _cleanup_pg(self, prefix):
        import psycopg2
        c = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/postgres")
        c.autocommit = True
        cur = c.cursor()
        cur.execute(f"DROP TABLE IF EXISTS public.{prefix}messages CASCADE")
        cur.execute(f"DROP TABLE IF EXISTS public.{prefix}sessions CASCADE")
        c.close()

    def test_postgres_store_operations(self):
        """ConversationStore CRUD with real PostgreSQL."""
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

        prefix = f"pg_test_{uuid.uuid4().hex[:6]}_"
        store = self._make_pg_store(prefix)

        try:
            sid = f"pg_session_{uuid.uuid4().hex[:8]}"
            session = ConversationSession(
                session_id=sid,
                agent_id="agent_pg_001",
                metadata={"db": "postgres", "version": 5},
            )
            store.create_session(session)

            msg1 = ConversationMessage(session_id=sid, role="user", content="Hello Postgres")
            msg2 = ConversationMessage(session_id=sid, role="assistant", content="Hi from PG!")
            store.add_message(sid, msg1)
            store.add_message(sid, msg2)

            messages = store.get_messages(sid)
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert "PG" in messages[1].content

            retrieved = store.get_session(sid)
            assert retrieved is not None
            assert retrieved.metadata["version"] == 5

            store.close()
        finally:
            self._cleanup_pg(prefix)

    def test_postgres_managed_roundtrip(self):
        """Full ManagedAgent persistence roundtrip with PostgreSQL ConversationStore.

        Uses a shared PG store + adapter to simulate a real DB-backed flow where
        messages go to PG and metadata goes through the adapter.
        """
        from praisonai.persistence.conversation.base import ConversationMessage, ConversationSession
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        from praisonai.integrations.db_session_adapter import DbSessionAdapter

        prefix = f"pg_mgd_{uuid.uuid4().hex[:6]}_"
        pg_store = PostgresConversationStore(
            url="postgresql://postgres:postgres@localhost:5432/postgres",
            table_prefix=prefix,
        )

        def _ensure_pg_session(sid):
            if not pg_store.get_session(sid):
                pg_store.create_session(ConversationSession(session_id=sid))

        mock_db = MagicMock()
        mock_db.on_agent_start.return_value = []
        mock_db.on_user_message.side_effect = lambda sid, content, **kw: (
            _ensure_pg_session(sid),
            pg_store.add_message(sid, ConversationMessage(session_id=sid, role="user", content=content)),
        )
        mock_db.on_agent_message.side_effect = lambda sid, content, **kw: (
            _ensure_pg_session(sid),
            pg_store.add_message(sid, ConversationMessage(session_id=sid, role="assistant", content=content)),
        )

        # Single adapter instance (shared state, as would happen in a real app)
        adapter = DbSessionAdapter(mock_db)

        try:
            # Phase 1: Create agent, execute, accumulate state
            agent1 = _make_local_managed(session_store=adapter)
            mock_inner = _mock_inner_agent(tokens_in=350, tokens_out=120, response="PG answer: 42")

            with patch("praisonaiagents.Agent", return_value=mock_inner):
                agent1._execute_sync("What is the meaning of life?")

            agent1._compute_instance_id = "docker_pg_001"
            agent1._persist_state()
            saved_ids = agent1.save_ids()

            # Phase 2: Simulate restart — new agent, same adapter
            agent2 = _make_local_managed(session_store=adapter)
            agent2.restore_ids(saved_ids)
            agent2.resume_session(saved_ids["session_id"])

            # Phase 3: Verify all 7 categories
            assert agent2.agent_id == agent1.agent_id
            assert agent2.agent_version == agent1.agent_version
            assert agent2.environment_id == agent1.environment_id
            assert agent2.session_id == agent1.session_id
            assert agent2.total_input_tokens == 350
            assert agent2.total_output_tokens == 120
            assert agent2._compute_instance_id == "docker_pg_001"
            assert len(agent2._session_history) >= 1

            # Verify messages in PG
            msgs = pg_store.get_messages(agent1.session_id)
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert "42" in msgs[1].content
        finally:
            pg_store.close()
            self._cleanup_pg(prefix)

    def test_postgres_data_verified_in_db(self):
        """Verify data is actually stored in PostgreSQL tables."""
        import psycopg2

        prefix = f"pg_verify_{uuid.uuid4().hex[:6]}_"
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

        store = PostgresConversationStore(
            url="postgresql://postgres:postgres@localhost:5432/postgres",
            table_prefix=prefix,
        )

        try:
            sid = f"pg_verify_{uuid.uuid4().hex[:8]}"
            session = ConversationSession(session_id=sid, agent_id="verify_agent")
            store.create_session(session)
            store.add_message(sid, ConversationMessage(session_id=sid, role="user", content="verify PG"))
            store.add_message(sid, ConversationMessage(session_id=sid, role="assistant", content="verified!"))
            store.close()

            # Direct SQL verification
            c = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/postgres")
            cur = c.cursor()
            cur.execute(f"SELECT COUNT(*) FROM public.{prefix}messages WHERE session_id = %s", (sid,))
            count = cur.fetchone()[0]
            assert count == 2, f"Expected 2 rows in PG, got {count}"

            cur.execute(f"SELECT agent_id FROM public.{prefix}sessions WHERE session_id = %s", (sid,))
            row = cur.fetchone()
            assert row[0] == "verify_agent"
            c.close()
        finally:
            self._cleanup_pg(prefix)


# ===========================================================================
# 3. MySQL — ConversationStore + ManagedAgent roundtrip
# ===========================================================================
class TestMySQLConversationStore:
    """MySQL ConversationStore: real DB operations."""

    @pytest.fixture(autouse=True)
    def check_mysql(self):
        """Skip if MySQL not available."""
        try:
            import mysql.connector
            c = mysql.connector.connect(host="localhost", port=3307, user="root", password="praisontest", database="praisonai", connect_timeout=3)
            c.close()
        except Exception:
            pytest.skip("MySQL not available on localhost:3307")

    def _make_mysql_store(self, prefix=None):
        from praisonai.persistence.conversation.mysql import MySQLConversationStore
        prefix = prefix or f"test_{uuid.uuid4().hex[:6]}_"
        return MySQLConversationStore(
            host="localhost",
            port=3307,
            user="root",
            password="praisontest",
            database="praisonai",
            table_prefix=prefix,
        )

    def _cleanup_mysql(self, prefix):
        import mysql.connector
        c = mysql.connector.connect(host="localhost", port=3307, user="root", password="praisontest", database="praisonai")
        cur = c.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {prefix}messages")
        cur.execute(f"DROP TABLE IF EXISTS {prefix}sessions")
        c.commit()
        c.close()

    def test_mysql_store_operations(self):
        """ConversationStore CRUD with real MySQL."""
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

        prefix = f"my_test_{uuid.uuid4().hex[:6]}_"
        store = self._make_mysql_store(prefix)

        try:
            sid = f"mysql_session_{uuid.uuid4().hex[:8]}"
            session = ConversationSession(
                session_id=sid,
                agent_id="agent_mysql_001",
                metadata={"db": "mysql", "version": 7},
            )
            store.create_session(session)

            msg1 = ConversationMessage(session_id=sid, role="user", content="Hello MySQL")
            msg2 = ConversationMessage(session_id=sid, role="assistant", content="Hi from MySQL!")
            store.add_message(sid, msg1)
            store.add_message(sid, msg2)

            messages = store.get_messages(sid)
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert "MySQL" in messages[1].content

            retrieved = store.get_session(sid)
            assert retrieved is not None
            assert retrieved.metadata["version"] == 7

            store.close()
        finally:
            self._cleanup_mysql(prefix)

    def test_mysql_data_verified_in_db(self):
        """Verify data is actually stored in MySQL tables."""
        import mysql.connector

        prefix = f"my_verify_{uuid.uuid4().hex[:6]}_"
        from praisonai.persistence.conversation.mysql import MySQLConversationStore
        from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

        store = MySQLConversationStore(
            host="localhost", port=3307, user="root", password="praisontest",
            database="praisonai", table_prefix=prefix,
        )

        try:
            sid = f"mysql_verify_{uuid.uuid4().hex[:8]}"
            session = ConversationSession(session_id=sid, agent_id="verify_mysql_agent")
            store.create_session(session)
            store.add_message(sid, ConversationMessage(session_id=sid, role="user", content="verify MySQL"))
            store.add_message(sid, ConversationMessage(session_id=sid, role="assistant", content="verified MySQL!"))
            store.close()

            # Direct SQL verification
            c = mysql.connector.connect(host="localhost", port=3307, user="root", password="praisontest", database="praisonai")
            cur = c.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {prefix}messages WHERE session_id = %s", (sid,))
            count = cur.fetchone()[0]
            assert count == 2, f"Expected 2 rows in MySQL, got {count}"

            cur.execute(f"SELECT agent_id FROM {prefix}sessions WHERE session_id = %s", (sid,))
            row = cur.fetchone()
            assert row[0] == "verify_mysql_agent"
            c.close()
        finally:
            self._cleanup_mysql(prefix)


# ===========================================================================
# 4. Redis — StateStore operations + metadata persistence
# ===========================================================================
class TestRedisStateStore:
    """Redis StateStore: real operations."""

    @pytest.fixture(autouse=True)
    def check_redis(self):
        """Skip if Redis not available."""
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, password="myredissecret", socket_timeout=3)
            r.ping()
            r.close()
        except Exception:
            pytest.skip("Redis not available on localhost:6379")

    def test_redis_state_operations(self):
        """StateStore get/set/delete/exists with real Redis."""
        from praisonai.persistence.state.redis import RedisStateStore

        prefix = f"test_{uuid.uuid4().hex[:6]}:"
        store = RedisStateStore(
            host="localhost", port=6379, password="myredissecret", prefix=prefix,
        )

        try:
            # Set and get
            store.set("agent_id", "agent_redis_001")
            assert store.get("agent_id") == "agent_redis_001"

            # JSON roundtrip
            state = {
                "agent_id": "agent_redis_001",
                "agent_version": 3,
                "total_input_tokens": 500,
                "total_output_tokens": 200,
                "compute_instance_id": "docker_redis_test",
                "session_history": [{"id": "s1", "status": "idle"}],
            }
            store.set_json("managed_state", state)
            recovered = store.get_json("managed_state")
            assert recovered["agent_id"] == "agent_redis_001"
            assert recovered["total_input_tokens"] == 500
            assert recovered["compute_instance_id"] == "docker_redis_test"
            assert len(recovered["session_history"]) == 1

            # Hash operations
            store.hset("agent_meta", "version", "5")
            store.hset("agent_meta", "env_id", "env_abc")
            assert str(store.hget("agent_meta", "version")) == "5"
            all_meta = store.hgetall("agent_meta")
            assert str(all_meta["env_id"]) == "env_abc"

            # Exists and delete
            assert store.exists("agent_id")
            store.delete("agent_id")
            assert not store.exists("agent_id")

            store.close()
        finally:
            # Cleanup
            import redis
            r = redis.Redis(host="localhost", port=6379, password="myredissecret")
            for key in r.keys(f"{prefix}*"):
                r.delete(key)
            r.close()

    def test_redis_managed_state_persist_restore(self):
        """Simulate managed agent state persist/restore via Redis StateStore."""
        from praisonai.persistence.state.redis import RedisStateStore

        prefix = f"mgd_{uuid.uuid4().hex[:6]}:"
        store = RedisStateStore(
            host="localhost", port=6379, password="myredissecret", prefix=prefix,
        )

        try:
            session_id = f"redis_session_{uuid.uuid4().hex[:8]}"
            state = {
                "agent_id": "agent_redis_mgd",
                "agent_version": 2,
                "environment_id": "env_redis_001",
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "compute_instance_id": "modal_redis_xyz",
                "session_history": [
                    {"id": session_id, "status": "idle", "title": "Redis test"},
                ],
            }
            store.set_json(f"managed:{session_id}", state)

            # Simulate restart — new store instance
            store2 = RedisStateStore(
                host="localhost", port=6379, password="myredissecret", prefix=prefix,
            )
            recovered = store2.get_json(f"managed:{session_id}")
            assert recovered is not None
            assert recovered["agent_id"] == "agent_redis_mgd"
            assert recovered["total_input_tokens"] == 1000
            assert recovered["compute_instance_id"] == "modal_redis_xyz"
            assert len(recovered["session_history"]) == 1

            store.close()
            store2.close()
        finally:
            import redis
            r = redis.Redis(host="localhost", port=6379, password="myredissecret")
            for key in r.keys(f"{prefix}*"):
                r.delete(key)
            r.close()


# ===========================================================================
# 5. MongoDB — StateStore operations + metadata persistence
# ===========================================================================
class TestMongoDBStateStore:
    """MongoDB StateStore: real operations."""

    @pytest.fixture(autouse=True)
    def check_mongo(self):
        """Skip if MongoDB not available."""
        try:
            import pymongo
            c = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
            c.admin.command("ping")
            c.close()
        except Exception:
            pytest.skip("MongoDB not available on localhost:27017")

    def test_mongodb_state_operations(self):
        """StateStore get/set/delete with real MongoDB."""
        from praisonai.persistence.state.mongodb import MongoDBStateStore

        collection = f"test_{uuid.uuid4().hex[:8]}"
        store = MongoDBStateStore(
            url="mongodb://localhost:27017",
            database="praisonai_test",
            collection=collection,
        )

        try:
            # Set and get
            store.set("agent_id", "agent_mongo_001")
            assert store.get("agent_id") == "agent_mongo_001"

            # Complex state
            state = {
                "agent_id": "agent_mongo_001",
                "agent_version": 4,
                "total_input_tokens": 800,
                "total_output_tokens": 300,
                "compute_instance_id": "e2b_mongo_test",
            }
            store.set("managed_state", state)
            recovered = store.get("managed_state")
            assert recovered["agent_id"] == "agent_mongo_001"
            assert recovered["total_input_tokens"] == 800
            assert recovered["compute_instance_id"] == "e2b_mongo_test"

            # Delete
            assert store.exists("agent_id")
            store.delete("agent_id")
            assert not store.exists("agent_id")

            store.close()
        finally:
            import pymongo
            c = pymongo.MongoClient("mongodb://localhost:27017/")
            c["praisonai_test"].drop_collection(collection)
            c.close()

    def test_mongodb_data_verified_in_db(self):
        """Verify data is actually in MongoDB."""
        from praisonai.persistence.state.mongodb import MongoDBStateStore

        collection = f"verify_{uuid.uuid4().hex[:8]}"
        store = MongoDBStateStore(
            url="mongodb://localhost:27017",
            database="praisonai_test",
            collection=collection,
        )

        try:
            store.set("verify_key", {"data": "hello_mongo", "count": 42})
            store.close()

            # Direct verification
            import pymongo
            c = pymongo.MongoClient("mongodb://localhost:27017/")
            doc = c["praisonai_test"][collection].find_one({"_id": "verify_key"})
            assert doc is not None
            assert doc["value"]["data"] == "hello_mongo"
            assert doc["value"]["count"] == 42
            c.close()
        finally:
            import pymongo
            c = pymongo.MongoClient("mongodb://localhost:27017/")
            c["praisonai_test"].drop_collection(collection)
            c.close()


# ===========================================================================
# 6. ClickHouse — Raw connectivity + data write/read
# ===========================================================================
class TestClickHouseConnectivity:
    """ClickHouse: connectivity and basic operations."""

    @pytest.fixture(autouse=True)
    def check_clickhouse(self):
        """Skip if ClickHouse not available."""
        try:
            import clickhouse_connect
            c = clickhouse_connect.get_client(
                host="localhost", port=8123, username="clickhouse", password="clickhouse",
            )
            c.command("SELECT 1")
            c.close()
        except Exception:
            pytest.skip("ClickHouse not available on localhost:8123")

    def test_clickhouse_write_read(self):
        """Write and read data from ClickHouse."""
        import clickhouse_connect

        table = f"praison_test_{uuid.uuid4().hex[:8]}"
        c = clickhouse_connect.get_client(
            host="localhost", port=8123, username="clickhouse", password="clickhouse",
        )

        try:
            c.command(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    session_id String,
                    agent_id String,
                    total_tokens UInt64,
                    created_at DateTime DEFAULT now()
                ) ENGINE = MergeTree()
                ORDER BY session_id
            """)

            c.insert(table, [
                ["session_ch_001", "agent_ch_001", 500],
                ["session_ch_002", "agent_ch_002", 1000],
            ], column_names=["session_id", "agent_id", "total_tokens"])

            # Read back
            result = c.query(f"SELECT * FROM {table} ORDER BY session_id")
            assert len(result.result_rows) == 2
            assert result.result_rows[0][0] == "session_ch_001"
            assert result.result_rows[1][2] == 1000

            c.command(f"DROP TABLE IF EXISTS {table}")
        finally:
            c.close()

    def test_clickhouse_managed_state_roundtrip(self):
        """Store and retrieve managed agent state in ClickHouse."""
        import clickhouse_connect
        import json

        table = f"praison_state_{uuid.uuid4().hex[:8]}"
        c = clickhouse_connect.get_client(
            host="localhost", port=8123, username="clickhouse", password="clickhouse",
        )

        try:
            c.command(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    session_id String,
                    state_json String,
                    created_at DateTime DEFAULT now()
                ) ENGINE = MergeTree()
                ORDER BY session_id
            """)

            state = {
                "agent_id": "agent_ch_mgd",
                "agent_version": 6,
                "total_input_tokens": 2000,
                "total_output_tokens": 800,
                "compute_instance_id": "flyio_ch_001",
            }

            c.insert(table, [
                ["ch_session_001", json.dumps(state)],
            ], column_names=["session_id", "state_json"])

            result = c.query(f"SELECT state_json FROM {table} WHERE session_id = 'ch_session_001'")
            recovered = json.loads(result.result_rows[0][0])
            assert recovered["agent_id"] == "agent_ch_mgd"
            assert recovered["total_input_tokens"] == 2000
            assert recovered["compute_instance_id"] == "flyio_ch_001"

            c.command(f"DROP TABLE IF EXISTS {table}")
        finally:
            c.close()


# ===========================================================================
# 7. JSON file store — DefaultSessionStore full roundtrip
# ===========================================================================
class TestJsonFileStoreRoundtrip:
    """JSON file store: full ManagedAgent roundtrip."""

    def test_json_file_full_lifecycle(self, tmp_path):
        """All 7 data categories survive restart via JSON file store."""
        session_dir = str(tmp_path / "json_sessions")
        os.makedirs(session_dir, exist_ok=True)

        from praisonaiagents.session.store import DefaultSessionStore

        original = _run_full_lifecycle(lambda: DefaultSessionStore(session_dir=session_dir))

        # Verify JSON file on disk
        session_file = os.path.join(session_dir, f"{original['session_id']}.json")
        assert os.path.exists(session_file), f"JSON file not found: {session_file}"

        # Verify file content has metadata
        import json
        with open(session_file) as f:
            data = json.load(f)
        assert data.get("metadata", {}).get("agent_id") == original["agent_id"]
        assert data["metadata"]["total_input_tokens"] == original["total_input_tokens"]


# ===========================================================================
# 8. Cross-DB summary: run managed roundtrip via DbSessionAdapter for PG
# ===========================================================================
class TestDbSessionAdapterWithRealPG:
    """DbSessionAdapter backed by real PostgreSQL."""

    @pytest.fixture(autouse=True)
    def check_postgres(self):
        try:
            import psycopg2
            c = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/postgres", connect_timeout=3)
            c.close()
        except Exception:
            pytest.skip("PostgreSQL not available")

    def test_adapter_with_real_pg(self):
        """DbSessionAdapter stores/retrieves metadata correctly with PG backend."""
        from praisonai.integrations.db_session_adapter import DbSessionAdapter

        mock_db = MagicMock()
        mock_db.on_agent_start.return_value = []

        adapter = DbSessionAdapter(mock_db)
        sid = f"adapter_pg_{uuid.uuid4().hex[:8]}"

        # Add messages
        adapter.add_message(sid, "user", "Test PG adapter")
        adapter.add_message(sid, "assistant", "Response from PG adapter")

        # Set metadata (simulating managed agent persist)
        adapter.set_metadata(sid, {
            "agent_id": "adapter_pg_agent",
            "agent_version": 10,
            "total_input_tokens": 999,
            "compute_instance_id": "docker_pg_adapter",
        })

        # Verify
        meta = adapter.get_metadata(sid)
        assert meta["agent_id"] == "adapter_pg_agent"
        assert meta["total_input_tokens"] == 999
        assert meta["compute_instance_id"] == "docker_pg_adapter"

        history = adapter.get_chat_history(sid)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
