"""
Tests for Git Integration System.

Test-Driven Development approach for Git operations.
"""

from pathlib import Path
import tempfile
import subprocess

from praisonai.cli.features.git_integration import (
    GitStatus,
    GitCommit,
    GitManager,
    CommitMessageGenerator,
    DiffViewer,
    GitIntegrationHandler,
)


# ============================================================================
# GitStatus Tests
# ============================================================================

class TestGitStatus:
    """Tests for GitStatus dataclass."""
    
    def test_create_status(self):
        """Test creating git status."""
        status = GitStatus()
        assert status.branch == ""
        assert status.is_clean is True
        assert status.staged_files == []
    
    def test_has_changes(self):
        """Test has_changes property."""
        status = GitStatus()
        assert status.has_changes is False
        
        status.modified_files = ["file.py"]
        assert status.has_changes is True


# ============================================================================
# GitCommit Tests
# ============================================================================

class TestGitCommit:
    """Tests for GitCommit dataclass."""
    
    def test_create_commit(self):
        """Test creating git commit."""
        commit = GitCommit(
            hash="abc123def456",
            short_hash="abc123d",
            message="Test commit",
            author="Test User",
            date="2024-01-01"
        )
        assert commit.hash == "abc123def456"
        assert commit.message == "Test commit"


# ============================================================================
# GitManager Tests
# ============================================================================

class TestGitManager:
    """Tests for GitManager."""
    
    def test_create_manager(self):
        """Test creating git manager."""
        manager = GitManager()
        assert manager is not None
    
    def test_is_repo_false_for_non_repo(self):
        """Test is_repo returns False for non-repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = GitManager(repo_path=tmpdir)
            assert manager.is_repo is False
    
    def test_is_repo_true_for_repo(self):
        """Test is_repo returns True for git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            
            manager = GitManager(repo_path=tmpdir)
            assert manager.is_repo is True
    
    def test_get_status_empty_repo(self):
        """Test getting status of empty repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            
            manager = GitManager(repo_path=tmpdir)
            status = manager.get_status()
            
            assert status.is_clean is True
    
    def test_get_status_with_changes(self):
        """Test getting status with changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            
            # Create a file
            (Path(tmpdir) / "test.py").write_text("# test")
            
            manager = GitManager(repo_path=tmpdir)
            status = manager.get_status()
            
            assert "test.py" in status.untracked_files
    
    def test_stage_files(self):
        """Test staging files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            (Path(tmpdir) / "test.py").write_text("# test")
            
            manager = GitManager(repo_path=tmpdir)
            result = manager.stage_files(["test.py"])
            
            assert result is True
            
            status = manager.get_status()
            assert "test.py" in status.staged_files
    
    def test_commit(self):
        """Test creating a commit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True
            )
            
            (Path(tmpdir) / "test.py").write_text("# test")
            
            manager = GitManager(repo_path=tmpdir)
            manager.stage_files()
            
            commit = manager.commit("Test commit")
            
            assert commit is not None
            assert commit.message == "Test commit"
    
    def test_get_log(self):
        """Test getting commit log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True
            )
            
            (Path(tmpdir) / "test.py").write_text("# test")
            
            manager = GitManager(repo_path=tmpdir)
            manager.stage_files()
            manager.commit("First commit")
            
            commits = manager.get_log()
            
            assert len(commits) >= 1
            assert commits[0].message == "First commit"
    
    def test_undo_last_commit(self):
        """Test undoing last commit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True
            )
            
            # Need at least 2 commits to undo one
            (Path(tmpdir) / "test.py").write_text("# test")
            
            manager = GitManager(repo_path=tmpdir)
            manager.stage_files()
            manager.commit("First commit")
            
            (Path(tmpdir) / "test2.py").write_text("# test2")
            manager.stage_files()
            manager.commit("Second commit")
            
            result = manager.undo_last_commit(soft=True)
            
            assert result is True
    
    def test_get_branches(self):
        """Test getting branches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True
            )
            
            (Path(tmpdir) / "test.py").write_text("# test")
            
            manager = GitManager(repo_path=tmpdir)
            manager.stage_files()
            manager.commit("Initial commit")
            
            branches = manager.get_branches()
            
            assert len(branches) >= 1


# ============================================================================
# CommitMessageGenerator Tests
# ============================================================================

class TestCommitMessageGenerator:
    """Tests for CommitMessageGenerator."""
    
    def test_create_generator(self):
        """Test creating generator."""
        generator = CommitMessageGenerator()
        assert generator is not None
    
    def test_generate_empty_diff(self):
        """Test generating message for empty diff."""
        generator = CommitMessageGenerator(use_ai=False)
        message = generator.generate("")
        
        assert message == "Empty commit"
    
    def test_generate_from_diff(self):
        """Test generating message from diff."""
        generator = CommitMessageGenerator(use_ai=False)
        
        diff = """
diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1 +1,5 @@
+# New content
+def hello():
+    pass
"""
        
        message = generator.generate(diff)
        
        assert len(message) > 0
        assert "test" in message.lower() or "feat" in message.lower()


# ============================================================================
# DiffViewer Tests
# ============================================================================

class TestDiffViewer:
    """Tests for DiffViewer."""
    
    def test_create_viewer(self):
        """Test creating viewer."""
        viewer = DiffViewer()
        assert viewer is not None
    
    def test_display_diff_no_console(self):
        """Test displaying diff without console."""
        viewer = DiffViewer()
        viewer._console = None
        
        # Should not raise
        viewer.display_diff("test diff")
    
    def test_display_status_no_console(self):
        """Test displaying status without console."""
        viewer = DiffViewer()
        viewer._console = None
        
        status = GitStatus(branch="main")
        viewer.display_status(status)


# ============================================================================
# GitIntegrationHandler Tests
# ============================================================================

class TestGitIntegrationHandler:
    """Tests for GitIntegrationHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = GitIntegrationHandler()
        assert handler.feature_name == "git_integration"
    
    def test_initialize(self):
        """Test initializing handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            
            handler = GitIntegrationHandler()
            git = handler.initialize(repo_path=tmpdir)
            
            assert git is not None
            assert git.is_repo is True
    
    def test_show_status(self):
        """Test showing status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            
            handler = GitIntegrationHandler()
            handler.initialize(repo_path=tmpdir)
            
            status = handler.show_status()
            
            assert status is not None


# ============================================================================
# Integration Tests
# ============================================================================

class TestGitIntegrationIntegration:
    """Integration tests for Git integration."""
    
    def test_full_workflow(self):
        """Test full git workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir, capture_output=True
            )
            
            handler = GitIntegrationHandler()
            handler.initialize(repo_path=tmpdir)
            
            # Create file
            (Path(tmpdir) / "main.py").write_text("# Main file\n")
            
            # Check status
            status = handler.show_status()
            assert "main.py" in status.untracked_files
            
            # Commit
            commit = handler.commit(message="Add main.py")
            assert commit is not None
            
            # Check log
            commits = handler.show_log()
            assert len(commits) >= 1
