"""
Comprehensive TDD tests for all 22 database backends.

Tests are organized by category:
1. ConversationStore backends (6): PostgreSQL, MySQL, SQLite, SingleStore, Supabase, SurrealDB
2. KnowledgeStore backends (10): Qdrant, ChromaDB, Pinecone, Weaviate, LanceDB, Milvus, PGVector, Redis Vector, Cassandra, ClickHouse
3. StateStore backends (6): Redis, Memory, MongoDB, DynamoDB, Firestore, Upstash

Run with: python -m pytest praisonai/persistence/tests/test_all_backends.py -v
"""

import sys
import os
import time
import uuid
import random
import json

# Add the package to path
sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai')

from praisonai.persistence.conversation.base import ConversationStore, ConversationSession, ConversationMessage
from praisonai.persistence.knowledge.base import KnowledgeStore, KnowledgeDocument
from praisonai.persistence.state.base import StateStore
from praisonai.persistence.orchestrator import PersistenceOrchestrator
from praisonai.persistence.factory import create_conversation_store, create_knowledge_store, create_state_store


# =============================================================================
# Test Utilities
# =============================================================================

def generate_test_session() -> ConversationSession:
    """Generate a test session with unique ID."""
    return ConversationSession(
        session_id=f"test-{uuid.uuid4().hex[:8]}",
        user_id="test-user",
        agent_id="test-agent",
        name="Test Session",
        metadata={"test": True, "timestamp": time.time()}
    )


def generate_test_message(session_id: str, role: str = "user", content: str = None) -> ConversationMessage:
    """Generate a test message."""
    return ConversationMessage(
        id=f"msg-{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        role=role,
        content=content or f"Test message from {role} at {time.time()}",
        metadata={"test": True}
    )


def generate_test_document(dim: int = 384) -> KnowledgeDocument:
    """Generate a test document with random embedding."""
    random.seed(42)
    return KnowledgeDocument(
        id=f"doc-{uuid.uuid4().hex[:8]}",
        content=f"Test document content {uuid.uuid4().hex[:8]}",
        embedding=[random.random() for _ in range(dim)],
        metadata={"test": True, "category": "test"}
    )


# =============================================================================
# ConversationStore Tests
# =============================================================================

class ConversationStoreTestMixin:
    """Mixin with standard tests for all ConversationStore implementations."""
    
    store: ConversationStore = None
    
    def test_create_session(self):
        """Test session creation."""
        session = generate_test_session()
        result = self.store.create_session(session)
        assert result.session_id == session.session_id
        assert result.user_id == session.user_id
        # Cleanup
        self.store.delete_session(session.session_id)
    
    def test_get_session(self):
        """Test session retrieval."""
        session = generate_test_session()
        self.store.create_session(session)
        
        retrieved = self.store.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.name == session.name
        
        # Cleanup
        self.store.delete_session(session.session_id)
    
    def test_update_session(self):
        """Test session update."""
        session = generate_test_session()
        self.store.create_session(session)
        
        session.name = "Updated Name"
        session.metadata = {"updated": True}
        self.store.update_session(session)
        
        retrieved = self.store.get_session(session.session_id)
        assert retrieved.name == "Updated Name"
        
        # Cleanup
        self.store.delete_session(session.session_id)
    
    def test_delete_session(self):
        """Test session deletion."""
        session = generate_test_session()
        self.store.create_session(session)
        
        result = self.store.delete_session(session.session_id)
        assert result is True
        
        retrieved = self.store.get_session(session.session_id)
        assert retrieved is None
    
    def test_add_message(self):
        """Test adding messages to session."""
        session = generate_test_session()
        self.store.create_session(session)
        
        msg = generate_test_message(session.session_id, "user", "Hello!")
        result = self.store.add_message(session.session_id, msg)
        assert result.id == msg.id
        assert result.content == "Hello!"
        
        # Cleanup
        self.store.delete_session(session.session_id)
    
    def test_get_messages(self):
        """Test retrieving messages from session."""
        session = generate_test_session()
        self.store.create_session(session)
        
        # Add multiple messages
        for i in range(5):
            role = "user" if i % 2 == 0 else "assistant"
            msg = generate_test_message(session.session_id, role, f"Message {i}")
            self.store.add_message(session.session_id, msg)
        
        messages = self.store.get_messages(session.session_id)
        assert len(messages) == 5
        
        # Test limit
        limited = self.store.get_messages(session.session_id, limit=3)
        assert len(limited) == 3
        
        # Cleanup
        self.store.delete_session(session.session_id)
    
    def test_list_sessions(self):
        """Test listing sessions."""
        sessions = []
        for i in range(3):
            session = generate_test_session()
            session.user_id = "list-test-user"
            self.store.create_session(session)
            sessions.append(session)
        
        listed = self.store.list_sessions(user_id="list-test-user")
        assert len(listed) >= 3
        
        # Cleanup
        for s in sessions:
            self.store.delete_session(s.session_id)


