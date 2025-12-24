"""
Unit tests for the LSP module.

Tests cover:
- LSP types (Position, Range, Diagnostic, etc.)
- LSPConfig creation and defaults
- LSPClient initialization
"""

import pytest
from praisonaiagents.lsp.types import (
    Position, Range, Location, Diagnostic, DiagnosticSeverity,
    CompletionItem, TextDocumentItem, TextDocumentIdentifier
)
from praisonaiagents.lsp.config import LSPConfig, DEFAULT_SERVERS
from praisonaiagents.lsp.client import LSPClient


# =============================================================================
# Position Tests
# =============================================================================

class TestPosition:
    """Tests for Position class."""
    
    def test_position_creation(self):
        """Test creating a position."""
        pos = Position(line=10, character=5)
        assert pos.line == 10
        assert pos.character == 5
    
    def test_position_to_dict(self):
        """Test position serialization."""
        pos = Position(line=10, character=5)
        data = pos.to_dict()
        assert data == {"line": 10, "character": 5}
    
    def test_position_from_dict(self):
        """Test position deserialization."""
        pos = Position.from_dict({"line": 10, "character": 5})
        assert pos.line == 10
        assert pos.character == 5


# =============================================================================
# Range Tests
# =============================================================================

class TestRange:
    """Tests for Range class."""
    
    def test_range_creation(self):
        """Test creating a range."""
        start = Position(line=0, character=0)
        end = Position(line=10, character=20)
        r = Range(start=start, end=end)
        
        assert r.start.line == 0
        assert r.end.line == 10
    
    def test_range_to_dict(self):
        """Test range serialization."""
        r = Range(
            start=Position(0, 0),
            end=Position(10, 20)
        )
        data = r.to_dict()
        
        assert data["start"]["line"] == 0
        assert data["end"]["line"] == 10
    
    def test_range_from_dict(self):
        """Test range deserialization."""
        r = Range.from_dict({
            "start": {"line": 0, "character": 0},
            "end": {"line": 10, "character": 20}
        })
        
        assert r.start.line == 0
        assert r.end.character == 20


# =============================================================================
# Location Tests
# =============================================================================

class TestLocation:
    """Tests for Location class."""
    
    def test_location_creation(self):
        """Test creating a location."""
        loc = Location(
            uri="file:///test.py",
            range=Range(Position(0, 0), Position(10, 0))
        )
        
        assert loc.uri == "file:///test.py"
        assert loc.range.start.line == 0
    
    def test_location_to_dict(self):
        """Test location serialization."""
        loc = Location(
            uri="file:///test.py",
            range=Range(Position(0, 0), Position(10, 0))
        )
        data = loc.to_dict()
        
        assert data["uri"] == "file:///test.py"
        assert "range" in data


# =============================================================================
# Diagnostic Tests
# =============================================================================

class TestDiagnostic:
    """Tests for Diagnostic class."""
    
    def test_diagnostic_creation(self):
        """Test creating a diagnostic."""
        diag = Diagnostic(
            range=Range(Position(5, 0), Position(5, 10)),
            message="Undefined variable 'x'",
            severity=DiagnosticSeverity.ERROR
        )
        
        assert diag.message == "Undefined variable 'x'"
        assert diag.severity == DiagnosticSeverity.ERROR
    
    def test_diagnostic_default_severity(self):
        """Test default severity is ERROR."""
        diag = Diagnostic(
            range=Range(Position(0, 0), Position(0, 10)),
            message="Test"
        )
        
        assert diag.severity == DiagnosticSeverity.ERROR
    
    def test_diagnostic_to_dict(self):
        """Test diagnostic serialization."""
        diag = Diagnostic(
            range=Range(Position(5, 0), Position(5, 10)),
            message="Test error",
            severity=DiagnosticSeverity.WARNING,
            code="W001",
            source="test"
        )
        data = diag.to_dict()
        
        assert data["message"] == "Test error"
        assert data["severity"] == 2  # WARNING
        assert data["code"] == "W001"
        assert data["source"] == "test"
    
    def test_diagnostic_from_dict(self):
        """Test diagnostic deserialization."""
        diag = Diagnostic.from_dict({
            "range": {
                "start": {"line": 5, "character": 0},
                "end": {"line": 5, "character": 10}
            },
            "message": "Test error",
            "severity": 2,
            "code": "W001"
        })
        
        assert diag.message == "Test error"
        assert diag.severity == DiagnosticSeverity.WARNING
        assert diag.code == "W001"


