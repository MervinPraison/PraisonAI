"""
Unit tests for Reader Protocol and Registry.
"""

import os
import tempfile
from praisonaiagents.knowledge.readers import (
    Document,
    get_reader_registry,
    detect_source_kind,
    get_file_extension,
)


class TestDocument:
    """Tests for Document dataclass."""
    
    def test_document_creation(self):
        """Test basic document creation."""
        doc = Document(content="Hello world")
        assert doc.content == "Hello world"
        assert doc.metadata == {}
        assert doc.doc_id is not None
        assert doc.embedding is None
    
    def test_document_with_metadata(self):
        """Test document with metadata."""
        doc = Document(
            content="Test content",
            metadata={"source": "test.txt", "page": 1}
        )
        assert doc.metadata["source"] == "test.txt"
        assert doc.metadata["page"] == 1
    
    def test_document_to_dict(self):
        """Test document serialization."""
        doc = Document(content="Test", metadata={"key": "value"})
        d = doc.to_dict()
        assert d["content"] == "Test"
        assert d["metadata"]["key"] == "value"
        assert "doc_id" in d
    
    def test_document_from_dict(self):
        """Test document deserialization."""
        data = {
            "content": "Test content",
            "metadata": {"source": "test.txt"},
            "doc_id": "test-id"
        }
        doc = Document.from_dict(data)
        assert doc.content == "Test content"
        assert doc.doc_id == "test-id"


class TestDetectSourceKind:
    """Tests for source kind detection."""
    
    def test_detect_url_http(self):
        """Test HTTP URL detection."""
        assert detect_source_kind("http://example.com") == "url"
    
    def test_detect_url_https(self):
        """Test HTTPS URL detection."""
        assert detect_source_kind("https://example.com/page.html") == "url"
    
    def test_detect_url_s3(self):
        """Test S3 URL detection."""
        assert detect_source_kind("s3://bucket/key") == "url"
    
    def test_detect_glob_asterisk(self):
        """Test glob pattern with asterisk."""
        assert detect_source_kind("*.txt") == "glob"
        assert detect_source_kind("docs/**/*.md") == "glob"
    
    def test_detect_glob_question(self):
        """Test glob pattern with question mark."""
        assert detect_source_kind("file?.txt") == "glob"
    
    def test_detect_glob_bracket(self):
        """Test glob pattern with brackets."""
        assert detect_source_kind("file[0-9].txt") == "glob"
    
    def test_detect_file_with_extension(self):
        """Test file path detection."""
        assert detect_source_kind("document.pdf") == "file"
        assert detect_source_kind("/path/to/file.txt") == "file"
    
    def test_detect_directory(self):
        """Test directory detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert detect_source_kind(tmpdir) == "directory"
    
    def test_detect_existing_file(self):
        """Test existing file detection."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = f.name
        try:
            assert detect_source_kind(path) == "file"
        finally:
            os.unlink(path)
    
    def test_detect_unknown(self):
        """Test unknown source kind."""
        assert detect_source_kind("") == "unknown"
        assert detect_source_kind("   ") == "unknown"


class TestGetFileExtension:
    """Tests for file extension extraction."""
    
    def test_simple_extension(self):
        """Test simple file extension."""
        assert get_file_extension("file.txt") == "txt"
        assert get_file_extension("document.pdf") == "pdf"
    
    def test_path_extension(self):
        """Test extension from path."""
        assert get_file_extension("/path/to/file.docx") == "docx"
    
    def test_url_extension(self):
        """Test extension from URL."""
        assert get_file_extension("https://example.com/doc.pdf") == "pdf"
    
    def test_no_extension(self):
        """Test file without extension."""
        assert get_file_extension("README") == ""
    
    def test_multiple_dots(self):
        """Test file with multiple dots."""
        assert get_file_extension("file.tar.gz") == "gz"


class TestReaderRegistry:
    """Tests for ReaderRegistry."""
    
    def setup_method(self):
        """Clear registry before each test."""
        registry = get_reader_registry()
        registry.clear()
    
    def test_register_reader(self):
        """Test registering a reader."""
        registry = get_reader_registry()
        
        class MockReader:
            name = "mock"
            supported_extensions = ["mock"]
            def load(self, source, *, metadata=None):
                return [Document(content="mock")]
            def can_handle(self, source):
                return source.endswith(".mock")
        
        registry.register("mock", MockReader, ["mock"])
        assert "mock" in registry.list_readers()
    
    def test_get_reader(self):
        """Test getting a reader by name."""
        registry = get_reader_registry()
        
        class MockReader:
            name = "mock"
            supported_extensions = ["mock"]
            def load(self, source, *, metadata=None):
                return []
            def can_handle(self, source):
                return True
        
        registry.register("mock", MockReader, ["mock"])
        reader = registry.get("mock")
        assert reader is not None
        assert reader.name == "mock"
    
    def test_get_nonexistent_reader(self):
        """Test getting a non-existent reader."""
        registry = get_reader_registry()
        assert registry.get("nonexistent") is None
    
    def test_extension_mapping(self):
        """Test extension to reader mapping."""
        registry = get_reader_registry()
        
        class MockReader:
            name = "mock"
            supported_extensions = ["txt", "text"]
            def load(self, source, *, metadata=None):
                return []
            def can_handle(self, source):
                return True
        
        registry.register("mock", MockReader, ["txt", "text"])
        
        extensions = registry.list_extensions()
        assert "txt" in extensions
        assert "text" in extensions
        assert extensions["txt"] == "mock"
    
    def test_get_for_source_file(self):
        """Test getting reader for file source."""
        registry = get_reader_registry()
        
        class TxtReader:
            name = "txt"
            supported_extensions = ["txt"]
            def load(self, source, *, metadata=None):
                return []
            def can_handle(self, source):
                return source.endswith(".txt")
        
        registry.register("txt", TxtReader, ["txt"])
        
        reader = registry.get_for_source("document.txt")
        assert reader is not None
        assert reader.name == "txt"
    
    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_reader_registry()
        registry2 = get_reader_registry()
        assert registry1 is registry2
