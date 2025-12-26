"""
Unit tests for Knowledge CLI Handler.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

from praisonai.cli.features.knowledge import KnowledgeHandler


class TestKnowledgeHandler:
    """Tests for KnowledgeHandler."""
    
    def test_init_defaults(self):
        """Test default initialization."""
        handler = KnowledgeHandler()
        assert handler.vector_store == "chroma"
        assert handler.retrieval_strategy == "basic"
        assert handler.reranker is None
        assert handler.index_type == "vector"
        assert handler.query_mode == "default"
    
    def test_init_custom_options(self):
        """Test initialization with custom options."""
        handler = KnowledgeHandler(
            vector_store="pinecone",
            retrieval_strategy="fusion",
            reranker="llm",
            index_type="hybrid",
            query_mode="sub_question"
        )
        assert handler.vector_store == "pinecone"
        assert handler.retrieval_strategy == "fusion"
        assert handler.reranker == "llm"
        assert handler.index_type == "hybrid"
        assert handler.query_mode == "sub_question"
    
    def test_feature_name(self):
        """Test feature name property."""
        handler = KnowledgeHandler()
        assert handler.feature_name == "knowledge"
    
    def test_get_actions(self):
        """Test available actions."""
        handler = KnowledgeHandler()
        actions = handler.get_actions()
        assert "add" in actions
        assert "query" in actions
        assert "search" in actions
        assert "list" in actions
        assert "clear" in actions
        assert "stats" in actions
    
    def test_get_help_text(self):
        """Test help text."""
        handler = KnowledgeHandler()
        help_text = handler.get_help_text()
        assert "knowledge add" in help_text
        assert "knowledge query" in help_text
        assert "--vector-store" in help_text
        assert "--retrieval" in help_text
    
    def test_action_add_no_args(self):
        """Test add action with no arguments."""
        handler = KnowledgeHandler()
        result = handler.action_add([])
        assert result is False
    
    def test_action_add_nonexistent_path(self):
        """Test add action with non-existent path."""
        handler = KnowledgeHandler()
        with patch.object(handler, '_get_knowledge', return_value=MagicMock()):
            result = handler.action_add(["/nonexistent/path/file.txt"])
            assert result is False
    
    def test_action_add_file(self):
        """Test add action with file."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            path = f.name
        
        try:
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_add([path])
                assert result is True
                mock_knowledge.add.assert_called_once_with(path)
        finally:
            os.unlink(path)
    
    def test_action_add_directory(self):
        """Test add action with directory."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.txt"), "w") as f:
                    f.write(f"content {i}")
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_add([tmpdir])
                assert result is True
                assert mock_knowledge.add.call_count == 3
    
    def test_action_add_url(self):
        """Test add action with URL."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            result = handler.action_add(["https://example.com/doc.pdf"])
            assert result is True
            mock_knowledge.add.assert_called_once_with("https://example.com/doc.pdf")
    
    def test_action_query_no_args(self):
        """Test query action with no arguments."""
        handler = KnowledgeHandler()
        result = handler.action_query([])
        assert result == []
    
    def test_action_query_with_results(self):
        """Test query action with results."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = [
            {"memory": "Result 1", "score": 0.9},
            {"memory": "Result 2", "score": 0.8}
        ]
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            results = handler.action_query(["test query"])
            assert len(results) == 2
            mock_knowledge.search.assert_called_once()
    
    def test_action_search_is_alias(self):
        """Test that search is alias for query."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.search.return_value = []
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            handler.action_search(["test"])
            mock_knowledge.search.assert_called_once()
    
    def test_action_list(self):
        """Test list action."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.documents = {"doc1": {}, "doc2": {}}
        mock_knowledge.list_documents = MagicMock(return_value=["doc1", "doc2"])
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            docs = handler.action_list([])
            assert len(docs) == 2
    
    def test_action_clear(self):
        """Test clear action."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            result = handler.action_clear([])
            assert result is True
            mock_knowledge.clear.assert_called_once()
    
    def test_action_stats(self):
        """Test stats action."""
        handler = KnowledgeHandler(
            vector_store="chroma",
            retrieval_strategy="fusion"
        )
        mock_knowledge = MagicMock()
        mock_knowledge.memory = MagicMock()
        mock_knowledge.memory.get_all.return_value = [1, 2, 3]
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            stats = handler.action_stats([])
            assert stats["vector_store"] == "chroma"
            assert stats["retrieval_strategy"] == "fusion"
            assert stats["document_count"] == 3
    
    def test_action_info_is_alias(self):
        """Test that info is alias for stats."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.memory = MagicMock()
        mock_knowledge.memory.get_all.return_value = []
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            stats = handler.action_info([])
            assert "vector_store" in stats


class TestKnowledgeHandlerGlobPatterns:
    """Tests for glob pattern handling."""
    
    def test_glob_pattern_detection(self):
        """Test that glob patterns are detected."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            for ext in ["txt", "md", "pdf"]:
                with open(os.path.join(tmpdir, f"file.{ext}"), "w") as f:
                    f.write("content")
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                pattern = os.path.join(tmpdir, "*.txt")
                result = handler.action_add([pattern])
                assert result is True
                assert mock_knowledge.add.call_count == 1
    
    def test_glob_no_matches(self):
        """Test glob pattern with no matches."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                pattern = os.path.join(tmpdir, "*.nonexistent")
                result = handler.action_add([pattern])
                assert result is False


class TestKnowledgeHandlerEdgeCases:
    """Tests for edge cases."""
    
    def test_knowledge_import_error(self):
        """Test handling of import error."""
        handler = KnowledgeHandler()
        
        with patch('praisonai.cli.features.knowledge.KnowledgeHandler._get_knowledge') as mock:
            mock.return_value = None
            result = handler.action_add(["test.txt"])
            assert result is False
    
    def test_add_with_exception(self):
        """Test add action when exception occurs."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.add.side_effect = Exception("Test error")
        
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = f.name
        
        try:
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_add([path])
                assert result is False
        finally:
            os.unlink(path)
    
    def test_query_with_exception(self):
        """Test query action when exception occurs."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.search.side_effect = Exception("Test error")
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            results = handler.action_query(["test"])
            assert results == []
