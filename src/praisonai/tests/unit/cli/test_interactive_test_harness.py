"""
Tests for Interactive Test Harness.

Tests workspace isolation, fixtures, tool trace, and artifact generation.
"""

import tempfile
from pathlib import Path


class TestWorkspaceFixture:
    """Tests for WorkspaceFixture dataclass."""
    
    def test_empty_fixture(self):
        """Test empty workspace fixture."""
        from praisonai.cli.features.interactive_test_harness import WorkspaceFixture
        
        fixture = WorkspaceFixture.empty()
        assert fixture.name == "empty"
        assert fixture.files == {}
        assert fixture.directories == []
    
    def test_seeded_fixture(self):
        """Test seeded workspace fixture."""
        from praisonai.cli.features.interactive_test_harness import WorkspaceFixture
        
        fixture = WorkspaceFixture.seeded()
        assert fixture.name == "seeded"
        assert "README.md" in fixture.files
        assert "main.py" in fixture.files
        assert "src" in fixture.directories
    
    def test_git_fixture(self):
        """Test git workspace fixture."""
        from praisonai.cli.features.interactive_test_harness import WorkspaceFixture
        
        fixture = WorkspaceFixture.git()
        assert fixture.name == "git"
        assert ".gitignore" in fixture.files
    
    def test_python_project_fixture(self):
        """Test Python project workspace fixture."""
        from praisonai.cli.features.interactive_test_harness import WorkspaceFixture
        
        fixture = WorkspaceFixture.python_project()
        assert fixture.name == "python_project"
        assert "main.py" in fixture.files
        assert "utils.py" in fixture.files
        assert "def main" in fixture.files["main.py"]


class TestBuiltinFixtures:
    """Tests for BUILTIN_FIXTURES registry."""
    
    def test_all_fixtures_registered(self):
        """Test that all fixtures are registered."""
        from praisonai.cli.features.interactive_test_harness import BUILTIN_FIXTURES
        
        assert "empty" in BUILTIN_FIXTURES
        assert "seeded" in BUILTIN_FIXTURES
        assert "git" in BUILTIN_FIXTURES
        assert "python_project" in BUILTIN_FIXTURES
    
    def test_fixtures_are_callable(self):
        """Test that fixtures are callable factories."""
        from praisonai.cli.features.interactive_test_harness import BUILTIN_FIXTURES
        
        for name, factory in BUILTIN_FIXTURES.items():
            fixture = factory()
            assert fixture.name == name


class TestTestArtifacts:
    """Tests for TestArtifacts dataclass."""
    
    def test_save_creates_files(self):
        """Test that save creates artifact files."""
        from praisonai.cli.features.interactive_test_harness import TestArtifacts
        
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            
            artifacts = TestArtifacts(
                transcript=[{"role": "user", "content": "Hello"}],
                tool_trace=[{"tool": "test", "success": True}],
                result={"status": "passed"},
            )
            
            artifacts.save(artifacts_dir)
            
            assert (artifacts_dir / "transcript.txt").exists()
            assert (artifacts_dir / "tool_trace.jsonl").exists()
            assert (artifacts_dir / "result.json").exists()
    
    def test_save_with_workspace_snapshot(self):
        """Test saving with workspace snapshot."""
        from praisonai.cli.features.interactive_test_harness import TestArtifacts
        
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            
            artifacts = TestArtifacts(
                transcript=[],
                tool_trace=[],
                result={},
                workspace_snapshot={"test.py": "print('hello')"},
            )
            
            artifacts.save(artifacts_dir)
            
            snapshot_file = artifacts_dir / "workspace" / "test.py"
            assert snapshot_file.exists()
            assert snapshot_file.read_text() == "print('hello')"
    
    def test_save_with_judge_result(self):
        """Test saving with judge result."""
        from praisonai.cli.features.interactive_test_harness import TestArtifacts
        
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            
            artifacts = TestArtifacts(
                transcript=[],
                tool_trace=[],
                result={},
                judge_result={"score": 8, "passed": True},
            )
            
            artifacts.save(artifacts_dir)
            
            assert (artifacts_dir / "judge_result.json").exists()


