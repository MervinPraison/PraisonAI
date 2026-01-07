"""
File Snapshot implementation for PraisonAI Agents.

Provides file change tracking using a shadow git repository.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default snapshot directory
DEFAULT_SNAPSHOT_DIR = os.path.expanduser("~/.praison/snapshots")


@dataclass
class FileDiff:
    """Represents a diff for a single file."""
    
    path: str
    additions: int = 0
    deletions: int = 0
    diff_content: str = ""
    status: str = "modified"  # added, modified, deleted
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "additions": self.additions,
            "deletions": self.deletions,
            "diff_content": self.diff_content,
            "status": self.status,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileDiff":
        return cls(
            path=data.get("path", ""),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            diff_content=data.get("diff_content", ""),
            status=data.get("status", "modified"),
        )


@dataclass
class SnapshotInfo:
    """Information about a snapshot."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    commit_hash: str = ""
    session_id: Optional[str] = None
    message: str = ""
    created_at: float = field(default_factory=time.time)
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "commit_hash": self.commit_hash,
            "session_id": self.session_id,
            "message": self.message,
            "created_at": self.created_at,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SnapshotInfo":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            commit_hash=data.get("commit_hash", ""),
            session_id=data.get("session_id"),
            message=data.get("message", ""),
            created_at=data.get("created_at", time.time()),
            files_changed=data.get("files_changed", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
        )


