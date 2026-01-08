"""
Unit tests for Knowledge Models.

Tests normalization functions and dataclasses.
"""

from praisonaiagents.knowledge.models import (
    SearchResultItem,
    SearchResult,
    AddResult,
    normalize_search_item,
    normalize_search_result,
    normalize_to_dict,
)


class TestSearchResultItem:
    """Tests for SearchResultItem dataclass."""
    
    def test_default_values(self):
        """Test default values are set correctly."""
        item = SearchResultItem()
        assert item.id == ""
        assert item.text == ""
        assert item.score == 0.0
        assert item.metadata == {}
        assert item.source is None
        assert item.filename is None
    
    def test_metadata_never_none(self):
        """Test metadata is never None - critical for mem0 compatibility."""
        # Explicitly pass None
        item = SearchResultItem(metadata=None)
        assert item.metadata == {}
        assert item.metadata is not None
    
    def test_to_dict(self):
        """Test conversion to dict."""
        item = SearchResultItem(
            id="test-id",
            text="test content",
            score=0.95,
            metadata={"key": "value"},
            source="test.txt",
        )
        d = item.to_dict()
        assert d["id"] == "test-id"
        assert d["text"] == "test content"
        assert d["score"] == 0.95
        assert d["metadata"] == {"key": "value"}
        assert d["source"] == "test.txt"


class TestSearchResult:
    """Tests for SearchResult dataclass."""
    
    def test_default_values(self):
        """Test default values are set correctly."""
        result = SearchResult()
        assert result.results == []
        assert result.metadata == {}
        assert result.query == ""
    
    def test_metadata_never_none(self):
        """Test metadata is never None."""
        result = SearchResult(metadata=None)
        assert result.metadata == {}
    
    def test_results_never_none(self):
        """Test results is never None."""
        result = SearchResult(results=None)
        assert result.results == []
    
    def test_to_legacy_format(self):
        """Test conversion to legacy format with 'memory' field."""
        result = SearchResult(
            results=[
                SearchResultItem(id="1", text="content 1"),
                SearchResultItem(id="2", text="content 2"),
            ]
        )
        legacy = result.to_legacy_format()
        assert "results" in legacy
        assert len(legacy["results"]) == 2
        assert legacy["results"][0]["memory"] == "content 1"
        assert legacy["results"][0]["text"] == "content 1"


class TestNormalizeSearchItem:
    """Tests for normalize_search_item function."""
    
    def test_normalize_none(self):
        """Test normalizing None returns empty item."""
        item = normalize_search_item(None)
        assert item.id == ""
        assert item.text == ""
        assert item.metadata == {}
    
    def test_normalize_mem0_format(self):
        """Test normalizing mem0 format with 'memory' field."""
        raw = {
            "id": "mem0-id",
            "memory": "mem0 content",
            "score": 0.85,
            "metadata": {"source": "test.txt"},
        }
        item = normalize_search_item(raw)
        assert item.id == "mem0-id"
        assert item.text == "mem0 content"
        assert item.score == 0.85
        assert item.metadata == {"source": "test.txt"}
        assert item.source == "test.txt"
    
    def test_normalize_metadata_none(self):
        """Test normalizing when metadata is None - critical mem0 bug fix."""
        raw = {
            "id": "test-id",
            "memory": "content",
            "score": 0.9,
            "metadata": None,  # mem0 returns this!
        }
        item = normalize_search_item(raw)
        assert item.metadata == {}
        assert item.metadata is not None
    
    def test_normalize_standard_format(self):
        """Test normalizing standard format with 'text' field."""
        raw = {
            "id": "std-id",
            "text": "standard content",
            "score": 0.75,
            "metadata": {"key": "value"},
        }
        item = normalize_search_item(raw)
        assert item.id == "std-id"
        assert item.text == "standard content"
        assert item.score == 0.75
    
    def test_normalize_extracts_source_from_metadata(self):
        """Test source is extracted from metadata if not at top level."""
        raw = {
            "id": "1",
            "text": "content",
            "metadata": {"source": "doc.pdf", "filename": "doc.pdf"},
        }
        item = normalize_search_item(raw)
        assert item.source == "doc.pdf"
        assert item.filename == "doc.pdf"


class TestNormalizeSearchResult:
    """Tests for normalize_search_result function."""
    
    def test_normalize_none(self):
        """Test normalizing None returns empty result."""
        result = normalize_search_result(None)
        assert result.results == []
        assert result.metadata == {}
    
    def test_normalize_dict_with_results(self):
        """Test normalizing dict with 'results' key (mem0 format)."""
        raw = {
            "results": [
                {"id": "1", "memory": "content 1", "metadata": None},
                {"id": "2", "memory": "content 2", "metadata": {"key": "val"}},
            ]
        }
        result = normalize_search_result(raw)
        assert len(result.results) == 2
        assert result.results[0].text == "content 1"
        assert result.results[0].metadata == {}  # None normalized to {}
        assert result.results[1].metadata == {"key": "val"}
    
    def test_normalize_filters_none_items(self):
        """Test None items in results list are filtered out."""
        raw = {
            "results": [
                {"id": "1", "memory": "content"},
                None,
                {"id": "2", "memory": "content 2"},
            ]
        }
        result = normalize_search_result(raw)
        assert len(result.results) == 2
    
    def test_normalize_list_format(self):
        """Test normalizing list of results."""
        raw = [
            {"id": "1", "text": "content 1"},
            {"id": "2", "text": "content 2"},
        ]
        result = normalize_search_result(raw)
        assert len(result.results) == 2
    
    def test_normalize_single_dict(self):
        """Test normalizing single result dict."""
        raw = {"id": "1", "text": "content"}
        result = normalize_search_result(raw)
        assert len(result.results) == 1
        assert result.results[0].text == "content"


class TestNormalizeToDict:
    """Tests for normalize_to_dict function."""
    
    def test_returns_legacy_format(self):
        """Test returns dict with 'results' key in legacy format."""
        raw = {
            "results": [
                {"id": "1", "memory": "content", "metadata": None},
            ]
        }
        result = normalize_to_dict(raw)
        assert "results" in result
        assert result["results"][0]["memory"] == "content"
        assert result["results"][0]["text"] == "content"
        assert result["results"][0]["metadata"] == {}


class TestAddResult:
    """Tests for AddResult dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        result = AddResult()
        assert result.id == ""
        assert result.success is True
        assert result.message == ""
        assert result.metadata == {}
    
    def test_metadata_never_none(self):
        """Test metadata is never None."""
        result = AddResult(metadata=None)
        assert result.metadata == {}