class TestInteractiveTestHarness:
    """Tests for InteractiveTestHarness class."""
    
    def test_initialization_creates_workspace(self):
        """Test that initialization creates workspace."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        
        assert harness.workspace.exists()
        assert harness._workspace_created is True
        
        harness.cleanup()
    
    def test_initialization_with_custom_workspace(self):
        """Test initialization with custom workspace."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "custom"
            workspace.mkdir()
            
            harness = InteractiveTestHarness(workspace=workspace)
            
            assert harness.workspace == workspace
            assert harness._workspace_created is False
    
    def test_setup_workspace_empty(self):
        """Test setting up empty workspace."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        harness.setup_workspace("empty")
        
        assert harness.workspace.exists()
        # Empty workspace should have no files
        files = list(harness.workspace.iterdir())
        assert len(files) == 0
        
        harness.cleanup()
    
    def test_setup_workspace_seeded(self):
        """Test setting up seeded workspace."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        harness.setup_workspace("seeded")
        
        assert (harness.workspace / "README.md").exists()
        assert (harness.workspace / "main.py").exists()
        assert (harness.workspace / "src").is_dir()
        
        harness.cleanup()
    
    def test_verify_files_exists(self):
        """Test verifying file existence."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        harness.setup_workspace("empty")
        
        # Create a test file
        test_file = harness.workspace / "test.py"
        test_file.write_text("print('hello')")
        
        results = harness.verify_files({"test.py": ""})
        assert results["test.py"] is True
        
        results = harness.verify_files({"nonexistent.py": ""})
        assert results["nonexistent.py"] is False
        
        harness.cleanup()
    
    def test_verify_files_content_pattern(self):
        """Test verifying file content with pattern."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        harness.setup_workspace("empty")
        
        test_file = harness.workspace / "test.py"
        test_file.write_text("x = 42\nprint(x)")
        
        # Pattern matches
        results = harness.verify_files({"test.py": "x.*=.*42"})
        assert results["test.py"] is True
        
        # Pattern doesn't match
        results = harness.verify_files({"test.py": "y.*=.*99"})
        assert results["test.py"] is False
        
        harness.cleanup()
    
    def test_verify_tool_calls_expected(self):
        """Test verifying expected tool calls."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        from unittest.mock import MagicMock
        
        harness = InteractiveTestHarness()
        harness._executor = MagicMock()
        harness._executor.get_tools_called.return_value = ["read_file", "write_file"]
        
        results = harness.verify_tool_calls(expected_tools=["read_file"])
        assert results["passed"] is True
        assert results["expected_passed"] is True
        
        results = harness.verify_tool_calls(expected_tools=["delete_file"])
        assert results["passed"] is False
        assert "delete_file" in results["missing_tools"]
        
        harness.cleanup()
    
    def test_verify_tool_calls_forbidden(self):
        """Test verifying forbidden tool calls."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        from unittest.mock import MagicMock
        
        harness = InteractiveTestHarness()
        harness._executor = MagicMock()
        harness._executor.get_tools_called.return_value = ["read_file", "delete_file"]
        
        results = harness.verify_tool_calls(forbidden_tools=["delete_file"])
        assert results["passed"] is False
        assert results["forbidden_passed"] is False
        assert "delete_file" in results["forbidden_called"]
        
        harness.cleanup()
    
    def test_verify_response_pattern(self):
        """Test verifying response with pattern."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        
        assert harness.verify_response("The answer is 42", "42") is True
        assert harness.verify_response("The answer is 42", "99") is False
        assert harness.verify_response("Hello World", "hello") is True  # Case insensitive
        
        harness.cleanup()
    
    def test_snapshot_workspace(self):
        """Test creating workspace snapshot."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness()
        harness.setup_workspace("seeded")
        
        snapshot = harness.snapshot_workspace()
        
        assert "README.md" in snapshot
        assert "main.py" in snapshot
        assert "Test Project" in snapshot["README.md"]
        
        harness.cleanup()
    
    def test_context_manager(self):
        """Test using harness as context manager."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        with InteractiveTestHarness() as harness:
            harness.setup_workspace("empty")
            workspace_path = harness.workspace
            assert workspace_path.exists()
        
        # Workspace should be cleaned up
        assert not workspace_path.exists()
    
    def test_keep_workspace(self):
        """Test keeping workspace after cleanup."""
        from praisonai.cli.features.interactive_test_harness import InteractiveTestHarness
        
        harness = InteractiveTestHarness(keep_workspace=True)
        harness.setup_workspace("empty")
        workspace_path = harness.workspace
        
        harness.cleanup()
        
        # Workspace should still exist
        assert workspace_path.exists()
        
        # Manual cleanup
        import shutil
        shutil.rmtree(workspace_path)


class TestCreateTestHarness:
    """Tests for create_test_harness function."""
    
    def test_creates_harness_with_fixture(self):
        """Test creating harness with fixture."""
        from praisonai.cli.features.interactive_test_harness import create_test_harness
        
        harness = create_test_harness(fixture="seeded")
        
        assert (harness.workspace / "README.md").exists()
        
        harness.cleanup()
    
    def test_creates_harness_with_custom_workspace(self):
        """Test creating harness with custom workspace."""
        from praisonai.cli.features.interactive_test_harness import create_test_harness
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "custom"
            
            harness = create_test_harness(
                fixture="empty",
                workspace=workspace,
            )
            
            assert harness.workspace == workspace