class FileSnapshot:
    """
    File snapshot manager using a shadow git repository.
    
    Creates and manages snapshots of file changes without
    interfering with the user's actual git repository.
    
    Example:
        snapshot = FileSnapshot("/path/to/project")
        
        # Track current state
        info = snapshot.track(message="Before refactor")
        
        # Make changes...
        
        # Get diff
        diffs = snapshot.diff(info.commit_hash)
        
        # Restore if needed
        snapshot.restore(info.commit_hash)
    """
    
    def __init__(
        self,
        project_path: str,
        snapshot_dir: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the file snapshot manager.
        
        Args:
            project_path: Path to the project to track
            snapshot_dir: Optional custom snapshot directory
            session_id: Optional session ID for grouping snapshots
        """
        self.project_path = os.path.abspath(project_path)
        self.session_id = session_id
        
        # Create unique shadow repo path based on project path hash
        project_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
        base_dir = snapshot_dir or DEFAULT_SNAPSHOT_DIR
        self.shadow_path = os.path.join(base_dir, project_hash)
        
        self._initialized = False
    
    def _run_git(self, *args, cwd: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the shadow repository."""
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.shadow_path,
                capture_output=True,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}")
            logger.error(f"stderr: {e.stderr}")
            raise
    
    def _ensure_initialized(self):
        """Ensure the shadow repository is initialized."""
        if self._initialized:
            return
        
        if not os.path.exists(self.shadow_path):
            os.makedirs(self.shadow_path, exist_ok=True)
            self._run_git("init", cwd=self.shadow_path)
            self._run_git("config", "user.email", "praison@snapshot.local")
            self._run_git("config", "user.name", "PraisonAI Snapshot")
            
            # Create initial empty commit
            self._run_git("commit", "--allow-empty", "-m", "Initial snapshot")
        
        self._initialized = True
    
    def _sync_files(self):
        """Sync project files to shadow repository."""
        self._ensure_initialized()
        
        # Get list of files to track (respecting .gitignore if exists)
        files_to_track = []
        gitignore_path = os.path.join(self.project_path, ".gitignore")
        ignore_patterns = set()
        
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignore_patterns.add(line)
        
        # Always ignore common patterns
        ignore_patterns.update([
            ".git",
            "__pycache__",
            "*.pyc",
            ".DS_Store",
            "node_modules",
            ".env",
            "venv",
            ".venv",
        ])
        
        # Walk project and copy files
        for root, dirs, files in os.walk(self.project_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if not self._should_ignore(d, ignore_patterns)]
            
            rel_root = os.path.relpath(root, self.project_path)
            
            for file in files:
                if self._should_ignore(file, ignore_patterns):
                    continue
                
                src_path = os.path.join(root, file)
                if rel_root == ".":
                    rel_path = file
                else:
                    rel_path = os.path.join(rel_root, file)
                
                dst_path = os.path.join(self.shadow_path, rel_path)
                
                # Create directory if needed
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                
                # Copy file
                try:
                    shutil.copy2(src_path, dst_path)
                    files_to_track.append(rel_path)
                except (IOError, OSError) as e:
                    logger.warning(f"Failed to copy {src_path}: {e}")
        
        return files_to_track
    
    def _should_ignore(self, name: str, patterns: set) -> bool:
        """Check if a file/directory should be ignored."""
        for pattern in patterns:
            if pattern.startswith("*."):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
        return False
    
    def track(self, message: Optional[str] = None) -> SnapshotInfo:
        """
        Track the current state of the project.
        
        Args:
            message: Optional commit message
            
        Returns:
            SnapshotInfo with the commit details
        """
        self._ensure_initialized()
        
        # Sync files
        files = self._sync_files()
        
        # Stage all changes
        self._run_git("add", "-A")
        
        # Check if there are changes
        status = self._run_git("status", "--porcelain")
        if not status.stdout.strip():
            # No changes, return current HEAD
            head = self._run_git("rev-parse", "HEAD")
            return SnapshotInfo(
                commit_hash=head.stdout.strip(),
                session_id=self.session_id,
                message="No changes",
                files_changed=0,
            )
        
        # Commit changes
        commit_msg = message or f"Snapshot at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        self._run_git("commit", "-m", commit_msg)
        
        # Get commit hash
        head = self._run_git("rev-parse", "HEAD")
        commit_hash = head.stdout.strip()
        
        # Get stats
        stats = self._run_git("diff", "--stat", "HEAD~1", "HEAD", check=False)
        additions = 0
        deletions = 0
        files_changed = 0
        
        for line in stats.stdout.split("\n"):
            if "insertion" in line or "deletion" in line:
                parts = line.split(",")
                for part in parts:
                    if "insertion" in part:
                        try:
                            additions = int(part.strip().split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "deletion" in part:
                        try:
                            deletions = int(part.strip().split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "file" in part:
                        try:
                            files_changed = int(part.strip().split()[0])
                        except (ValueError, IndexError):
                            pass
        
        return SnapshotInfo(
            commit_hash=commit_hash,
            session_id=self.session_id,
            message=commit_msg,
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
        )
    
    def diff(self, from_hash: str, to_hash: Optional[str] = None) -> List[FileDiff]:
        """
        Get diff between two snapshots.
        
        Args:
            from_hash: Starting commit hash
            to_hash: Ending commit hash (defaults to HEAD)
            
        Returns:
            List of FileDiff objects
        """
        self._ensure_initialized()
        
        to_hash = to_hash or "HEAD"
        
        # Get list of changed files
        result = self._run_git("diff", "--name-status", from_hash, to_hash, check=False)
        
        diffs = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            
            status_code = parts[0]
            file_path = parts[1]
            
            # Map status code
            if status_code.startswith("A"):
                status = "added"
            elif status_code.startswith("D"):
                status = "deleted"
            else:
                status = "modified"
            
            # Get detailed diff for this file
            file_diff = self._run_git(
                "diff", from_hash, to_hash, "--", file_path,
                check=False
            )
            
            # Count additions/deletions
            additions = 0
            deletions = 0
            for diff_line in file_diff.stdout.split("\n"):
                if diff_line.startswith("+") and not diff_line.startswith("+++"):
                    additions += 1
                elif diff_line.startswith("-") and not diff_line.startswith("---"):
                    deletions += 1
            
            diffs.append(FileDiff(
                path=file_path,
                additions=additions,
                deletions=deletions,
                diff_content=file_diff.stdout,
                status=status,
            ))
        
        return diffs
    
    def restore(self, commit_hash: str, files: Optional[List[str]] = None) -> bool:
        """
        Restore files from a snapshot.
        
        Args:
            commit_hash: The commit hash to restore from
            files: Optional list of specific files to restore
            
        Returns:
            True if successful
        """
        self._ensure_initialized()
        
        try:
            if files:
                # Restore specific files
                for file_path in files:
                    # Checkout file from shadow repo
                    self._run_git("checkout", commit_hash, "--", file_path)
                    
                    # Copy to project
                    src = os.path.join(self.shadow_path, file_path)
                    dst = os.path.join(self.project_path, file_path)
                    
                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
            else:
                # Restore all files
                self._run_git("checkout", commit_hash, "--", ".")
                
                # Copy all files back to project
                for root, dirs, files_list in os.walk(self.shadow_path):
                    # Skip .git directory
                    if ".git" in root:
                        continue
                    
                    rel_root = os.path.relpath(root, self.shadow_path)
                    
                    for file in files_list:
                        if rel_root == ".":
                            rel_path = file
                        else:
                            rel_path = os.path.join(rel_root, file)
                        
                        src = os.path.join(root, file)
                        dst = os.path.join(self.project_path, rel_path)
                        
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
            
            return True
        except Exception as e:
            logger.error(f"Failed to restore: {e}")
            return False
    
    def revert(self, file_path: str) -> bool:
        """
        Revert a single file to its last tracked state.
        
        Args:
            file_path: Path to the file to revert
            
        Returns:
            True if successful
        """
        return self.restore("HEAD", files=[file_path])
    
    def list_snapshots(self, limit: int = 50) -> List[SnapshotInfo]:
        """
        List recent snapshots.
        
        Args:
            limit: Maximum number of snapshots to return
            
        Returns:
            List of SnapshotInfo objects
        """
        self._ensure_initialized()
        
        result = self._run_git(
            "log", f"-{limit}", "--format=%H|%s|%at",
            check=False
        )
        
        snapshots = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    snapshots.append(SnapshotInfo(
                        commit_hash=parts[0],
                        message=parts[1],
                        created_at=float(parts[2]),
                        session_id=self.session_id,
                    ))
                except (ValueError, IndexError):
                    pass
        
        return snapshots
    
    def get_current_hash(self) -> str:
        """Get the current HEAD commit hash."""
        self._ensure_initialized()
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()
    
    def cleanup(self):
        """Remove the shadow repository."""
        if os.path.exists(self.shadow_path):
            shutil.rmtree(self.shadow_path)
            self._initialized = False
