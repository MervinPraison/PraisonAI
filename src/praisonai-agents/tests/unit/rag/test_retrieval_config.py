"""
Tests for RetrievalConfig - Unified retrieval configuration.

Tests cover:
1. RetrievalConfig creation and defaults
2. Policy-based retrieval decisions
3. Conversion to knowledge_config and rag_config
4. Legacy config migration
5. Heuristic-based auto retrieval
"""

import pytest
from praisonaiagents.rag.retrieval_config import (
    RetrievalConfig,
    RetrievalPolicy,
    CitationsMode,
    create_retrieval_config,
)


class TestRetrievalConfigDefaults:
    """Test default values for RetrievalConfig."""
    
    def test_default_values(self):
        """Test that default values are set correctly."""
        config = RetrievalConfig()
        
        assert config.enabled is True
        assert config.policy == RetrievalPolicy.AUTO
        assert config.top_k == 5
        assert config.min_score == 0.0
        assert config.max_context_tokens == 4000
        assert config.rerank is False
        assert config.hybrid is False
        assert config.citations is True
        assert config.citations_mode == CitationsMode.APPEND
        assert config.vector_store_provider == "chroma"
        assert config.auto_min_length == 10
        assert config.system_separation is True
    
    def test_custom_values(self):
        """Test custom values are preserved."""
        config = RetrievalConfig(
            enabled=False,
            policy=RetrievalPolicy.ALWAYS,
            top_k=10,
            min_score=0.5,
            max_context_tokens=8000,
            rerank=True,
            hybrid=True,
            citations=False,
            citations_mode=CitationsMode.HIDDEN,
        )
        
        assert config.enabled is False
        assert config.policy == RetrievalPolicy.ALWAYS
        assert config.top_k == 10
        assert config.min_score == 0.5
        assert config.max_context_tokens == 8000
        assert config.rerank is True
        assert config.hybrid is True
        assert config.citations is False
        assert config.citations_mode == CitationsMode.HIDDEN


class TestRetrievalPolicy:
    """Test retrieval policy decisions."""
    
    def test_policy_always(self):
        """Test ALWAYS policy always retrieves."""
        config = RetrievalConfig(policy=RetrievalPolicy.ALWAYS)
        
        assert config.should_retrieve("hi") is True
        assert config.should_retrieve("") is True
        assert config.should_retrieve("what is the answer?") is True
    
    def test_policy_never(self):
        """Test NEVER policy never retrieves."""
        config = RetrievalConfig(policy=RetrievalPolicy.NEVER)
        
        assert config.should_retrieve("what is the answer?") is False
        assert config.should_retrieve("explain this document") is False
    
    def test_policy_auto_with_keywords(self):
        """Test AUTO policy retrieves for keyword queries."""
        config = RetrievalConfig(policy=RetrievalPolicy.AUTO)
        
        # Should retrieve - contains keywords
        assert config.should_retrieve("what is the main finding?") is True
        assert config.should_retrieve("explain the concept") is True
        assert config.should_retrieve("how does this work?") is True
        assert config.should_retrieve("find the relevant section") is True
    
    def test_policy_auto_with_question_mark(self):
        """Test AUTO policy retrieves for questions."""
        config = RetrievalConfig(policy=RetrievalPolicy.AUTO)
        
        assert config.should_retrieve("is this correct?") is True
        assert config.should_retrieve("can you help?") is True
    
    def test_policy_auto_short_queries(self):
        """Test AUTO policy skips short queries."""
        config = RetrievalConfig(policy=RetrievalPolicy.AUTO, auto_min_length=10)
        
        assert config.should_retrieve("hi") is False
        assert config.should_retrieve("hello") is False
        assert config.should_retrieve("ok") is False
    
    def test_force_retrieval(self):
        """Test force_retrieval overrides policy."""
        config = RetrievalConfig(policy=RetrievalPolicy.NEVER)
        
        assert config.should_retrieve("hi", force=True) is True
    
    def test_skip_retrieval(self):
        """Test skip_retrieval overrides policy."""
        config = RetrievalConfig(policy=RetrievalPolicy.ALWAYS)
        
        assert config.should_retrieve("what is the answer?", skip=True) is False
    
    def test_disabled_config(self):
        """Test disabled config never retrieves."""
        config = RetrievalConfig(enabled=False, policy=RetrievalPolicy.ALWAYS)
        
        assert config.should_retrieve("what is the answer?") is False
        assert config.should_retrieve("what is the answer?", force=True) is False


