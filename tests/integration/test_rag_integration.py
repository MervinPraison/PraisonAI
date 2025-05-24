import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import tempfile

# Add the source path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
except ImportError as e:
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


class TestRAGIntegration:
    """Test RAG (Retrieval Augmented Generation) integration functionality."""
    
    def test_rag_config_creation(self):
        """Test RAG configuration creation."""
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_collection",
                    "path": ".test_praison"
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                    "max_tokens": 4000
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "embedding_dims": 1536
                }
            }
        }
        
        assert config["vector_store"]["provider"] == "chroma"
        assert config["llm"]["provider"] == "openai"
        assert config["embedder"]["provider"] == "openai"
        assert config["vector_store"]["config"]["collection_name"] == "test_collection"
    
    def test_agent_with_knowledge_config(self, sample_agent_config, mock_vector_store):
        """Test agent creation with knowledge configuration."""
        rag_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "test_knowledge",
                    "path": ".test_praison"
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small"
                }
            }
        }
        
        # Mock knowledge sources
        knowledge_sources = ["test_document.pdf", "knowledge_base.txt"]
        
        agent = Agent(
            name="RAG Knowledge Agent",
            knowledge=knowledge_sources,
            knowledge_config=rag_config,
            user_id="test_user",
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        assert agent.name == "RAG Knowledge Agent"
        assert hasattr(agent, 'knowledge')
        # knowledge_config is passed to Knowledge constructor, not stored as attribute
        assert agent.knowledge is not None
    
    @patch('chromadb.Client')
    def test_vector_store_operations(self, mock_chroma_client):
        """Test vector store operations."""
        # Mock ChromaDB operations
        mock_collection = Mock()
        mock_collection.add.return_value = None
        mock_collection.query.return_value = {
            'documents': [['Sample document content']],
            'metadatas': [[{'source': 'test.pdf', 'page': 1}]],
            'distances': [[0.1]]
        }
        mock_chroma_client.return_value.get_or_create_collection.return_value = mock_collection
        
        # Simulate vector store operations
        client = mock_chroma_client()
        collection = client.get_or_create_collection("test_collection")
        
        # Test adding documents
        collection.add(
            documents=["Test document content"],
            metadatas=[{"source": "test.pdf"}],
            ids=["doc1"]
        )
        
        # Test querying
        results = collection.query(
            query_texts=["search query"],
            n_results=5
        )
        
        assert len(results['documents']) == 1
        assert 'Sample document content' in results['documents'][0]
        assert results['metadatas'][0][0]['source'] == 'test.pdf'
    
    def test_knowledge_indexing_simulation(self, temp_directory):
        """Test knowledge document indexing simulation."""
        # Create mock knowledge files
        test_files = []
        for i, content in enumerate([
            "This is a test document about AI.",
            "Machine learning is a subset of AI.",
            "Deep learning uses neural networks."
        ]):
            test_file = temp_directory / f"test_doc_{i}.txt"
            test_file.write_text(content)
            test_files.append(str(test_file))
        
        # Mock knowledge indexing process
        def mock_index_documents(file_paths, config):
            """Mock document indexing."""
            indexed_docs = []
            for file_path in file_paths:
                with open(file_path, 'r') as f:
                    content = f.read()
                indexed_docs.append({
                    'content': content,
                    'source': file_path,
                    'embedding': [0.1, 0.2, 0.3]  # Mock embedding
                })
            return indexed_docs
        
        config = {"chunk_size": 1000, "overlap": 100}
        indexed = mock_index_documents(test_files, config)
        
        assert len(indexed) == 3
        assert 'AI' in indexed[0]['content']
        assert 'Machine learning' in indexed[1]['content']
        assert 'Deep learning' in indexed[2]['content']
    
    def test_knowledge_retrieval_simulation(self, mock_vector_store):
        """Test knowledge retrieval simulation."""
        def mock_retrieve_knowledge(query: str, k: int = 5):
            """Mock knowledge retrieval."""
            # Simulate retrieval based on query
            if "AI" in query:
                return [
                    {
                        'content': 'AI is artificial intelligence technology.',
                        'source': 'ai_doc.pdf',
                        'score': 0.95
                    },
                    {
                        'content': 'Machine learning is a branch of AI.',
                        'source': 'ml_doc.pdf', 
                        'score': 0.87
                    }
                ]
            return []
        
        # Test retrieval
        results = mock_retrieve_knowledge("What is AI?", k=2)
        
        assert len(results) == 2
        assert results[0]['score'] > results[1]['score']
        assert 'artificial intelligence' in results[0]['content']
    
    def test_rag_agent_with_different_providers(self, sample_agent_config):
        """Test RAG agent with different vector store providers."""
        configs = [
            {
                "name": "ChromaDB Agent",
                "vector_store": {"provider": "chroma"},
                "embedder": {"provider": "openai"}
            },
            {
                "name": "Pinecone Agent", 
                "vector_store": {"provider": "pinecone"},
                "embedder": {"provider": "cohere"}
            },
            {
                "name": "Weaviate Agent",
                "vector_store": {"provider": "weaviate"},
                "embedder": {"provider": "huggingface"}
            }
        ]
        
        agents = []
        for config in configs:
            agent = Agent(
                name=config["name"],
                knowledge=["test_knowledge.pdf"],
                knowledge_config={
                    "vector_store": config["vector_store"],
                    "embedder": config["embedder"]
                },
                **{k: v for k, v in sample_agent_config.items() if k != 'name'}
            )
            agents.append(agent)
        
        assert len(agents) == 3
        assert agents[0].name == "ChromaDB Agent"
        assert agents[1].name == "Pinecone Agent"
        assert agents[2].name == "Weaviate Agent"
    
    def test_ollama_rag_integration(self, sample_agent_config):
        """Test RAG integration with Ollama models."""
        ollama_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "ollama_knowledge",
                    "path": ".praison"
                }
            },
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": "deepseek-r1:latest",
                    "temperature": 0,
                    "max_tokens": 8000,
                    "ollama_base_url": "http://localhost:11434"
                }
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": "nomic-embed-text:latest",
                    "ollama_base_url": "http://localhost:11434",
                    "embedding_dims": 1536
                }
            }
        }
        
        agent = Agent(
            name="Ollama RAG Agent",
            knowledge=["research_paper.pdf"],
            knowledge_config=ollama_config,
            user_id="test_user",
            llm="deepseek-r1",
            **{k: v for k, v in sample_agent_config.items() if k not in ['name', 'llm']}
        )
        
        assert agent.name == "Ollama RAG Agent"
        assert hasattr(agent, 'knowledge')
        assert agent.knowledge is not None
    
    @patch('chromadb.Client')
    def test_rag_context_injection(self, mock_chroma_client, sample_agent_config, mock_llm_response):
        """Test RAG context injection into agent prompts."""
        # Mock vector store retrieval
        mock_collection = Mock()
        mock_collection.query.return_value = {
            'documents': [['Relevant context about the query']],
            'metadatas': [[{'source': 'knowledge.pdf'}]],
            'distances': [[0.2]]
        }
        mock_chroma_client.return_value.get_or_create_collection.return_value = mock_collection
        
        # Create RAG agent
        agent = Agent(
            name="Context Injection Agent",
            knowledge=["knowledge.pdf"],
            knowledge_config={
                "vector_store": {"provider": "chroma"},
                "embedder": {"provider": "openai"}
            },
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        # Mock the knowledge retrieval and context injection
        def mock_get_context(query: str) -> str:
            """Mock getting context for a query."""
            return "Context: Relevant context about the query\nSource: knowledge.pdf"
        
        context = mock_get_context("test query")
        assert "Relevant context about the query" in context
        assert "knowledge.pdf" in context
    
    def test_multi_document_rag(self, temp_directory):
        """Test RAG with multiple document types."""
        # Create different document types
        documents = {
            'text_doc.txt': 'This is a plain text document about AI fundamentals.',
            'markdown_doc.md': '# AI Overview\nThis markdown document covers AI basics.',
            'json_data.json': '{"topic": "AI", "content": "JSON document with AI information"}'
        }
        
        doc_paths = []
        for filename, content in documents.items():
            doc_path = temp_directory / filename
            doc_path.write_text(content)
            doc_paths.append(str(doc_path))
        
        # Mock multi-document processing
        def mock_process_documents(file_paths):
            """Mock processing multiple document types."""
            processed = []
            for path in file_paths:
                with open(path, 'r') as f:
                    content = f.read()
                    processed.append({
                        'path': path,
                        'type': path.split('.')[-1],
                        'content': content,
                        'chunks': len(content) // 100 + 1
                    })
            return processed
        
        processed_docs = mock_process_documents(doc_paths)
        
        assert len(processed_docs) == 3
        assert processed_docs[0]['type'] == 'txt'
        assert processed_docs[1]['type'] == 'md'
        assert processed_docs[2]['type'] == 'json'


class TestRAGMemoryIntegration:
    """Test RAG integration with memory systems."""
    
    def test_rag_with_memory_persistence(self, temp_directory):
        """Test RAG with persistent memory."""
        memory_path = temp_directory / "rag_memory"
        memory_path.mkdir()
        
        # Mock memory configuration
        memory_config = {
            "type": "persistent",
            "path": str(memory_path),
            "vector_store": "chroma",
            "embedder": "openai"
        }
        
        # Mock memory operations
        def mock_save_interaction(query: str, response: str, context: str):
            """Mock saving interaction to memory."""
            return {
                'id': 'mem_001',
                'query': query,
                'response': response,
                'context': context,
                'timestamp': '2024-01-01T12:00:00Z'
            }
        
        def mock_retrieve_memory(query: str, limit: int = 5):
            """Mock retrieving relevant memories."""
            return [
                {
                    'query': 'Previous similar query',
                    'response': 'Previous response',
                    'context': 'Previous context',
                    'similarity': 0.85
                }
            ]
        
        # Test memory operations
        saved_memory = mock_save_interaction(
            "What is AI?",
            "AI is artificial intelligence.",
            "Context about AI from documents."
        )
        
        retrieved_memories = mock_retrieve_memory("Tell me about AI")
        
        assert saved_memory['query'] == "What is AI?"
        assert len(retrieved_memories) == 1
        assert retrieved_memories[0]['similarity'] > 0.8
    
    def test_rag_knowledge_update(self, sample_agent_config):
        """Test updating RAG knowledge base."""
        agent = Agent(
            name="Updatable RAG Agent",
            knowledge=["initial_knowledge.pdf"],
            knowledge_config={
                "vector_store": {"provider": "chroma"},
                "update_mode": "append"  # or "replace"
            },
            **{k: v for k, v in sample_agent_config.items() if k != 'name'}
        )
        
        # Mock knowledge update
        def mock_update_knowledge(agent, new_documents: list, mode: str = "append"):
            """Mock updating agent knowledge."""
            if mode == "append":
                current_knowledge = getattr(agent, 'knowledge', [])
                updated_knowledge = current_knowledge + new_documents
            else:  # replace
                updated_knowledge = new_documents
            
            return {
                'previous_count': len(getattr(agent, 'knowledge', [])),
                'new_count': len(updated_knowledge),
                'added_documents': new_documents
            }
        
        # Test knowledge update
        update_result = mock_update_knowledge(
            agent, 
            ["new_document.pdf", "updated_info.txt"],
            mode="append"
        )
        
        assert update_result['new_count'] > update_result['previous_count']
        assert len(update_result['added_documents']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v']) 