"""
Unit tests for Knowledge CLI (Phase 7).
"""
import os
import tempfile
import pytest


class TestKnowledgeCLI:
    """Tests for knowledge CLI commands."""
    
    def test_import_knowledge_cli(self):
        """knowledge_cli should be importable."""
        from praisonai.cli.features.knowledge_cli import create_knowledge_app
        assert create_knowledge_app is not None
    
    def test_create_knowledge_app(self):
        """create_knowledge_app should return a typer app."""
        from praisonai.cli.features.knowledge_cli import create_knowledge_app
        
        app = create_knowledge_app()
        # May be None if typer not installed
        if app is not None:
            assert hasattr(app, "command")
    
    def test_knowledge_app_has_commands(self):
        """Knowledge app should have expected commands."""
        from praisonai.cli.features.knowledge_cli import knowledge_app
        
        if knowledge_app is None:
            pytest.skip("typer not installed")
        
        # Check registered commands exist
        command_names = [cmd.name for cmd in knowledge_app.registered_commands]
        assert "index" in command_names
        assert "stats" in command_names
        assert "search" in command_names
        assert "clear" in command_names


class TestKnowledgeCLIIntegration:
    """Integration tests for knowledge CLI with typer runner."""
    
    @pytest.fixture
    def cli_runner(self):
        """Get typer CLI test runner."""
        try:
            from typer.testing import CliRunner
            return CliRunner()
        except ImportError:
            pytest.skip("typer not installed")
    
    @pytest.fixture
    def knowledge_app(self):
        """Get knowledge app."""
        from praisonai.cli.features.knowledge_cli import knowledge_app
        if knowledge_app is None:
            pytest.skip("typer not installed")
        return knowledge_app
    
    def test_index_command_help(self, cli_runner, knowledge_app):
        """Index command should show help."""
        result = cli_runner.invoke(knowledge_app, ["index", "--help"])
        assert result.exit_code == 0
        assert "index" in result.stdout.lower() or "path" in result.stdout.lower()
    
    def test_stats_command_help(self, cli_runner, knowledge_app):
        """Stats command should show help."""
        result = cli_runner.invoke(knowledge_app, ["stats", "--help"])
        assert result.exit_code == 0
        assert "stats" in result.stdout.lower() or "corpus" in result.stdout.lower()
    
    def test_search_command_help(self, cli_runner, knowledge_app):
        """Search command should show help."""
        result = cli_runner.invoke(knowledge_app, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.stdout.lower() or "query" in result.stdout.lower()
    
    def test_index_nonexistent_path(self, cli_runner, knowledge_app):
        """Index should fail for nonexistent path."""
        result = cli_runner.invoke(knowledge_app, ["index", "/nonexistent/path"])
        assert result.exit_code != 0
        # Error may be in stdout or output
        output = (result.stdout + (result.output if hasattr(result, 'output') else '')).lower()
        assert "error" in output or "not exist" in output or result.exit_code == 1
    
    def test_stats_with_directory(self, cli_runner, knowledge_app):
        """Stats should work with a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            with open(os.path.join(tmpdir, "test.txt"), "w") as f:
                f.write("Test content")
            
            result = cli_runner.invoke(knowledge_app, ["stats", tmpdir])
            assert result.exit_code == 0
            output = result.stdout.lower()
            assert "files" in output or "corpus" in output or "1" in output
    
    def test_stats_json_output(self, cli_runner, knowledge_app):
        """Stats should support JSON output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test.txt"), "w") as f:
                f.write("Test content")
            
            result = cli_runner.invoke(knowledge_app, ["stats", tmpdir, "--json"])
            assert result.exit_code == 0
            # Should be valid JSON
            import json
            try:
                data = json.loads(result.stdout)
                assert "file_count" in data
            except json.JSONDecodeError:
                pytest.fail("Output is not valid JSON")