class TestConfigConversion:
    """Test conversion to knowledge_config and rag_config."""
    
    def test_to_knowledge_config(self):
        """Test conversion to Knowledge-compatible config."""
        config = RetrievalConfig(
            vector_store_provider="chroma",
            persist_path=".praison/test",
            collection_name="test_collection",
        )
        
        knowledge_config = config.to_knowledge_config()
        
        assert knowledge_config["vector_store"]["provider"] == "chroma"
        assert knowledge_config["vector_store"]["config"]["path"] == ".praison/test"
        assert knowledge_config["vector_store"]["config"]["collection_name"] == "test_collection"
    
    def test_to_knowledge_config_with_rerank(self):
        """Test rerank is included in knowledge config."""
        config = RetrievalConfig(rerank=True)
        
        knowledge_config = config.to_knowledge_config()
        
        assert "reranker" in knowledge_config
        assert knowledge_config["reranker"]["enabled"] is True
    
    def test_to_rag_config(self):
        """Test conversion to RAG pipeline config."""
        config = RetrievalConfig(
            top_k=10,
            min_score=0.5,
            max_context_tokens=8000,
            citations=True,
            hybrid=True,
            rerank=True,
        )
        
        rag_config = config.to_rag_config()
        
        assert rag_config["top_k"] == 10
        assert rag_config["min_score"] == 0.5
        assert rag_config["max_context_tokens"] == 8000
        assert rag_config["include_citations"] is True
        assert rag_config["rerank"] is True


class TestLegacyConfigMigration:
    """Test migration from legacy knowledge_config and rag_config."""
    
    def test_create_from_knowledge_config(self):
        """Test creation from legacy knowledge_config."""
        knowledge_config = {
            "vector_store": {
                "provider": "mongodb",
                "config": {
                    "collection_name": "my_collection",
                    "path": ".praison/custom",
                }
            }
        }
        
        config = create_retrieval_config(knowledge_config=knowledge_config)
        
        assert config.vector_store_provider == "mongodb"
        assert config.collection_name == "my_collection"
        assert config.persist_path == ".praison/custom"
    
    def test_create_from_rag_config(self):
        """Test creation from legacy rag_config."""
        rag_config = {
            "top_k": 10,
            "min_score": 0.3,
            "max_context_tokens": 6000,
            "include_citations": True,
            "rerank": True,
            "retrieval_strategy": "hybrid",
        }
        
        config = create_retrieval_config(rag_config=rag_config)
        
        assert config.top_k == 10
        assert config.min_score == 0.3
        assert config.max_context_tokens == 6000
        assert config.citations is True
        assert config.rerank is True
        assert config.hybrid is True
    
    def test_create_from_merged_configs(self):
        """Test creation from both legacy configs merged."""
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {"collection_name": "merged"}
            }
        }
        rag_config = {
            "top_k": 15,
            "rerank": True,
        }
        
        config = create_retrieval_config(
            knowledge_config=knowledge_config,
            rag_config=rag_config,
        )
        
        assert config.collection_name == "merged"
        assert config.top_k == 15
        assert config.rerank is True
    
    def test_create_from_retrieval_config_passthrough(self):
        """Test that RetrievalConfig instance is passed through."""
        original = RetrievalConfig(top_k=20)
        
        result = create_retrieval_config(retrieval_config=original)
        
        assert result is original
    
    def test_create_from_retrieval_config_dict(self):
        """Test creation from retrieval_config dict."""
        config_dict = {
            "top_k": 25,
            "policy": "always",
            "citations_mode": "inline",
        }
        
        config = create_retrieval_config(retrieval_config=config_dict)
        
        assert config.top_k == 25
        assert config.policy == RetrievalPolicy.ALWAYS
        assert config.citations_mode == CitationsMode.INLINE


class TestSerialization:
    """Test serialization and deserialization."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = RetrievalConfig(
            policy=RetrievalPolicy.ALWAYS,
            top_k=10,
            citations_mode=CitationsMode.INLINE,
        )
        
        data = config.to_dict()
        
        assert data["policy"] == "always"
        assert data["top_k"] == 10
        assert data["citations_mode"] == "inline"
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "policy": "never",
            "top_k": 15,
            "citations_mode": "hidden",
            "rerank": True,
        }
        
        config = RetrievalConfig.from_dict(data)
        
        assert config.policy == RetrievalPolicy.NEVER
        assert config.top_k == 15
        assert config.citations_mode == CitationsMode.HIDDEN
        assert config.rerank is True
    
    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = RetrievalConfig(
            policy=RetrievalPolicy.ALWAYS,
            top_k=20,
            min_score=0.7,
            hybrid=True,
            citations_mode=CitationsMode.INLINE,
        )
        
        data = original.to_dict()
        restored = RetrievalConfig.from_dict(data)
        
        assert restored.policy == original.policy
        assert restored.top_k == original.top_k
        assert restored.min_score == original.min_score
        assert restored.hybrid == original.hybrid
        assert restored.citations_mode == original.citations_mode
