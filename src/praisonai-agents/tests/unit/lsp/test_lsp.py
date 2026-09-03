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
from praisonaiagents.lsp.config import (
    LSPConfig, DEFAULT_SERVERS, detect_language, detect_root_uri, probe,
    path_to_uri, resolve_servers,
)
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


# =============================================================================
# Auto-detection / availability helper tests
# =============================================================================

class TestDetectLanguage:
    """Tests for detect_language()."""

    def test_detects_known_extensions(self):
        assert detect_language("mod.py") == "python"
        assert detect_language("app.ts") == "typescript"
        assert detect_language("main.go") == "go"
        assert detect_language("lib.rs") == "rust"
        assert detect_language("index.jsx") == "javascript"

    def test_case_insensitive(self):
        assert detect_language("MOD.PY") == "python"

    def test_unknown_extension_returns_none(self):
        assert detect_language("notes.txt") is None
        assert detect_language("noext") is None


class TestDetectRootUri:
    """Tests for detect_root_uri() root-marker discovery."""

    def test_finds_nearest_root_marker(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool]\n")
        sub = tmp_path / "pkg" / "sub"
        sub.mkdir(parents=True)
        f = sub / "mod.py"
        f.write_text("x = 1\n")
        root = detect_root_uri(str(f))
        assert root == f"file://{tmp_path}"

    def test_returns_none_without_marker(self, tmp_path):
        f = tmp_path / "lonely.rs"
        f.write_text("fn main() {}\n")
        # No Cargo.toml / .git anywhere up to filesystem root under tmp_path.
        # Walk may still hit a real marker above tmp; assert it's not the file dir.
        root = detect_root_uri(str(f))
        assert root != f"file://{f.parent}"