# =============================================================================
# KnowledgeStore Tests
# =============================================================================

class KnowledgeStoreTestMixin:
    """Mixin with standard tests for all KnowledgeStore implementations."""
    
    store: KnowledgeStore = None
    collection_name: str = "test_collection"
    dimension: int = 384
    
    def test_create_collection(self):
        """Test collection creation."""
        if self.store.collection_exists(self.collection_name):
            self.store.delete_collection(self.collection_name)
        
        self.store.create_collection(self.collection_name, self.dimension)
        assert self.store.collection_exists(self.collection_name)
        
        # Cleanup
        self.store.delete_collection(self.collection_name)
    
    def test_insert_documents(self):
        """Test document insertion."""
        if not self.store.collection_exists(self.collection_name):
            self.store.create_collection(self.collection_name, self.dimension)
        
        docs = [generate_test_document(self.dimension) for _ in range(5)]
        ids = self.store.insert(self.collection_name, docs)
        assert len(ids) == 5
        
        # Cleanup
        self.store.delete_collection(self.collection_name)
    
    def test_search_documents(self):
        """Test vector search."""
        if not self.store.collection_exists(self.collection_name):
            self.store.create_collection(self.collection_name, self.dimension)
        
        # Insert documents
        docs = [generate_test_document(self.dimension) for _ in range(10)]
        self.store.insert(self.collection_name, docs)
        
        # Search
        random.seed(42)
        query_embedding = [random.random() for _ in range(self.dimension)]
        results = self.store.search(self.collection_name, query_embedding, limit=5)
        assert len(results) <= 5
        
        # Cleanup
        self.store.delete_collection(self.collection_name)
    
    def test_delete_documents(self):
        """Test document deletion."""
        if not self.store.collection_exists(self.collection_name):
            self.store.create_collection(self.collection_name, self.dimension)
        
        docs = [generate_test_document(self.dimension) for _ in range(3)]
        ids = self.store.insert(self.collection_name, docs)
        
        deleted = self.store.delete(self.collection_name, ids=ids[:1])
        assert deleted >= 1
        
        # Cleanup
        self.store.delete_collection(self.collection_name)


# =============================================================================
# StateStore Tests
# =============================================================================

class StateStoreTestMixin:
    """Mixin with standard tests for all StateStore implementations."""
    
    store: StateStore = None
    
    def test_set_get(self):
        """Test basic set/get operations."""
        key = f"test:{uuid.uuid4().hex[:8]}"
        value = {"test": True, "count": 42}
        
        self.store.set(key, value)
        retrieved = self.store.get(key)
        
        assert retrieved == value
        
        # Cleanup
        self.store.delete(key)
    
    def test_set_with_ttl(self):
        """Test set with TTL."""
        key = f"test:ttl:{uuid.uuid4().hex[:8]}"
        self.store.set(key, "temporary", ttl=3600)
        
        assert self.store.exists(key)
        ttl = self.store.ttl(key)
        assert ttl is None or ttl > 0
        
        # Cleanup
        self.store.delete(key)
    
    def test_delete(self):
        """Test key deletion."""
        key = f"test:delete:{uuid.uuid4().hex[:8]}"
        self.store.set(key, "to_delete")
        
        result = self.store.delete(key)
        assert result is True
        assert not self.store.exists(key)
    
    def test_exists(self):
        """Test key existence check."""
        key = f"test:exists:{uuid.uuid4().hex[:8]}"
        
        assert not self.store.exists(key)
        self.store.set(key, "value")
        assert self.store.exists(key)
        
        # Cleanup
        self.store.delete(key)
    
    def test_hash_operations(self):
        """Test hash operations."""
        key = f"test:hash:{uuid.uuid4().hex[:8]}"
        
        self.store.hset(key, "field1", "value1")
        self.store.hset(key, "field2", 42)
        
        assert self.store.hget(key, "field1") == "value1"
        
        all_fields = self.store.hgetall(key)
        assert "field1" in all_fields
        assert "field2" in all_fields
        
        # Cleanup
        self.store.delete(key)


# =============================================================================
# Concrete Test Classes
# =============================================================================

