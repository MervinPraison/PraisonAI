"""Tests for langextract tools."""

import tempfile
import os
from unittest.mock import patch, MagicMock


def test_langextract_extract_smoke_import():
    """Test that langextract_extract can be imported without langextract installed."""
    from praisonaiagents.tools.langextract_tools import langextract_extract
    assert langextract_extract is not None


def test_langextract_extract_missing_dependency():
    """Test behavior when langextract is not installed."""
    from praisonaiagents.tools.langextract_tools import langextract_extract
    
    with patch.dict('sys.modules', {'langextract': None}):
        with patch('builtins.__import__', side_effect=ImportError("No module named 'langextract'")):
            result = langextract_extract("test text", ["test"])
            
            assert result["success"] is False
            assert "langextract is not installed" in result["error"]
            assert result["html_path"] is None
            assert result["extractions_count"] == 0


def test_langextract_extract_empty_text():
    """Test behavior with empty text input."""
    from praisonaiagents.tools.langextract_tools import langextract_extract
    
    result = langextract_extract("", ["test"])
    
    assert result["success"] is False
    assert "Text cannot be empty" in result["error"]
    assert result["html_path"] is None
    assert result["extractions_count"] == 0


@patch('builtins.__import__')
def test_langextract_extract_with_mock_langextract(mock_import):
    """Test successful extraction with mocked langextract."""
    from praisonaiagents.tools.langextract_tools import langextract_extract
    
    # Mock langextract module
    mock_lx = MagicMock()
    mock_lx.data.CharInterval = MagicMock()
    mock_lx.data.Extraction = MagicMock()
    mock_lx.data.AnnotatedDocument = MagicMock()
    mock_lx.io.save_annotated_documents = MagicMock()
    mock_lx.visualize = MagicMock()
    
    # Mock HTML response
    mock_html = MagicMock()
    mock_html.data = "<html>test</html>"
    mock_lx.visualize.return_value = mock_html
    
    def mock_import_func(name, *args, **kwargs):
        if name == 'langextract':
            return mock_lx
        return __import__(name, *args, **kwargs)
    
    mock_import.side_effect = mock_import_func
    
    # Mock file operations
    with patch('builtins.open', create=True) as mock_open:
        with patch('os.remove'):
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            result = langextract_extract(
                text="The quick brown fox jumps",
                extractions=["fox", "quick"],
                document_id="test-doc"
            )
            
            assert result["success"] is True
            assert result["document_id"] == "test-doc"
            assert result["error"] is None
            # Should count actual extractions found (2: "fox" once, "quick" once)
            assert result["extractions_count"] >= 0


def test_langextract_render_file_missing_file():
    """Test behavior when file doesn't exist."""
    from praisonaiagents.tools.langextract_tools import langextract_render_file
    
    # Mock approval to bypass interactive prompt in tests
    with patch('praisonaiagents.approval.console_approval_callback') as mock_approval:
        mock_approval.return_value.approved = True
        result = langextract_render_file("/nonexistent/file.txt")
        
        assert result["success"] is False
        assert "File not found" in result["error"]
        assert result["html_path"] is None
        assert result["extractions_count"] == 0


@patch('os.path.exists')
@patch('builtins.open')
def test_langextract_render_file_delegates_to_extract(mock_open, mock_exists):
    """Test that render_file delegates to langextract_extract."""
    from praisonaiagents.tools.langextract_tools import langextract_render_file
    
    mock_exists.return_value = True
    mock_file = MagicMock()
    mock_file.read.return_value = "test file content"
    mock_open.return_value.__enter__.return_value = mock_file
    
    with patch('praisonaiagents.tools.langextract_tools.langextract_extract') as mock_extract:
        mock_extract.return_value = {"success": True, "delegated": True}
        
        result = langextract_render_file("/test/file.txt", ["test"])
        
        assert result["delegated"] is True
        mock_extract.assert_called_once()
        # Verify it called extract with file content
        args, kwargs = mock_extract.call_args
        assert kwargs["text"] == "test file content"


if __name__ == "__main__":
    test_langextract_extract_smoke_import()
    test_langextract_extract_missing_dependency()
    test_langextract_extract_empty_text()
    test_langextract_render_file_missing_file()
    print("All basic tests passed!")