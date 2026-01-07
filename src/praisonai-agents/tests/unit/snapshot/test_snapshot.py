"""
Tests for the Snapshot module.

TDD: Tests for file change tracking with shadow git repository.
"""

import os
import shutil
import tempfile

from praisonaiagents.snapshot import FileSnapshot, SnapshotInfo, FileDiff


class TestFileDiff:
    """Tests for FileDiff."""
    
    def test_file_diff_creation(self):
        """Test basic file diff creation."""
        diff = FileDiff(
            path="src/main.py",
            additions=10,
            deletions=5,
            status="modified"
        )
        
        assert diff.path == "src/main.py"
        assert diff.additions == 10
        assert diff.deletions == 5
        assert diff.status == "modified"
    
    def test_file_diff_serialization(self):
        """Test file diff round-trip."""
        diff = FileDiff(path="test.py", additions=5, deletions=2)
        d = diff.to_dict()
        restored = FileDiff.from_dict(d)
        
        assert restored.path == diff.path
        assert restored.additions == diff.additions
        assert restored.deletions == diff.deletions


class TestSnapshotInfo:
    """Tests for SnapshotInfo."""
    
    def test_snapshot_info_creation(self):
        """Test basic snapshot info creation."""
        info = SnapshotInfo(
            commit_hash="abc123",
            session_id="session_1",
            message="Test snapshot"
        )
        
        assert info.commit_hash == "abc123"
        assert info.session_id == "session_1"
        assert info.message == "Test snapshot"
    
    def test_snapshot_info_serialization(self):
        """Test snapshot info round-trip."""
        info = SnapshotInfo(
            commit_hash="abc123",
            message="Test",
            files_changed=5,
            additions=100,
            deletions=50
        )
        
        d = info.to_dict()
        restored = SnapshotInfo.from_dict(d)
        
        assert restored.commit_hash == info.commit_hash
        assert restored.files_changed == info.files_changed


