"""Tests for RAG module import performance and lazy loading."""

import time
import sys


class TestImportPerformance:
    """Tests for import performance."""
    
    def test_rag_module_import_time(self):
        """Test that RAG module imports quickly (< 100ms)."""
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules.keys() if 'praisonaiagents.rag' in k]
        for mod in modules_to_clear:
            del sys.modules[mod]
        
        start = time.time()
        from praisonaiagents.rag import RAG, RAGConfig, RAGResult
        elapsed = time.time() - start
        
        # Should import in under 100ms (generous for CI)
        assert elapsed < 0.1, f"RAG import took {elapsed:.3f}s, expected < 0.1s"
    
    def test_no_heavy_deps_on_import(self):
        """Test that importing RAG doesn't pull heavy dependencies."""
        # Clear modules
        modules_to_clear = [k for k in sys.modules.keys() if 'praisonaiagents.rag' in k]
        for mod in modules_to_clear:
            del sys.modules[mod]
        
        # Track loaded modules before
        before = set(sys.modules.keys())
        
        # Import RAG
        from praisonaiagents.rag import RAG, RAGConfig, Citation
        
        # Track loaded modules after
        after = set(sys.modules.keys())
        new_modules = after - before
        
        # These heavy modules should NOT be imported
        heavy_deps = ['chromadb', 'torch', 'transformers', 'sentence_transformers', 
                      'faiss', 'mem0', 'litellm']
        
        for dep in heavy_deps:
            matching = [m for m in new_modules if dep in m]
            assert not matching, f"Heavy dependency {dep} was imported: {matching}"
    
    def test_lazy_loading_works(self):
        """Test that lazy loading mechanism works."""
        from praisonaiagents.rag import __getattr__, _LAZY_IMPORTS
        
        # All expected exports should be in lazy imports
        expected = ['RAG', 'RAGConfig', 'RAGResult', 'Citation', 
                    'build_context', 'truncate_context', 'deduplicate_chunks']
        
        for name in expected:
            assert name in _LAZY_IMPORTS, f"{name} not in lazy imports"


class TestProtocolCompliance:
    """Tests for protocol compliance."""
    
    def test_rag_protocol_compliance(self):
        """Test that RAG class implements RAGProtocol."""
        from praisonaiagents.rag.protocols import RAGProtocol
        from praisonaiagents.rag.pipeline import RAG
        from unittest.mock import MagicMock
        
        mock_knowledge = MagicMock()
        rag = RAG(knowledge=mock_knowledge)
        
        # Check required methods exist
        assert hasattr(rag, 'query')
        assert hasattr(rag, 'aquery')
        assert hasattr(rag, 'stream')
        assert callable(rag.query)
        assert callable(rag.aquery)
        assert callable(rag.stream)
    
    def test_context_builder_protocol(self):
        """Test ContextBuilderProtocol."""
        from praisonaiagents.rag.protocols import ContextBuilderProtocol
        from praisonaiagents.rag.context import DefaultContextBuilder
        
        builder = DefaultContextBuilder()
        
        # Should have build method
        assert hasattr(builder, 'build')
        assert callable(builder.build)
    
    def test_citation_formatter_protocol(self):
        """Test CitationFormatterProtocol."""
        from praisonaiagents.rag.protocols import CitationFormatterProtocol
        from praisonaiagents.rag.pipeline import DefaultCitationFormatter
        
        formatter = DefaultCitationFormatter()
        
        # Should have format method
        assert hasattr(formatter, 'format')
        assert callable(formatter.format)


class TestMainPackageExports:
    """Tests for main package exports."""
    
    def test_rag_in_all(self):
        """Test that RAG is accessible (via __getattr__, not necessarily in __all__)."""
        import praisonaiagents
        
        # RAG is accessible via __getattr__ for backwards compatibility
        # but may not be in __all__ (which is kept minimal for IDE experience)
        assert hasattr(praisonaiagents, 'RAG'), "RAG not accessible from praisonaiagents"
        assert hasattr(praisonaiagents, 'RAGConfig'), "RAGConfig not accessible"
        assert hasattr(praisonaiagents, 'RAGResult'), "RAGResult not accessible"
    
    def test_rag_accessible_from_main(self):
        """Test that RAG classes are accessible from main package."""
        from praisonaiagents import RAG, RAGConfig, RAGResult
        
        # Should be the actual classes
        assert RAG.__name__ == 'RAG'
        assert RAGConfig.__name__ == 'RAGConfig'
        assert RAGResult.__name__ == 'RAGResult'