# =============================================================================
# CompletionItem Tests
# =============================================================================

class TestCompletionItem:
    """Tests for CompletionItem class."""
    
    def test_completion_creation(self):
        """Test creating a completion item."""
        item = CompletionItem(
            label="print",
            kind=3,  # Function
            detail="Built-in function"
        )
        
        assert item.label == "print"
        assert item.kind == 3
        assert item.detail == "Built-in function"
    
    def test_completion_to_dict(self):
        """Test completion serialization."""
        item = CompletionItem(
            label="print",
            kind=3,
            detail="Built-in function",
            insert_text="print($1)"
        )
        data = item.to_dict()
        
        assert data["label"] == "print"
        assert data["insertText"] == "print($1)"
    
    def test_completion_from_dict(self):
        """Test completion deserialization."""
        item = CompletionItem.from_dict({
            "label": "print",
            "kind": 3,
            "detail": "Built-in function",
            "insertText": "print($1)"
        })
        
        assert item.label == "print"
        assert item.insert_text == "print($1)"


# =============================================================================
# TextDocument Tests
# =============================================================================

class TestTextDocumentTypes:
    """Tests for text document types."""
    
    def test_text_document_item(self):
        """Test TextDocumentItem."""
        doc = TextDocumentItem(
            uri="file:///test.py",
            language_id="python",
            version=1,
            text="print('hello')"
        )
        data = doc.to_dict()
        
        assert data["uri"] == "file:///test.py"
        assert data["languageId"] == "python"
        assert data["version"] == 1
    
    def test_text_document_identifier(self):
        """Test TextDocumentIdentifier."""
        doc = TextDocumentIdentifier(uri="file:///test.py")
        data = doc.to_dict()
        
        assert data["uri"] == "file:///test.py"


# =============================================================================
# LSPConfig Tests
# =============================================================================

class TestLSPConfig:
    """Tests for LSPConfig class."""
    
    def test_config_with_defaults(self):
        """Test config with default server."""
        config = LSPConfig(language="python")
        
        assert config.language == "python"
        assert config.command == "pylsp"
        assert config.args == []
    
    def test_config_custom_command(self):
        """Test config with custom command."""
        config = LSPConfig(
            language="python",
            command="pyright-langserver",
            args=["--stdio"]
        )
        
        assert config.command == "pyright-langserver"
        assert config.args == ["--stdio"]
    
    def test_config_unknown_language(self):
        """Test config with unknown language raises error."""
        with pytest.raises(ValueError):
            LSPConfig(language="unknown_language")
    
    def test_default_servers_exist(self):
        """Test that default servers are defined."""
        assert "python" in DEFAULT_SERVERS
        assert "javascript" in DEFAULT_SERVERS
        assert "typescript" in DEFAULT_SERVERS


# =============================================================================
# LSPClient Tests
# =============================================================================

class TestLSPClient:
    """Tests for LSPClient class."""
    
    def test_client_creation(self):
        """Test creating a client."""
        client = LSPClient(language="python")
        
        assert client.config.language == "python"
        assert not client.is_running
    
    def test_client_custom_command(self):
        """Test client with custom command."""
        client = LSPClient(
            language="python",
            command="custom-server",
            args=["--mode", "stdio"]
        )
        
        assert client.config.command == "custom-server"
        assert client.config.args == ["--mode", "stdio"]
    
    def test_client_root_uri(self):
        """Test client with root URI."""
        client = LSPClient(
            language="python",
            root_uri="file:///workspace"
        )
        
        assert client.config.root_uri == "file:///workspace"
    
    def test_client_not_running_initially(self):
        """Test client is not running initially."""
        client = LSPClient(language="python")
        
        assert not client.is_running
        assert not client._initialized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