class TestFileSnapshot:
    """Tests for FileSnapshot."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_dir = tempfile.mkdtemp()
        self.snapshot_dir = tempfile.mkdtemp()
        
        # Create some test files
        os.makedirs(os.path.join(self.project_dir, "src"), exist_ok=True)
        with open(os.path.join(self.project_dir, "README.md"), "w") as f:
            f.write("# Test Project\n")
        with open(os.path.join(self.project_dir, "src", "main.py"), "w") as f:
            f.write("print('Hello')\n")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.project_dir, ignore_errors=True)
        shutil.rmtree(self.snapshot_dir, ignore_errors=True)
    
    def test_snapshot_initialization(self):
        """Test snapshot manager initialization."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        assert snapshot.project_path == self.project_dir
    
    def test_track_creates_snapshot(self):
        """Test tracking creates a snapshot."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        info = snapshot.track(message="Initial snapshot")
        
        assert info.commit_hash is not None
        assert len(info.commit_hash) > 0
        assert info.message == "Initial snapshot"
    
    def test_track_detects_changes(self):
        """Test tracking detects file changes."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Initial snapshot
        info1 = snapshot.track(message="Initial")
        
        # Make changes
        with open(os.path.join(self.project_dir, "README.md"), "a") as f:
            f.write("\nMore content\n")
        
        # Track again
        info2 = snapshot.track(message="After changes")
        
        assert info2.commit_hash != info1.commit_hash
    
    def test_diff_shows_changes(self):
        """Test diff shows file changes."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Initial snapshot
        info1 = snapshot.track(message="Initial")
        
        # Make changes
        with open(os.path.join(self.project_dir, "README.md"), "a") as f:
            f.write("\nNew line\n")
        
        # Track again
        info2 = snapshot.track(message="After changes")
        
        # Get diff
        diffs = snapshot.diff(info1.commit_hash, info2.commit_hash)
        
        assert len(diffs) > 0
        readme_diff = next((d for d in diffs if "README" in d.path), None)
        assert readme_diff is not None
        assert readme_diff.additions > 0
    
    def test_restore_reverts_changes(self):
        """Test restore reverts file changes."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Initial snapshot
        info1 = snapshot.track(message="Initial")
        
        # Read original content
        with open(os.path.join(self.project_dir, "README.md"), "r") as f:
            original_content = f.read()
        
        # Make changes
        with open(os.path.join(self.project_dir, "README.md"), "w") as f:
            f.write("Completely different content\n")
        
        # Track the change
        snapshot.track(message="Changed")
        
        # Restore to original
        result = snapshot.restore(info1.commit_hash)
        assert result is True
        
        # Verify content is restored
        with open(os.path.join(self.project_dir, "README.md"), "r") as f:
            restored_content = f.read()
        
        assert restored_content == original_content
    
    def test_restore_specific_files(self):
        """Test restoring specific files."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Initial snapshot
        info1 = snapshot.track(message="Initial")
        
        # Read original content
        with open(os.path.join(self.project_dir, "README.md"), "r") as f:
            original_readme = f.read()
        with open(os.path.join(self.project_dir, "src", "main.py"), "r") as f:
            original_main = f.read()
        
        # Change both files
        with open(os.path.join(self.project_dir, "README.md"), "w") as f:
            f.write("Changed README\n")
        with open(os.path.join(self.project_dir, "src", "main.py"), "w") as f:
            f.write("print('Changed')\n")
        
        # Track changes
        snapshot.track(message="Changed both")
        
        # Restore only README
        result = snapshot.restore(info1.commit_hash, files=["README.md"])
        assert result is True
        
        # Verify README is restored but main.py is not
        with open(os.path.join(self.project_dir, "README.md"), "r") as f:
            assert f.read() == original_readme
        
        with open(os.path.join(self.project_dir, "src", "main.py"), "r") as f:
            assert f.read() != original_main  # Should still be changed
    
    def test_list_snapshots(self):
        """Test listing snapshots."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Create multiple snapshots
        snapshot.track(message="Snapshot 1")
        
        with open(os.path.join(self.project_dir, "README.md"), "a") as f:
            f.write("\nChange 1\n")
        snapshot.track(message="Snapshot 2")
        
        with open(os.path.join(self.project_dir, "README.md"), "a") as f:
            f.write("\nChange 2\n")
        snapshot.track(message="Snapshot 3")
        
        # List snapshots
        snapshots = snapshot.list_snapshots()
        
        # Should have at least 3 snapshots (plus initial)
        assert len(snapshots) >= 3
    
    def test_get_current_hash(self):
        """Test getting current hash."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        info = snapshot.track(message="Test")
        current = snapshot.get_current_hash()
        
        assert current == info.commit_hash
    
    def test_cleanup_removes_shadow_repo(self):
        """Test cleanup removes shadow repository."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Initialize by tracking
        snapshot.track(message="Test")
        
        # Verify shadow repo exists
        assert os.path.exists(snapshot.shadow_path)
        
        # Cleanup
        snapshot.cleanup()
        
        # Verify shadow repo is removed
        assert not os.path.exists(snapshot.shadow_path)
    
    def test_ignores_gitignore_patterns(self):
        """Test that gitignore patterns are respected."""
        # Create .gitignore
        with open(os.path.join(self.project_dir, ".gitignore"), "w") as f:
            f.write("*.log\n__pycache__/\n")
        
        # Create files that should be ignored
        with open(os.path.join(self.project_dir, "debug.log"), "w") as f:
            f.write("log content\n")
        os.makedirs(os.path.join(self.project_dir, "__pycache__"), exist_ok=True)
        with open(os.path.join(self.project_dir, "__pycache__", "cache.pyc"), "w") as f:
            f.write("cache\n")
        
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Track
        snapshot.track(message="Test")
        
        # Verify ignored files are not in shadow repo
        assert not os.path.exists(os.path.join(snapshot.shadow_path, "debug.log"))
        assert not os.path.exists(os.path.join(snapshot.shadow_path, "__pycache__"))
    
    def test_session_id_tracking(self):
        """Test session ID is tracked in snapshots."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir,
            session_id="test_session_123"
        )
        
        info = snapshot.track(message="Test")
        
        assert info.session_id == "test_session_123"
    
    def test_revert_single_file(self):
        """Test reverting a single file."""
        snapshot = FileSnapshot(
            self.project_dir,
            snapshot_dir=self.snapshot_dir
        )
        
        # Initial snapshot
        snapshot.track(message="Initial")
        
        # Read original
        with open(os.path.join(self.project_dir, "README.md"), "r") as f:
            original = f.read()
        
        # Change file
        with open(os.path.join(self.project_dir, "README.md"), "w") as f:
            f.write("Changed\n")
        
        # Revert
        result = snapshot.revert("README.md")
        assert result is True
        
        # Verify reverted
        with open(os.path.join(self.project_dir, "README.md"), "r") as f:
            assert f.read() == original
