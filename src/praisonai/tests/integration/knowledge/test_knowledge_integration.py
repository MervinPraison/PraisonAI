"""
Integration tests for Knowledge Stack.

These tests require external services and are skipped by default.
Set environment variables to enable:
- OPENAI_API_KEY: For embedding tests
- PINECONE_API_KEY: For Pinecone tests
- COHERE_API_KEY: For Cohere reranker tests
"""

import os
import pytest
import tempfile

# Skip markers
requires_openai = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)

requires_pinecone = pytest.mark.skipif(
    not os.environ.get("PINECONE_API_KEY"),
    reason="PINECONE_API_KEY not set"
)

requires_cohere = pytest.mark.skipif(
    not os.environ.get("COHERE_API_KEY"),
    reason="COHERE_API_KEY not set"
)

requires_chromadb = pytest.mark.skipif(
    not pytest.importorskip("chromadb", reason="chromadb not installed"),
    reason="chromadb not installed"
)


class TestKnowledgeIntegration:
    """Integration tests for Knowledge class."""
    
    @requires_openai
    def test_knowledge_add_and_search(self):
        """Test adding and searching documents."""
        from praisonaiagents import Knowledge
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Python is a programming language created by Guido van Rossum.")
            
            # Create knowledge instance
            knowledge = Knowledge(config={
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "path": os.path.join(tmpdir, ".praison"),
                        "collection_name": "test_collection"
                    }
                }
            })
            
            # Add document
            result = knowledge.add(test_file)
            assert result is not None
            
            # Search
            results = knowledge.search("Who created Python?")
            assert len(results) > 0
    
    @requires_openai
    def test_knowledge_store_and_retrieve(self):
        """Test storing and retrieving text content."""
        from praisonaiagents import Knowledge
        
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge = Knowledge(config={
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "path": os.path.join(tmpdir, ".praison"),
                        "collection_name": "test_store"
                    }
                }
            })
            
            # Store text
            knowledge.store("The capital of France is Paris.")
            knowledge.store("The capital of Germany is Berlin.")
            
            # Search
            results = knowledge.search("What is the capital of France?")
            assert len(results) > 0
            # Check that Paris is mentioned in results
            result_text = str(results[0]).lower()
            assert "paris" in result_text or "france" in result_text


class TestVectorStoreIntegration:
    """Integration tests for vector stores."""
    
    @requires_openai
    def test_chroma_vector_store(self):
        """Test ChromaDB vector store."""
        try:
            from praisonai.adapters.vector_stores import ChromaVectorStore
        except ImportError:
            pytest.skip("ChromaDB not available")
        
        import openai
        client = openai.OpenAI()
        
        def get_embedding(text):
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaVectorStore(
                persist_directory=tmpdir,
                namespace="test"
            )
            
            # Add vectors
            texts = ["Hello world", "Goodbye world"]
            embeddings = [get_embedding(t) for t in texts]
            
            ids = store.add(texts=texts, embeddings=embeddings)
            assert len(ids) == 2
            
            # Query
            query_embedding = get_embedding("Hello")
            results = store.query(embedding=query_embedding, top_k=2)
            
            assert len(results) > 0
            assert results[0].text == "Hello world"
    
    @requires_pinecone
    def test_pinecone_vector_store(self):
        """Test Pinecone vector store."""
        try:
            from praisonai.adapters.vector_stores import PineconeVectorStore
        except ImportError:
            pytest.skip("Pinecone not available")
        
        import openai
        client = openai.OpenAI()
        
        def get_embedding(text):
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        
        store = PineconeVectorStore(
            index_name="praisonai-test",
            namespace="integration-test"
        )
        
        # Add vectors
        texts = ["Integration test document"]
        embeddings = [get_embedding(t) for t in texts]
        
        ids = store.add(texts=texts, embeddings=embeddings)
        assert len(ids) == 1
        
        # Query
        query_embedding = get_embedding("test document")
        results = store.query(embedding=query_embedding, top_k=1)
        
        assert len(results) > 0
        
        # Cleanup
        store.delete(ids=ids)


class TestRerankerIntegration:
    """Integration tests for rerankers."""
    
    @requires_openai
    def test_llm_reranker(self):
        """Test LLM-based reranker."""
        try:
            from praisonai.adapters.rerankers import LLMReranker
        except ImportError:
            pytest.skip("Reranker not available")
        
        reranker = LLMReranker(model="gpt-5-nano")
        
        documents = [
            "Python is a programming language.",
            "JavaScript is used for web development.",
            "Python was created by Guido van Rossum."
        ]
        
        results = reranker.rerank("Who created Python?", documents, top_k=2)
        
        assert len(results) == 2
        # The document about Guido should rank higher
        assert "Guido" in results[0].text
    
    @requires_cohere
    def test_cohere_reranker(self):
        """Test Cohere reranker."""
        try:
            from praisonai.adapters.rerankers import CohereReranker
        except ImportError:
            pytest.skip("Cohere not available")
        
        reranker = CohereReranker()
        
        documents = [
            "Python is a programming language.",
            "JavaScript is used for web development.",
            "Python was created by Guido van Rossum."
        ]
        
        results = reranker.rerank("Who created Python?", documents, top_k=2)
        
        assert len(results) == 2


class TestRetrieverIntegration:
    """Integration tests for retrievers."""
    
    @requires_openai
    def test_basic_retriever(self):
        """Test basic retriever with real embeddings."""
        from praisonaiagents.knowledge.vector_store import InMemoryVectorStore
        try:
            from praisonai.adapters.retrievers import BasicRetriever
        except ImportError:
            pytest.skip("Retriever not available")
        
        import openai
        client = openai.OpenAI()
        
        def get_embedding(text):
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        
        # Setup store with documents
        store = InMemoryVectorStore()
        texts = [
            "Python is a programming language.",
            "JavaScript is for web development.",
            "Machine learning uses neural networks."
        ]
        embeddings = [get_embedding(t) for t in texts]
        store.add(texts=texts, embeddings=embeddings)
        
        # Create retriever
        retriever = BasicRetriever(
            vector_store=store,
            embedding_fn=get_embedding
        )
        
        # Retrieve
        results = retriever.retrieve("What is Python?", top_k=2)
        
        assert len(results) == 2
        assert "Python" in results[0].text
    
    @requires_openai
    def test_fusion_retriever(self):
        """Test fusion retriever with real embeddings."""
        from praisonaiagents.knowledge.vector_store import InMemoryVectorStore
        try:
            from praisonai.adapters.retrievers import FusionRetriever
        except ImportError:
            pytest.skip("Retriever not available")
        
        import openai
        client = openai.OpenAI()
        
        def get_embedding(text):
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        
        # Setup store with documents
        store = InMemoryVectorStore()
        texts = [
            "Python is a programming language created by Guido.",
            "JavaScript is for web development.",
            "Python is great for data science."
        ]
        embeddings = [get_embedding(t) for t in texts]
        store.add(texts=texts, embeddings=embeddings)
        
        # Create retriever
        retriever = FusionRetriever(
            vector_store=store,
            embedding_fn=get_embedding,
            num_queries=2
        )
        
        # Retrieve
        results = retriever.retrieve("Python programming", top_k=2)
        
        assert len(results) >= 1
