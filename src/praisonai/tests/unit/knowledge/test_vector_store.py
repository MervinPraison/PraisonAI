"""
Unit tests for Vector Store Protocol and Registry.
"""

from praisonaiagents.knowledge.vector_store import (
    VectorRecord,
    get_vector_store_registry,
    InMemoryVectorStore,
)


class TestVectorRecord:
    """Tests for VectorRecord dataclass."""
    
    def test_record_creation(self):
        """Test basic record creation."""
        record = VectorRecord(
            id="test-id",
            text="Hello world",
            embedding=[0.1, 0.2, 0.3]
        )
        assert record.id == "test-id"
        assert record.text == "Hello world"
        assert record.embedding == [0.1, 0.2, 0.3]
        assert record.metadata == {}
        assert record.score is None
    
    def test_record_with_metadata(self):
        """Test record with metadata."""
        record = VectorRecord(
            id="test-id",
            text="Test content",
            embedding=[0.1],
            metadata={"source": "test.txt"}
        )
        assert record.metadata["source"] == "test.txt"
    
    def test_record_to_dict(self):
        """Test record serialization."""
        record = VectorRecord(
            id="test-id",
            text="Test",
            embedding=[0.1, 0.2],
            score=0.95
        )
        d = record.to_dict()
        assert d["id"] == "test-id"
        assert d["text"] == "Test"
        assert d["score"] == 0.95
    
    def test_record_from_dict(self):
        """Test record deserialization."""
        data = {
            "id": "test-id",
            "text": "Test content",
            "embedding": [0.1, 0.2, 0.3],
            "metadata": {"key": "value"},
            "score": 0.9
        }
        record = VectorRecord.from_dict(data)
        assert record.id == "test-id"
        assert record.score == 0.9


class TestInMemoryVectorStore:
    """Tests for InMemoryVectorStore."""
    
    def test_add_vectors(self):
        """Test adding vectors."""
        store = InMemoryVectorStore()
        ids = store.add(
            texts=["Hello", "World"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]]
        )
        assert len(ids) == 2
        assert store.count() == 2
    
    def test_add_with_metadata(self):
        """Test adding vectors with metadata."""
        store = InMemoryVectorStore()
        ids = store.add(
            texts=["Test"],
            embeddings=[[0.1, 0.2]],
            metadatas=[{"source": "test.txt"}]
        )
        
        records = store.get(ids)
        assert len(records) == 1
        assert records[0].metadata["source"] == "test.txt"
    
    def test_query_similarity(self):
        """Test querying by similarity."""
        store = InMemoryVectorStore()
        store.add(
            texts=["Hello world", "Goodbye world", "Hello there"],
            embeddings=[
                [1.0, 0.0, 0.0],  # Most similar to query
                [0.0, 1.0, 0.0],
                [0.9, 0.1, 0.0]   # Second most similar
            ]
        )
        
        # Query with embedding similar to first document
        results = store.query(
            embedding=[1.0, 0.0, 0.0],
            top_k=2
        )
        
        assert len(results) == 2
        assert results[0].text == "Hello world"
        assert results[0].score > results[1].score
    
    def test_query_with_filter(self):
        """Test querying with metadata filter."""
        store = InMemoryVectorStore()
        store.add(
            texts=["Doc A", "Doc B", "Doc C"],
            embeddings=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            metadatas=[
                {"type": "a"},
                {"type": "b"},
                {"type": "a"}
            ]
        )
        
        results = store.query(
            embedding=[0.1, 0.2],
            top_k=10,
            filter={"type": "a"}
        )
        
        assert len(results) == 2
        for r in results:
            assert r.metadata["type"] == "a"
    
    def test_delete_by_ids(self):
        """Test deleting by IDs."""
        store = InMemoryVectorStore()
        ids = store.add(
            texts=["A", "B", "C"],
            embeddings=[[0.1], [0.2], [0.3]]
        )
        
        deleted = store.delete(ids=[ids[0], ids[1]])
        assert deleted == 2
        assert store.count() == 1
    
    def test_delete_all(self):
        """Test deleting all vectors."""
        store = InMemoryVectorStore()
        store.add(
            texts=["A", "B", "C"],
            embeddings=[[0.1], [0.2], [0.3]]
        )
        
        deleted = store.delete(delete_all=True)
        assert deleted == 3
        assert store.count() == 0
    
    def test_delete_by_filter(self):
        """Test deleting by filter."""
        store = InMemoryVectorStore()
        store.add(
            texts=["A", "B", "C"],
            embeddings=[[0.1], [0.2], [0.3]],
            metadatas=[{"keep": True}, {"keep": False}, {"keep": True}]
        )
        
        deleted = store.delete(filter={"keep": False})
        assert deleted == 1
        assert store.count() == 2
    
    def test_get_by_ids(self):
        """Test getting vectors by ID."""
        store = InMemoryVectorStore()
        ids = store.add(
            texts=["A", "B", "C"],
            embeddings=[[0.1], [0.2], [0.3]]
        )
        
        records = store.get([ids[0], ids[2]])
        assert len(records) == 2
        texts = [r.text for r in records]
        assert "A" in texts
        assert "C" in texts
    
    def test_namespace_isolation(self):
        """Test namespace isolation."""
        store = InMemoryVectorStore()
        
        store.add(texts=["NS1"], embeddings=[[0.1]], namespace="ns1")
        store.add(texts=["NS2"], embeddings=[[0.2]], namespace="ns2")
        
        assert store.count(namespace="ns1") == 1
        assert store.count(namespace="ns2") == 1
        
        results = store.query(embedding=[0.1], namespace="ns1")
        assert len(results) == 1
        assert results[0].text == "NS1"
    
    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        # Identical vectors should have similarity 1.0
        sim = InMemoryVectorStore._cosine_similarity([1, 0, 0], [1, 0, 0])
        assert abs(sim - 1.0) < 0.001
        
        # Orthogonal vectors should have similarity 0.0
        sim = InMemoryVectorStore._cosine_similarity([1, 0, 0], [0, 1, 0])
        assert abs(sim - 0.0) < 0.001
        
        # Opposite vectors should have similarity -1.0
        sim = InMemoryVectorStore._cosine_similarity([1, 0, 0], [-1, 0, 0])
        assert abs(sim - (-1.0)) < 0.001


class TestVectorStoreRegistry:
    """Tests for VectorStoreRegistry."""
    
    def test_memory_store_registered(self):
        """Test that memory store is registered by default."""
        registry = get_vector_store_registry()
        assert "memory" in registry.list_stores()
    
    def test_get_memory_store(self):
        """Test getting memory store."""
        registry = get_vector_store_registry()
        store = registry.get("memory")
        assert store is not None
        assert store.name == "memory"
    
    def test_get_nonexistent_store(self):
        """Test getting non-existent store."""
        registry = get_vector_store_registry()
        assert registry.get("nonexistent") is None
    
    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_vector_store_registry()
        registry2 = get_vector_store_registry()
        assert registry1 is registry2
