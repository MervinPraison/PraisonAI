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


class TestKnowledgeHandlerExportImport:
    """Tests for export/import functionality."""
    
    def test_get_actions_includes_export_import(self):
        """Test that export and import are in available actions."""
        handler = KnowledgeHandler()
        actions = handler.get_actions()
        assert "export" in actions
        assert "import" in actions
    
    def test_action_export_default_filename(self):
        """Test export with default filename."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.get_all.return_value = [
            {"content": "doc1", "metadata": {}},
            {"content": "doc2", "metadata": {}}
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_export([])
                assert result is True
                
                # Check that file was created
                files = os.listdir(tmpdir)
                export_files = [f for f in files if f.startswith("knowledge_export_")]
                assert len(export_files) == 1
    
    def test_action_export_custom_filename(self):
        """Test export with custom filename."""
        import json
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        # Set up memory.get_all since that's checked first
        mock_knowledge.memory = MagicMock()
        mock_knowledge.memory.get_all.return_value = [
            {"content": "test content", "metadata": {"source": "test"}}
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            output_file = os.path.join(tmpdir, "my_export.json")
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_export([output_file])
                assert result is True
                assert os.path.exists(output_file)
                
                with open(output_file, 'r') as f:
                    data = json.load(f)
                assert data["version"] == "1.0"
                assert len(data["documents"]) == 1
    
    def test_action_export_empty_knowledge(self):
        """Test export with empty knowledge base."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        mock_knowledge.get_all.return_value = []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            output_file = os.path.join(tmpdir, "empty_export.json")
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_export([output_file])
                assert result is True
    
    def test_action_import_no_args(self):
        """Test import with no arguments."""
        handler = KnowledgeHandler()
        result = handler.action_import([])
        assert result is False
    
    def test_action_import_nonexistent_file(self):
        """Test import with non-existent file."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
            result = handler.action_import(["/nonexistent/file.json"])
            assert result is False
    
    def test_action_import_valid_file(self):
        """Test import with valid JSON file."""
        import json
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            input_file = os.path.join(tmpdir, "import_test.json")
            
            # Create test import file
            import_data = {
                "version": "1.0",
                "documents": [
                    {"content": "doc1", "metadata": {}},
                    {"content": "doc2", "metadata": {"key": "value"}}
                ]
            }
            with open(input_file, 'w') as f:
                json.dump(import_data, f)
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_import([input_file])
                assert result is True
                assert mock_knowledge.store.call_count == 2 or mock_knowledge.add.call_count == 2
    
    def test_action_import_empty_documents(self):
        """Test import with empty documents list."""
        import json
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            input_file = os.path.join(tmpdir, "empty_import.json")
            
            import_data = {"version": "1.0", "documents": []}
            with open(input_file, 'w') as f:
                json.dump(import_data, f)
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_import([input_file])
                assert result is True
    
    def test_action_import_invalid_json(self):
        """Test import with invalid JSON file."""
        handler = KnowledgeHandler()
        mock_knowledge = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            input_file = os.path.join(tmpdir, "invalid.json")
            
            with open(input_file, 'w') as f:
                f.write("not valid json {{{")
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge):
                result = handler.action_import([input_file])
                assert result is False
    
    def test_export_import_roundtrip(self):
        """Test that export and import work together."""
        handler = KnowledgeHandler()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            handler.workspace = tmpdir
            export_file = os.path.join(tmpdir, "roundtrip.json")
            
            # Mock for export - set up memory.get_all since that's checked first
            mock_knowledge_export = MagicMock()
            mock_knowledge_export.memory = MagicMock()
            mock_knowledge_export.memory.get_all.return_value = [
                {"content": "test doc 1", "metadata": {"id": "1"}},
                {"content": "test doc 2", "metadata": {"id": "2"}}
            ]
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge_export):
                export_result = handler.action_export([export_file])
                assert export_result is True
            
            # Mock for import
            mock_knowledge_import = MagicMock()
            
            with patch.object(handler, '_get_knowledge', return_value=mock_knowledge_import):
                import_result = handler.action_import([export_file])
                assert import_result is True
                # Verify documents were imported
                assert mock_knowledge_import.store.call_count == 2 or mock_knowledge_import.add.call_count == 2