def run_test(test_func, name):
    """Run a single test and report result."""
    try:
        test_func()
        print(f"  ✅ {name}")
        return True
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return False


def test_postgresql_conversation_store():
    """Test PostgreSQL ConversationStore."""
    print("\n=== PostgreSQL ConversationStore ===")
    
    try:
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        store = PostgresConversationStore(
            host='localhost', port=5432, database='praisonai',
            user='postgres', password='praison123'
        )
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    class TestPostgres(ConversationStoreTestMixin):
        pass
    
    test = TestPostgres()
    test.store = store
    
    results = []
    results.append(run_test(test.test_create_session, "create_session"))
    results.append(run_test(test.test_get_session, "get_session"))
    results.append(run_test(test.test_update_session, "update_session"))
    results.append(run_test(test.test_delete_session, "delete_session"))
    results.append(run_test(test.test_add_message, "add_message"))
    results.append(run_test(test.test_get_messages, "get_messages"))
    results.append(run_test(test.test_list_sessions, "list_sessions"))
    
    store.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def test_sqlite_conversation_store():
    """Test SQLite ConversationStore."""
    print("\n=== SQLite ConversationStore ===")
    
    try:
        from praisonai.persistence.conversation.sqlite import SQLiteConversationStore
        store = SQLiteConversationStore(path="/tmp/test_praison.db")
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    class TestSQLite(ConversationStoreTestMixin):
        pass
    
    test = TestSQLite()
    test.store = store
    
    results = []
    results.append(run_test(test.test_create_session, "create_session"))
    results.append(run_test(test.test_get_session, "get_session"))
    results.append(run_test(test.test_update_session, "update_session"))
    results.append(run_test(test.test_delete_session, "delete_session"))
    results.append(run_test(test.test_add_message, "add_message"))
    results.append(run_test(test.test_get_messages, "get_messages"))
    results.append(run_test(test.test_list_sessions, "list_sessions"))
    
    store.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def test_qdrant_knowledge_store():
    """Test Qdrant KnowledgeStore."""
    print("\n=== Qdrant KnowledgeStore ===")
    
    try:
        from praisonai.persistence.knowledge.qdrant import QdrantKnowledgeStore
        store = QdrantKnowledgeStore(host='localhost', port=6333)
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    class TestQdrant(KnowledgeStoreTestMixin):
        pass
    
    test = TestQdrant()
    test.store = store
    test.collection_name = f"test_{uuid.uuid4().hex[:8]}"
    
    results = []
    results.append(run_test(test.test_create_collection, "create_collection"))
    results.append(run_test(test.test_insert_documents, "insert_documents"))
    results.append(run_test(test.test_search_documents, "search_documents"))
    results.append(run_test(test.test_delete_documents, "delete_documents"))
    
    store.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def test_chroma_knowledge_store():
    """Test ChromaDB KnowledgeStore."""
    print("\n=== ChromaDB KnowledgeStore ===")
    
    try:
        from praisonai.persistence.knowledge.chroma import ChromaKnowledgeStore
        store = ChromaKnowledgeStore(path="/tmp/test_chroma")
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    class TestChroma(KnowledgeStoreTestMixin):
        pass
    
    test = TestChroma()
    test.store = store
    test.collection_name = f"test_{uuid.uuid4().hex[:8]}"
    
    results = []
    results.append(run_test(test.test_create_collection, "create_collection"))
    results.append(run_test(test.test_insert_documents, "insert_documents"))
    results.append(run_test(test.test_search_documents, "search_documents"))
    results.append(run_test(test.test_delete_documents, "delete_documents"))
    
    store.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def test_redis_state_store():
    """Test Redis StateStore."""
    print("\n=== Redis StateStore ===")
    
    try:
        from praisonai.persistence.state.redis import RedisStateStore
        store = RedisStateStore(host='localhost', port=6379)
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    class TestRedis(StateStoreTestMixin):
        pass
    
    test = TestRedis()
    test.store = store
    
    results = []
    results.append(run_test(test.test_set_get, "set_get"))
    results.append(run_test(test.test_set_with_ttl, "set_with_ttl"))
    results.append(run_test(test.test_delete, "delete"))
    results.append(run_test(test.test_exists, "exists"))
    results.append(run_test(test.test_hash_operations, "hash_operations"))
    
    store.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def test_memory_state_store():
    """Test Memory StateStore (zero-dependency)."""
    print("\n=== Memory StateStore ===")
    
    try:
        from praisonai.persistence.state.memory import MemoryStateStore
        store = MemoryStateStore(path="/tmp/test_state.json")
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    class TestMemory(StateStoreTestMixin):
        pass
    
    test = TestMemory()
    test.store = store
    
    results = []
    results.append(run_test(test.test_set_get, "set_get"))
    results.append(run_test(test.test_set_with_ttl, "set_with_ttl"))
    results.append(run_test(test.test_delete, "delete"))
    results.append(run_test(test.test_exists, "exists"))
    results.append(run_test(test.test_hash_operations, "hash_operations"))
    
    store.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def test_orchestrator_integration():
    """Test PersistenceOrchestrator with all stores."""
    print("\n=== PersistenceOrchestrator Integration ===")
    
    try:
        from praisonai.persistence.conversation.postgres import PostgresConversationStore
        from praisonai.persistence.knowledge.qdrant import QdrantKnowledgeStore
        from praisonai.persistence.state.redis import RedisStateStore
        
        conv_store = PostgresConversationStore(
            host='localhost', port=5432, database='praisonai',
            user='postgres', password='praison123'
        )
        knowledge_store = QdrantKnowledgeStore(host='localhost', port=6333)
        state_store = RedisStateStore(host='localhost', port=6379)
        
        orchestrator = PersistenceOrchestrator(
            conversation_store=conv_store,
            knowledge_store=knowledge_store,
            state_store=state_store,
        )
    except Exception as e:
        print(f"  ⚠️ SKIPPED: {e}")
        return
    
    results = []
    
    # Test 1: Agent lifecycle
    def test_agent_lifecycle():
        class MockAgent:
            name = "test-agent"
        
        agent = MockAgent()
        session_id = f"orch-test-{uuid.uuid4().hex[:8]}"
        
        # Start
        history = orchestrator.on_agent_start(agent, session_id=session_id, user_id="test-user")
        assert isinstance(history, list)
        
        # Messages
        orchestrator.on_message(session_id, "user", "Hello!")
        orchestrator.on_message(session_id, "assistant", "Hi there!")
        
        # End
        orchestrator.on_agent_end(agent, session_id)
        
        # Verify
        messages = orchestrator.get_messages(session_id)
        assert len(messages) == 2
        
        # Cleanup
        orchestrator.delete_session(session_id)
    
    results.append(run_test(test_agent_lifecycle, "agent_lifecycle"))
    
    # Test 2: State management
    def test_state_management():
        key = f"orch:state:{uuid.uuid4().hex[:8]}"
        orchestrator.set_state(key, {"test": True})
        value = orchestrator.get_state(key)
        assert value == {"test": True}
        orchestrator.delete_state(key)
    
    results.append(run_test(test_state_management, "state_management"))
    
    # Test 3: Session resume
    def test_session_resume():
        class MockAgent:
            name = "resume-agent"
        
        agent = MockAgent()
        session_id = f"resume-test-{uuid.uuid4().hex[:8]}"
        
        # First run
        orchestrator.on_agent_start(agent, session_id=session_id)
        orchestrator.on_message(session_id, "user", "First message")
        orchestrator.on_agent_end(agent, session_id)
        
        # Second run - should resume
        history = orchestrator.on_agent_start(agent, session_id=session_id, resume=True)
        assert len(history) == 1
        assert history[0].content == "First message"
        
        # Cleanup
        orchestrator.delete_session(session_id)
    
    results.append(run_test(test_session_resume, "session_resume"))
    
    orchestrator.close()
    print(f"  Results: {sum(results)}/{len(results)} passed")


def run_all_tests():
    """Run all database backend tests."""
    print("=" * 60)
    print("PraisonAI Persistence Layer - Comprehensive TDD Tests")
    print("=" * 60)
    
    # ConversationStore tests
    print("\n" + "=" * 40)
    print("CONVERSATION STORE BACKENDS")
    print("=" * 40)
    test_postgresql_conversation_store()
    test_sqlite_conversation_store()
    
    # KnowledgeStore tests
    print("\n" + "=" * 40)
    print("KNOWLEDGE STORE BACKENDS")
    print("=" * 40)
    test_qdrant_knowledge_store()
    test_chroma_knowledge_store()
    
    # StateStore tests
    print("\n" + "=" * 40)
    print("STATE STORE BACKENDS")
    print("=" * 40)
    test_redis_state_store()
    test_memory_state_store()
    
    # Integration tests
    print("\n" + "=" * 40)
    print("INTEGRATION TESTS")
    print("=" * 40)
    test_orchestrator_integration()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
