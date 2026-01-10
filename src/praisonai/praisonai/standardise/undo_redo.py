"""
Git-based undo/redo system for the FDEP standardisation system.

Provides:
- Checkpoint creation before changes
- Undo to previous checkpoint
- Redo to next checkpoint
- List checkpoints
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


class UndoRedoManager:
    """Git-based undo/redo for standardisation changes."""
    
    CHECKPOINT_PREFIX = "standardise-checkpoint-"
    
    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or Path.cwd()
        self._verify_git_repo()
    
    def _verify_git_repo(self) -> bool:
        """Verify we're in a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _run_git(self, *args) -> Tuple[bool, str]:
        """Run a git command."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)
    
    def create_checkpoint(self, message: Optional[str] = None) -> Tuple[bool, str]:
        """
        Create a checkpoint before making changes.
        
        Returns:
            Tuple of (success, checkpoint_id or error message)
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        checkpoint_id = f"{self.CHECKPOINT_PREFIX}{timestamp}"
        
        # Stage all changes
        success, output = self._run_git("add", "-A")
        if not success:
            return False, f"Failed to stage changes: {output}"
        
        # Check if there are changes to commit
        success, output = self._run_git("diff", "--cached", "--quiet")
        if success:
            # No changes to commit, just create a tag at current HEAD
            pass
        else:
            # Commit changes
            commit_msg = message or f"Standardise checkpoint: {timestamp}"
            success, output = self._run_git("commit", "-m", commit_msg)
            if not success and "nothing to commit" not in output:
                return False, f"Failed to commit: {output}"
        
        # Create tag
        tag_msg = message or f"Standardise checkpoint at {timestamp}"
        success, output = self._run_git("tag", "-a", checkpoint_id, "-m", tag_msg)
        if not success:
            return False, f"Failed to create tag: {output}"
        
        return True, checkpoint_id
    
    def undo(self, checkpoint_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Undo to a previous checkpoint.
        
        Args:
            checkpoint_id: Specific checkpoint to restore (default: previous)
        
        Returns:
            Tuple of (success, message)
        """
        if checkpoint_id is None:
            # Find the most recent checkpoint
            checkpoints = self.list_checkpoints()
            if len(checkpoints) < 2:
                return False, "No previous checkpoint to undo to"
            checkpoint_id = checkpoints[1][0]  # Second most recent
        
        # Verify checkpoint exists
        success, output = self._run_git("rev-parse", checkpoint_id)
        if not success:
            return False, f"Checkpoint not found: {checkpoint_id}"
        
        # Create a safety checkpoint before undoing
        self.create_checkpoint("Auto-checkpoint before undo")
        
        # Reset to checkpoint
        success, output = self._run_git("reset", "--hard", checkpoint_id)
        if not success:
            return False, f"Failed to reset: {output}"
        
        return True, f"Restored to checkpoint: {checkpoint_id}"
    
    def redo(self) -> Tuple[bool, str]:
        """
        Redo to the next checkpoint (after an undo).
        
        Returns:
            Tuple of (success, message)
        """
        # Get reflog to find the previous HEAD
        success, output = self._run_git("reflog", "-n", "10", "--format=%H %s")
        if not success:
            return False, "Failed to read reflog"
        
        # Find the commit before the last reset
        lines = output.strip().split("\n")
        for i, line in enumerate(lines):
            if "reset: moving to" in line and i > 0:
                # The previous line has the commit we want to redo to
                target_hash = lines[i - 1].split()[0]
                success, output = self._run_git("reset", "--hard", target_hash)
                if success:
                    return True, "Redo successful"
                return False, f"Failed to redo: {output}"
        
        return False, "No redo available"
    
    def list_checkpoints(self) -> List[Tuple[str, str, str]]:
        """
        List all standardise checkpoints.
        
        Returns:
            List of (checkpoint_id, date, message) tuples
        """
        success, output = self._run_git(
            "tag", "-l", f"{self.CHECKPOINT_PREFIX}*",
            "--format=%(refname:short)|%(creatordate:short)|%(subject)"
        )
        
        if not success:
            return []
        
        checkpoints = []
        for line in output.strip().split("\n"):
            if line and "|" in line:
                parts = line.split("|", 2)
                if len(parts) >= 3:
                    checkpoints.append((parts[0], parts[1], parts[2]))
                elif len(parts) == 2:
                    checkpoints.append((parts[0], parts[1], ""))
        
        # Sort by date descending
        checkpoints.sort(key=lambda x: x[1], reverse=True)
        return checkpoints
    
    def delete_checkpoint(self, checkpoint_id: str) -> Tuple[bool, str]:
        """Delete a checkpoint."""
        success, output = self._run_git("tag", "-d", checkpoint_id)
        if success:
            return True, f"Deleted checkpoint: {checkpoint_id}"
        return False, f"Failed to delete: {output}"
    
    def get_changes_since(self, checkpoint_id: str) -> List[str]:
        """Get list of files changed since a checkpoint."""
        success, output = self._run_git(
            "diff", "--name-only", checkpoint_id, "HEAD"
        )
        
        if not success:
            return []
        
        return [f for f in output.strip().split("\n") if f]
    
    def preview_undo(self, checkpoint_id: str) -> List[str]:
        """Preview what files would change if we undo to a checkpoint."""
        return self.get_changes_since(checkpoint_id)


class FileBackupManager:
    """Simple file-based backup for non-git scenarios."""
    
    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or Path(".praison/backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def backup_file(self, file_path: Path) -> Optional[Path]:
        """Create a backup of a file."""
        if not file_path.exists():
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = self.backup_dir / backup_name
        
        import shutil
        shutil.copy2(file_path, backup_path)
        return backup_path
    
    def restore_file(self, backup_path: Path, target_path: Path) -> bool:
        """Restore a file from backup."""
        if not backup_path.exists():
            return False
        
        import shutil
        shutil.copy2(backup_path, target_path)
        return True
    
    def list_backups(self, file_stem: Optional[str] = None) -> List[Path]:
        """List all backups, optionally filtered by file stem."""
        backups = list(self.backup_dir.glob("*"))
        
        if file_stem:
            backups = [b for b in backups if b.stem.startswith(file_stem)]
        
        backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return backups