class TestProbe:
    """Tests for probe() availability check."""

    def test_available_when_on_path(self, monkeypatch):
        import praisonaiagents.lsp.config as cfg
        monkeypatch.setattr(cfg.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
        available, command, hint = probe("python")
        assert available is True
        assert command == "pylsp"

    def test_unavailable_returns_command_and_hint(self, monkeypatch):
        import praisonaiagents.lsp.config as cfg
        monkeypatch.setattr(cfg.shutil, "which", lambda cmd: None)
        available, command, hint = probe("go")
        assert available is False
        assert command == "gopls"
        assert hint and "gopls" in hint

    def test_unknown_language(self):
        available, command, hint = probe("cobol")
        assert available is False
        assert command is None


class TestStartProbePreflight:
    """start() should not spawn a missing server; it records last_error."""

    def test_missing_server_sets_last_error(self, monkeypatch):
        import asyncio
        import praisonaiagents.lsp.client as client_mod
        monkeypatch.setattr(client_mod.shutil, "which", lambda cmd: None)
        client = LSPClient(language="go")
        ok = asyncio.run(client.start())
        assert ok is False
        assert client.last_error is not None
        assert "gopls" in client.last_error
        assert "install" in client.last_error

    def test_missing_custom_command_reports_custom_command(self, monkeypatch):
        """A missing custom server is named in last_error (not the default)."""
        import asyncio
        import praisonaiagents.lsp.client as client_mod
        monkeypatch.setattr(client_mod.shutil, "which", lambda cmd: None)
        client = LSPClient(language="python", command="pyright-langserver",
                           args=["--stdio"])
        ok = asyncio.run(client.start())
        assert ok is False
        assert client.last_error is not None
        assert "pyright-langserver" in client.last_error
        # The registry install hint is for pylsp; it must not mislead here.
        assert "python-lsp-server" not in client.last_error


class TestPathToUri:
    """path_to_uri() must produce valid, percent-encoded file:// URIs."""

    def test_plain_path(self, tmp_path):
        uri = path_to_uri(str(tmp_path))
        assert uri.startswith("file://")

    def test_encodes_reserved_characters(self, tmp_path):
        weird = tmp_path / "my project#1"
        weird.mkdir()
        uri = path_to_uri(str(weird))
        assert "#" not in uri
        assert " " not in uri
        assert "%23" in uri
        assert "%20" in uri

    def test_detect_root_uri_encodes_reserved(self, tmp_path):
        root = tmp_path / "proj space#x"
        root.mkdir()
        (root / "pyproject.toml").write_text("[tool]\n")
        f = root / "mod.py"
        f.write_text("x = 1\n")
        uri = detect_root_uri(str(f))
        assert uri is not None
        assert "%20" in uri and "%23" in uri


# =============================================================================
# Configurable server registry tests
# =============================================================================

class TestResolveServers:
    """Tests for resolve_servers() merge of user config over DEFAULT_SERVERS."""

    def test_none_returns_defaults_unchanged(self):
        assert resolve_servers(None) is DEFAULT_SERVERS
        assert resolve_servers({}) is DEFAULT_SERVERS

    def test_adds_new_language(self):
        user = {
            "java": {
                "command": "jdtls",
                "args": ["--stdio"],
                "extensions": [".java"],
                "root_markers": ["pom.xml", ".git"],
                "install_hint": "install eclipse.jdt.ls",
            }
        }
        merged = resolve_servers(user)
        assert "java" in merged
        assert merged["java"]["command"] == "jdtls"
        # Built-ins preserved and untouched.
        assert merged["python"]["command"] == "pylsp"
        assert "java" not in DEFAULT_SERVERS

    def test_overrides_shipped_language(self):
        user = {"python": {"command": "pyright-langserver", "args": ["--stdio"]}}
        merged = resolve_servers(user)
        assert merged["python"]["command"] == "pyright-langserver"
        # Fields not overridden fall back to the built-in entry.
        assert merged["python"]["extensions"] == [".py", ".pyi"]
        # Original default is not mutated.
        assert DEFAULT_SERVERS["python"]["command"] == "pylsp"

    def test_ignores_non_dict_entries(self):
        merged = resolve_servers({"bogus": "not-a-dict"})
        assert "bogus" not in merged

    def test_command_only_override_drops_inherited_args(self):
        # Overriding only the command must not leak the replaced server's args
        # (e.g. typescript-language-server's `--stdio`) to a different binary.
        user = {"typescript": {"command": "my-ts-server"}}
        merged = resolve_servers(user)
        assert merged["typescript"]["command"] == "my-ts-server"
        assert merged["typescript"]["args"] == []
        # Non-command fields still fall back to the built-in entry.
        assert merged["typescript"]["extensions"] == [".ts", ".tsx"]
        # Original default is untouched.
        assert DEFAULT_SERVERS["typescript"]["args"] == ["--stdio"]

    def test_command_override_with_explicit_args_kept(self):
        user = {"typescript": {"command": "my-ts-server", "args": ["--lsp"]}}
        merged = resolve_servers(user)
        assert merged["typescript"]["args"] == ["--lsp"]

    def test_same_command_override_keeps_args(self):
        # Overriding other fields while keeping the same command retains args.
        user = {"typescript": {"root_markers": ["deno.json", ".git"]}}
        merged = resolve_servers(user)
        assert merged["typescript"]["args"] == ["--stdio"]


class TestConfigurableRegistry:
    """LSPConfig / detection / probe consult the merged registry."""

    JAVA = {
        "java": {
            "command": "jdtls",
            "args": ["--stdio"],
            "extensions": [".java"],
            "root_markers": ["pom.xml", ".git"],
            "install_hint": "install eclipse.jdt.ls",
            "initialization_options": {"foo": "bar"},
        }
    }

    def test_configured_language_resolves(self):
        config = LSPConfig(language="java", servers=self.JAVA)
        assert config.command == "jdtls"
        assert config.args == ["--stdio"]
        assert config.initialization_options == {"foo": "bar"}

    def test_unconfigured_unknown_still_raises(self):
        with pytest.raises(ValueError):
            LSPConfig(language="cobol", servers=self.JAVA)

    def test_override_replaces_default_command(self):
        user = {"python": {"command": "pyright-langserver", "args": ["--stdio"]}}
        config = LSPConfig(language="python", servers=user)
        assert config.command == "pyright-langserver"
        assert config.args == ["--stdio"]

    def test_detect_language_honours_custom_extension(self):
        assert detect_language("App.java", self.JAVA) == "java"
        # Without config the same extension is unknown.
        assert detect_language("App.java") is None

    def test_probe_uses_configured_server(self, monkeypatch):
        import praisonaiagents.lsp.config as cfg
        monkeypatch.setattr(cfg.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
        available, command, hint = probe("java", self.JAVA)
        assert available is True
        assert command == "jdtls"

    def test_detect_root_uri_uses_custom_markers(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>\n")
        sub = tmp_path / "src" / "main"
        sub.mkdir(parents=True)
        f = sub / "App.java"
        f.write_text("class App {}\n")
        root = detect_root_uri(str(f), servers=self.JAVA)
        assert root == f"file://{tmp_path}"

    def test_client_threads_servers_into_config(self):
        client = LSPClient(language="java", servers=self.JAVA)
        assert client.config.command == "jdtls"

    def test_client_configured_language_start_preflight(self, monkeypatch):
        import asyncio
        import praisonaiagents.lsp.client as client_mod
        monkeypatch.setattr(client_mod.shutil, "which", lambda cmd: None)
        client = LSPClient(language="java", servers=self.JAVA)
        ok = asyncio.run(client.start())
        assert ok is False
        assert client.last_error is not None
        assert "jdtls" in client.last_error
        assert "eclipse.jdt.ls" in client.last_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
