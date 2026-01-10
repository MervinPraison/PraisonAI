"""
Unit tests for the undo/redo system.
"""

from unittest.mock import patch

from praisonai.standardise.undo_redo import UndoRedoManager, FileBackupManager


class TestUndoRedoManager:
    """Tests for UndoRedoManager."""
    
    def test_init_with_path(self, tmp_path):
        """Test initialization with a path."""
        manager = UndoRedoManager(tmp_path)
        assert manager.repo_path == tmp_path
    
    def test_checkpoint_prefix(self):
        """Test checkpoint prefix constant."""
        assert UndoRedoManager.CHECKPOINT_PREFIX == "standardise-checkpoint-"
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_create_checkpoint_success(self, mock_git, tmp_path):
        """Test successful checkpoint creation."""
        mock_git.side_effect = [
            (True, ""),  # git add
            (False, "changes"),  # git diff (has changes)
            (True, ""),  # git commit
            (True, ""),  # git tag
        ]
        
        manager = UndoRedoManager(tmp_path)
        success, result = manager.create_checkpoint("Test checkpoint")
        
        assert success
        assert result.startswith("standardise-checkpoint-")
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_create_checkpoint_no_changes(self, mock_git, tmp_path):
        """Test checkpoint creation with no changes."""
        mock_git.side_effect = [
            (True, ""),  # git add
            (True, ""),  # git diff (no changes)
            (True, ""),  # git tag
        ]
        
        manager = UndoRedoManager(tmp_path)
        success, result = manager.create_checkpoint()
        
        assert success
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_list_checkpoints(self, mock_git, tmp_path):
        """Test listing checkpoints."""
        mock_git.return_value = (True, "standardise-checkpoint-20240101|2024-01-01|Test message\n")
        
        manager = UndoRedoManager(tmp_path)
        checkpoints = manager.list_checkpoints()
        
        assert len(checkpoints) == 1
        assert checkpoints[0][0] == "standardise-checkpoint-20240101"
        assert checkpoints[0][1] == "2024-01-01"
        assert checkpoints[0][2] == "Test message"
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_list_checkpoints_empty(self, mock_git, tmp_path):
        """Test listing checkpoints when none exist."""
        mock_git.return_value = (True, "")
        
        manager = UndoRedoManager(tmp_path)
        checkpoints = manager.list_checkpoints()
        
        assert checkpoints == []
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_undo_success(self, mock_git, tmp_path):
        """Test successful undo."""
        mock_git.side_effect = [
            (True, ""),  # rev-parse (checkpoint exists)
            (True, ""),  # git add (safety checkpoint)
            (True, ""),  # git diff
            (True, ""),  # git tag
            (True, ""),  # git reset
        ]
        
        manager = UndoRedoManager(tmp_path)
        success, result = manager.undo("standardise-checkpoint-test")
        
        assert success
        assert "Restored" in result
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_undo_checkpoint_not_found(self, mock_git, tmp_path):
        """Test undo with non-existent checkpoint."""
        mock_git.return_value = (False, "not found")
        
        manager = UndoRedoManager(tmp_path)
        success, result = manager.undo("nonexistent")
        
        assert not success
        assert "not found" in result
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_redo_no_redo_available(self, mock_git, tmp_path):
        """Test redo when no redo is available."""
        mock_git.return_value = (True, "abc123 HEAD@{0}: commit: test\n")
        
        manager = UndoRedoManager(tmp_path)
        success, result = manager.redo()
        
        assert not success
        assert "No redo available" in result
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_delete_checkpoint(self, mock_git, tmp_path):
        """Test deleting a checkpoint."""
        mock_git.return_value = (True, "")
        
        manager = UndoRedoManager(tmp_path)
        success, result = manager.delete_checkpoint("test-checkpoint")
        
        assert success
        assert "Deleted" in result
    
    @patch.object(UndoRedoManager, '_run_git')
    def test_get_changes_since(self, mock_git, tmp_path):
        """Test getting changes since a checkpoint."""
        mock_git.return_value = (True, "file1.py\nfile2.py\n")
        
        manager = UndoRedoManager(tmp_path)
        changes = manager.get_changes_since("test-checkpoint")
        
        assert len(changes) == 2
        assert "file1.py" in changes
        assert "file2.py" in changes


class TestFileBackupManager:
    """Tests for FileBackupManager."""
    
    def test_init_creates_backup_dir(self, tmp_path):
        """Test that init creates backup directory."""
        backup_dir = tmp_path / "backups"
        _ = FileBackupManager(backup_dir)  # Creates dir on init
        
        assert backup_dir.exists()
    
    def test_backup_file(self, tmp_path):
        """Test backing up a file."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        backup_dir = tmp_path / "backups"
        manager = FileBackupManager(backup_dir)
        
        backup_path = manager.backup_file(test_file)
        
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == "test content"
    
    def test_backup_nonexistent_file(self, tmp_path):
        """Test backing up a non-existent file."""
        manager = FileBackupManager(tmp_path / "backups")
        
        result = manager.backup_file(tmp_path / "nonexistent.txt")
        
        assert result is None
    
    def test_restore_file(self, tmp_path):
        """Test restoring a file from backup."""
        # Create backup
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        backup_file = backup_dir / "backup.txt"
        backup_file.write_text("backup content")
        
        # Target file
        target_file = tmp_path / "restored.txt"
        
        manager = FileBackupManager(backup_dir)
        result = manager.restore_file(backup_file, target_file)
        
        assert result
        assert target_file.exists()
        assert target_file.read_text() == "backup content"
    
    def test_list_backups(self, tmp_path):
        """Test listing backups."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        
        # Create some backup files
        (backup_dir / "file1_20240101.txt").write_text("1")
        (backup_dir / "file1_20240102.txt").write_text("2")
        (backup_dir / "file2_20240101.txt").write_text("3")
        
        backup_manager = FileBackupManager(backup_dir)
        
        # List all
        all_backups = backup_manager.list_backups()
        assert len(all_backups) == 3
        
        # List filtered
        file1_backups = backup_manager.list_backups("file1")
        assert len(file1_backups) == 2
