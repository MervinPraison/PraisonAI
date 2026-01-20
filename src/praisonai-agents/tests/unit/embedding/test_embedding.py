"""
Unit tests for praisonaiagents.embedding module.

TDD: These tests define the expected behavior of the embedding module.
"""

import pytest
from unittest.mock import Mock, patch


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""
    
    def test_embedding_result_dataclass(self):
        """Test EmbeddingResult dataclass creation."""
        from praisonaiagents.embedding import EmbeddingResult
        
        result = EmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="text-embedding-3-small",
            usage={"prompt_tokens": 10, "total_tokens": 10},
            metadata={"test": "value"}
        )
        
        assert result.embeddings == [[0.1, 0.2, 0.3]]
        assert result.model == "text-embedding-3-small"
        assert result.usage == {"prompt_tokens": 10, "total_tokens": 10}
        assert result.metadata == {"test": "value"}
    
    def test_embedding_result_defaults(self):
        """Test EmbeddingResult with default values."""
        from praisonaiagents.embedding import EmbeddingResult
        
        result = EmbeddingResult(embeddings=[[0.1, 0.2]])
        
        assert result.embeddings == [[0.1, 0.2]]
        assert result.model is None
        assert result.usage is None
        assert result.metadata == {}


class TestEmbeddingFunction:
    """Tests for embedding() function."""
    
    @patch('litellm.embedding')
    def test_embedding_single_text(self, mock_litellm):
        """Test embedding() with single text input."""
        from praisonaiagents.embedding import embedding
        
        # Mock litellm response
        mock_item = Mock()
        mock_item.embedding = [0.1, 0.2, 0.3]
        mock_response = Mock()
        mock_response.data = [mock_item]
        mock_response.usage = Mock(prompt_tokens=5, total_tokens=5)
        mock_litellm.return_value = mock_response
        
        result = embedding("Hello world")
        
        assert len(result.embeddings) == 1
        assert result.embeddings[0] == [0.1, 0.2, 0.3]
        mock_litellm.assert_called_once()
    
    @patch('litellm.embedding')
    def test_embedding_batch_texts(self, mock_litellm):
        """Test embedding() with batch text input."""
        from praisonaiagents.embedding import embedding
        
        # Mock litellm response for batch
        mock_item1 = Mock()
        mock_item1.embedding = [0.1, 0.2]
        mock_item2 = Mock()
        mock_item2.embedding = [0.3, 0.4]
        mock_response = Mock()
        mock_response.data = [mock_item1, mock_item2]
        mock_response.usage = Mock(prompt_tokens=10, total_tokens=10)
        mock_litellm.return_value = mock_response
        
        result = embedding(["Hello", "World"])
        
        assert len(result.embeddings) == 2
        assert result.embeddings[0] == [0.1, 0.2]
        assert result.embeddings[1] == [0.3, 0.4]
    
    @patch('litellm.embedding')
    def test_embedding_with_model(self, mock_litellm):
        """Test embedding() with custom model."""
        from praisonaiagents.embedding import embedding
        
        mock_item = Mock()
        mock_item.embedding = [0.1]
        mock_response = Mock()
        mock_response.data = [mock_item]
        mock_response.usage = Mock(prompt_tokens=5, total_tokens=5)
        mock_litellm.return_value = mock_response
        
        result = embedding("test", model="text-embedding-3-large")
        
        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs['model'] == "text-embedding-3-large"
        assert result.model == "text-embedding-3-large"
    
    @patch('litellm.embedding')
    def test_embedding_with_dimensions(self, mock_litellm):
        """Test embedding() with dimensions parameter."""
        from praisonaiagents.embedding import embedding
        
        mock_item = Mock()
        mock_item.embedding = [0.1] * 256
        mock_response = Mock()
        mock_response.data = [mock_item]
        mock_response.usage = Mock(prompt_tokens=5, total_tokens=5)
        mock_litellm.return_value = mock_response
        
        emb_result = embedding("test", dimensions=256)
        
        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs['dimensions'] == 256
        assert emb_result is not None


class TestAsyncEmbedding:
    """Tests for aembedding() async function."""
    
    @pytest.mark.asyncio
    @patch('litellm.aembedding')
    async def test_aembedding_single_text(self, mock_aembedding):
        """Test aembedding() with single text input."""
        from praisonaiagents.embedding import aembedding
        
        mock_item = Mock()
        mock_item.embedding = [0.1, 0.2, 0.3]
        mock_response = Mock()
        mock_response.data = [mock_item]
        mock_response.usage = Mock(prompt_tokens=5, total_tokens=5)
        mock_aembedding.return_value = mock_response
        
        result = await aembedding("Hello world")
        
        assert len(result.embeddings) == 1
        assert result.embeddings[0] == [0.1, 0.2, 0.3]


class TestGetDimensions:
    """Tests for get_dimensions() utility."""
    
    def test_get_dimensions_known_models(self):
        """Test get_dimensions() for known models."""
        from praisonaiagents.embedding import get_dimensions
        
        assert get_dimensions("text-embedding-3-small") == 1536
        assert get_dimensions("text-embedding-3-large") == 3072
        assert get_dimensions("text-embedding-ada-002") == 1536
    
    def test_get_dimensions_partial_match(self):
        """Test get_dimensions() with partial model name match."""
        from praisonaiagents.embedding import get_dimensions
        
        assert get_dimensions("openai/text-embedding-3-small") == 1536
        assert get_dimensions("azure/text-embedding-3-large") == 3072
    
    def test_get_dimensions_unknown_model(self):
        """Test get_dimensions() returns default for unknown models."""
        from praisonaiagents.embedding import get_dimensions
        
        assert get_dimensions("unknown-model") == 1536  # Default


