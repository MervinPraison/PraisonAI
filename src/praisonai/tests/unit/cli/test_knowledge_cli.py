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

    def test_search_handles_search_result_dataclass(self, cli_runner, knowledge_app, monkeypatch):
        """Search should not crash when Knowledge.search returns SearchResult.

        Regression test for #2775: Knowledge.search() returns a typed
        SearchResult dataclass, which the CLI previously treated as a dict,
        raising "'SearchResult' object is not subscriptable".
        """
        try:
            from praisonaiagents.knowledge.models import (
                SearchResult, SearchResultItem,
            )
            import praisonaiagents.knowledge as knowledge_mod
        except ImportError:
            pytest.skip("praisonaiagents.knowledge not installed")

        search_result = SearchResult(
            results=[
                SearchResultItem(
                    id="1",
                    text="Paris is the capital of France.",
                    score=0.9,
                    metadata={"path": "kb-audit.txt"},
                )
            ]
        )

        class _FakeKnowledge:
            def __init__(self, *args, **kwargs):
                pass

            def search(self, *args, **kwargs):
                return search_result

        monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

        result = cli_runner.invoke(knowledge_app, ["search", "Paris"])
        assert result.exit_code == 0
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "not subscriptable" not in output
        assert "Paris is the capital of France." in output

    def test_search_handles_empty_search_result(self, cli_runner, knowledge_app, monkeypatch):
        """Search should report no results for an empty SearchResult."""
        try:
            from praisonaiagents.knowledge.models import SearchResult
            import praisonaiagents.knowledge as knowledge_mod
        except ImportError:
            pytest.skip("praisonaiagents.knowledge not installed")

        class _FakeKnowledge:
            def __init__(self, *args, **kwargs):
                pass

            def search(self, *args, **kwargs):
                return SearchResult(results=[])

        monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

        result = cli_runner.invoke(knowledge_app, ["search", "Paris"])
        assert result.exit_code == 0
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "not subscriptable" not in output
        assert "No results found" in output


class TestRetrievalSearchCommand:
    """Tests for the top-level `praisonai search` command (retrieval.py).

    Mirrors the knowledge_cli regression coverage so a future refactor of the
    parallel normalization block in retrieval.search_command cannot silently
    reintroduce the #2775 crash.
    """

    @pytest.fixture
    def cli_runner(self):
        try:
            from typer.testing import CliRunner
            return CliRunner()
        except ImportError:
            pytest.skip("typer not installed")

    @pytest.fixture
    def retrieval_app(self):
        try:
            from praisonai.cli.commands.retrieval import app
        except ImportError:
            pytest.skip("retrieval CLI not installed")
        return app

    def test_search_handles_search_result_dataclass(self, cli_runner, retrieval_app, monkeypatch):
        """`praisonai search` should not crash on a SearchResult dataclass.

        Regression test for #2775 covering the parallel code path in
        retrieval.search_command.
        """
        try:
            from praisonaiagents.knowledge.models import (
                SearchResult, SearchResultItem,
            )
            import praisonaiagents.knowledge as knowledge_mod
        except ImportError:
            pytest.skip("praisonaiagents.knowledge not installed")

        search_result = SearchResult(
            results=[
                SearchResultItem(
                    id="1",
                    text="Paris is the capital of France.",
                    score=0.9,
                    metadata={"path": "kb-audit.txt"},
                )
            ]
        )

        class _FakeKnowledge:
            def __init__(self, *args, **kwargs):
                pass

            def search(self, *args, **kwargs):
                return search_result

        monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

        result = cli_runner.invoke(retrieval_app, ["search", "Paris"])
        assert result.exit_code == 0
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "not subscriptable" not in output
        assert "Paris is the capital of France." in output

    def test_search_handles_empty_search_result(self, cli_runner, retrieval_app, monkeypatch):
        """`praisonai search` should report no results for an empty SearchResult."""
        try:
            from praisonaiagents.knowledge.models import SearchResult
            import praisonaiagents.knowledge as knowledge_mod
        except ImportError:
            pytest.skip("praisonaiagents.knowledge not installed")

        class _FakeKnowledge:
            def __init__(self, *args, **kwargs):
                pass

            def search(self, *args, **kwargs):
                return SearchResult(results=[])

        monkeypatch.setattr(knowledge_mod, "Knowledge", _FakeKnowledge)

        result = cli_runner.invoke(retrieval_app, ["search", "Paris"])
        assert result.exit_code == 0
        output = result.stdout + (result.output if hasattr(result, "output") else "")
        assert "not subscriptable" not in output
        assert "No results found" in output