class TestAliases:
    """Tests for function aliases."""
    
    def test_embed_alias(self):
        """Test that embed is an alias for embedding."""
        from praisonaiagents.embedding.embed import embedding, embed
        
        assert embed is embedding
    
    def test_aembed_alias(self):
        """Test that aembed is an alias for aembedding."""
        from praisonaiagents.embedding.embed import aembedding, aembed
        
        assert aembed is aembedding


class TestLazyImports:
    """Tests for lazy import behavior."""
    
    def test_no_litellm_import_on_module_load(self):
        """Test that EmbeddingResult can be imported without litellm."""
        # EmbeddingResult should be importable without litellm
        from praisonaiagents.embedding import EmbeddingResult
        
        # This should work without litellm being imported
        test_result = EmbeddingResult(embeddings=[[0.1]])
        assert test_result.embeddings == [[0.1]]


class TestBackwardsCompatibility:
    """Tests for backwards compatibility."""
    
    def test_import_embedding_function_from_embedding_module(self):
        """Test importing embedding function from praisonaiagents.embedding."""
        from praisonaiagents.embedding import embedding
        
        # embedding is the function
        assert callable(embedding)
    
    def test_import_embedding_result(self):
        """Test importing EmbeddingResult from praisonaiagents.embedding."""
        from praisonaiagents.embedding import EmbeddingResult
        
        assert EmbeddingResult is not None


class TestSimplifiedImports:
    """Tests for simplified import patterns - the main goal of this fix."""
    
    def test_from_praisonaiagents_import_embedding_returns_function(self):
        """Test that 'from praisonaiagents import embedding' returns the function, not module."""
        from praisonaiagents import embedding
        
        # This is the key test - embedding should be a callable function
        assert callable(embedding), f"Expected function, got {type(embedding)}"
        assert not isinstance(embedding, type(None))
        # Should NOT be a module
        import types
        assert not isinstance(embedding, types.ModuleType), "embedding should be function, not module"
    
    def test_from_praisonaiagents_import_embeddings_returns_function(self):
        """Test that 'from praisonaiagents import embeddings' (plural) works as alias."""
        from praisonaiagents import embeddings
        
        assert callable(embeddings), f"Expected function, got {type(embeddings)}"
        import types
        assert not isinstance(embeddings, types.ModuleType), "embeddings should be function, not module"
    
    def test_embedding_and_embeddings_are_same_function(self):
        """Test that embedding and embeddings are the same function."""
        from praisonaiagents import embedding, embeddings
        
        assert embedding is embeddings, "embedding and embeddings should be the same function"
    
    def test_from_praisonaiagents_import_aembedding(self):
        """Test that 'from praisonaiagents import aembedding' works."""
        from praisonaiagents import aembedding
        
        assert callable(aembedding)
    
    def test_from_praisonaiagents_import_aembeddings(self):
        """Test that 'from praisonaiagents import aembeddings' (plural) works as alias."""
        from praisonaiagents import aembeddings
        
        assert callable(aembeddings)
    
    def test_from_praisonaiagents_import_EmbeddingResult(self):
        """Test that 'from praisonaiagents import EmbeddingResult' works."""
        from praisonaiagents import EmbeddingResult
        
        # Should be a class
        assert isinstance(EmbeddingResult, type) or hasattr(EmbeddingResult, '__dataclass_fields__')
    
    def test_from_praisonaiagents_import_get_dimensions(self):
        """Test that 'from praisonaiagents import get_dimensions' works."""
        from praisonaiagents import get_dimensions
        
        assert callable(get_dimensions)
        # Quick sanity check
        assert get_dimensions("text-embedding-3-small") == 1536
    
    def test_all_embedding_imports_together(self):
        """Test importing all embedding-related items at once."""
        from praisonaiagents import embedding, embeddings, aembedding, aembeddings, EmbeddingResult, get_dimensions
        
        assert callable(embedding)
        assert callable(embeddings)
        assert callable(aembedding)
        assert callable(aembeddings)
        assert EmbeddingResult is not None
        assert callable(get_dimensions)


class TestLazyLoadingPreserved:
    """Tests to ensure litellm is still lazy-loaded (no performance impact)."""
    
    def test_litellm_not_loaded_on_embedding_import(self):
        """Test that litellm is NOT loaded when importing embedding function."""
        import sys
        
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules.keys() if 'litellm' in k]
        for mod in modules_to_clear:
            del sys.modules[mod]
        
        # Import the embedding function
        from praisonaiagents import embedding
        
        # litellm should NOT be loaded yet (lazy loading preserved)
        assert 'litellm' not in sys.modules, "litellm should not be loaded on import"
    
    def test_litellm_not_loaded_on_EmbeddingResult_import(self):
        """Test that litellm is NOT loaded when importing EmbeddingResult."""
        import sys
        
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules.keys() if 'litellm' in k]
        for mod in modules_to_clear:
            del sys.modules[mod]
        
        # Import EmbeddingResult
        from praisonaiagents import EmbeddingResult
        
        # litellm should NOT be loaded
        assert 'litellm' not in sys.modules, "litellm should not be loaded on EmbeddingResult import"
