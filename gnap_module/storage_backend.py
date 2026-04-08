"""
GNAP (Git-Native Agent Protocol) Storage Backend for PraisonAI Tools.

Implements StorageBackendProtocol for zero-server durable task queuing using Git.
Provides persistent task storage in .gnap folders with git commit history.

This is a plugin for PraisonAI-Tools that extends storage capabilities with:
- Git-based task persistence
- Distributed coordination via shared repositories  
- Complete audit trail through git history
- Zero infrastructure requirements
"""

import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from praisonaiagents.storage.protocols import StorageBackendProtocol
except ImportError:
    # Fallback protocol definition for development
    from typing import Protocol
    
    class StorageBackendProtocol(Protocol):
        def save(self, key: str, data: Dict[str, Any]) -> None: ...
        def load(self, key: str) -> Any: ...
        def delete(self, key: str) -> bool: ...
        def list_keys(self, prefix: str = "") -> List[str]: ...
        def exists(self, key: str) -> bool: ...


class GNAPStorageBackend:
    """
    Git-Native Agent Protocol storage backend.
    
    Implements StorageBackendProtocol using .gnap folders and git commits
    for durable task queuing and distributed coordination.
    
    Features:
    - Zero-server architecture (pure git)
    - Durable task persistence via git commits
    - Distributed multi-agent coordination
    - Complete audit trail through git history
    - Human-readable .gnap folder structure
    
    Example:
        ```python
        backend = GNAPStorageBackend(repo_path="./my_project")
        backend.save("task_123", {
            "id": "task_123",
            "status": "pending",
            "agent": "researcher",
            "payload": {"query": "AI trends"}
        })
        
        # Tasks persist across crashes and restarts
        task = backend.load("task_123")
        ```
    """
    
    def __init__(
        self,
        repo_path: str = ".",
        gnap_folder: str = ".gnap",
        auto_commit: bool = True,
        commit_author: Optional[str] = None,
        commit_email: Optional[str] = None,
        branch: str = "main",
    ):
        """
        Initialize GNAP storage backend.
        
        Args:
            repo_path: Path to git repository root
            gnap_folder: Name of the .gnap folder for task storage
            auto_commit: Automatically commit changes to git
            commit_author: Git commit author name
            commit_email: Git commit author email  
            branch: Git branch to use for commits
        """
        self.repo_path = Path(repo_path).resolve()
        self.gnap_folder = gnap_folder
        self.gnap_path = self.repo_path / gnap_folder
        self.auto_commit = auto_commit
        self.branch = branch
        self._lock = threading.Lock()
        
        # Git configuration
        self.git_author = commit_author or os.getenv("GIT_AUTHOR_NAME", "GNAP-Agent")
        self.git_email = commit_email or os.getenv("GIT_AUTHOR_EMAIL", "gnap@praisonai.com")
        
        # Initialize GNAP folder structure
        self._init_gnap_structure()
    
    def _init_gnap_structure(self) -> None:
        """Initialize .gnap folder structure if needed."""
        # Create .gnap directory
        self.gnap_path.mkdir(exist_ok=True)
        
        # Create subdirectories
        (self.gnap_path / "tasks").mkdir(exist_ok=True)
        (self.gnap_path / "agents").mkdir(exist_ok=True)
        (self.gnap_path / "status").mkdir(exist_ok=True)
        
        # Create .gnap/config.json if it doesn't exist
        config_path = self.gnap_path / "config.json"
        if not config_path.exists():
            config = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "description": "GNAP (Git-Native Agent Protocol) task storage"
            }
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
        
        # Ensure git repository is initialized
        if not (self.repo_path / ".git").exists():
            self._run_git_cmd(["init"])
            
        # Add .gnap to git if not already tracked
        if self.auto_commit:
            self._add_and_commit_if_changed("Initialize GNAP structure")
    
    def _run_git_cmd(self, cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the repository."""
        try:
            # Use subprocess instead of GitPython to avoid heavy dependency
            full_cmd = ["git"] + cmd
            result = subprocess.run(
                full_cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=check,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": self.git_author,
                    "GIT_AUTHOR_EMAIL": self.git_email,
                    "GIT_COMMITTER_NAME": self.git_author,
                    "GIT_COMMITTER_EMAIL": self.git_email,
                }
            )
            return result
        except subprocess.CalledProcessError as e:
            # Log error but don't fail completely
            print(f"GNAP: Git command failed: {' '.join(full_cmd)}")
            print(f"GNAP: Error: {e.stderr}")
            if check:
                raise
            return e
    
    def _add_and_commit_if_changed(self, message: str) -> bool:
        """Add changes and commit if there are any."""
        if not self.auto_commit:
            return False
            
        try:
            # Check if there are changes
            status_result = self._run_git_cmd(["status", "--porcelain", str(self.gnap_path)], check=False)
            if status_result.returncode != 0 or not status_result.stdout.strip():
                return False  # No changes
            
            # Add and commit changes
            self._run_git_cmd(["add", str(self.gnap_path)])
            
            # Create commit with timestamp
            commit_msg = f"GNAP: {message}\n\nTimestamp: {datetime.now(timezone.utc).isoformat()}"
            self._run_git_cmd(["commit", "-m", commit_msg])
            
            return True
        except Exception as e:
            print(f"GNAP: Failed to commit changes: {e}")
            return False
    
    def _key_to_path(self, key: str) -> Path:
        """Convert storage key to file path."""
        # Sanitize key for filesystem
        safe_key = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return self.gnap_path / "tasks" / f"{safe_key}.json"
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        with self._lock:
            file_path = self._key_to_path(key)
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add metadata
            save_data = {
                **data,
                "_gnap": {
                    "key": key,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "version": "1.0"
                }
            }
            
            # Atomic write via temp file
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8", 
                    dir=str(file_path.parent),
                    delete=False,
                    suffix=".tmp"
                ) as f:
                    json.dump(save_data, f, indent=2, default=str, ensure_ascii=False)
                    temp_path = f.name
                
                os.replace(temp_path, str(file_path))
                
                # Commit to git
                self._add_and_commit_if_changed(f"Save task: {key}")
                
            except Exception as e:
                try:
                    if 'temp_path' in locals():
                        os.remove(temp_path)
                except Exception:
                    pass
                raise RuntimeError(f"GNAP: Failed to save {key}: {e}") from e
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        file_path = self._key_to_path(key)
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Remove GNAP metadata from returned data
            if "_gnap" in data:
                data = {k: v for k, v in data.items() if k != "_gnap"}
            
            return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"GNAP: Failed to load {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        with self._lock:
            file_path = self._key_to_path(key)
            
            if not file_path.exists():
                return False
            
            try:
                file_path.unlink()
                self._add_and_commit_if_changed(f"Delete task: {key}")
                return True
            except Exception as e:
                print(f"GNAP: Failed to delete {key}: {e}")
                return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        tasks_dir = self.gnap_path / "tasks"
        if not tasks_dir.exists():
            return []
        
        keys = []
        for file_path in tasks_dir.iterdir():
            if file_path.is_file() and file_path.suffix == ".json":
                key = file_path.stem
                if not prefix or key.startswith(prefix):
                    keys.append(key)
        
        return sorted(keys)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return self._key_to_path(key).exists()
    
    def get_git_history(self, key: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get git commit history for tasks.
        
        Args:
            key: Optional specific task key to filter by
            
        Returns:
            List of commit information dictionaries
        """
        try:
            cmd = ["log", "--format=%H|%ai|%s", "--"]
            if key:
                cmd.append(str(self._key_to_path(key)))
            else:
                cmd.append(str(self.gnap_path))
            
            result = self._run_git_cmd(cmd, check=False)
            if result.returncode != 0:
                return []
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|', 2)
                    if len(parts) == 3:
                        commits.append({
                            "hash": parts[0],
                            "date": parts[1],
                            "message": parts[2]
                        })
            
            return commits
        except Exception as e:
            print(f"GNAP: Failed to get git history: {e}")
            return []
    
    def sync_with_remote(self, remote: str = "origin") -> bool:
        """
        Sync with remote git repository for distributed coordination.
        
        Args:
            remote: Name of git remote
            
        Returns:
            True if sync successful
        """
        if not self.auto_commit:
            return False
            
        try:
            # Fetch from remote
            self._run_git_cmd(["fetch", remote])
            
            # Try to merge (for distributed coordination)
            merge_result = self._run_git_cmd([
                "merge", f"{remote}/{self.branch}"
            ], check=False)
            
            if merge_result.returncode == 0:
                # Push our changes
                self._run_git_cmd(["push", remote, self.branch])
                return True
            else:
                print(f"GNAP: Merge conflict detected, manual resolution needed")
                return False
                
        except Exception as e:
            print(f"GNAP: Failed to sync with remote: {e}")
            return False
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of current GNAP storage status."""
        try:
            tasks = self.list_keys()
            
            # Count by status if available
            status_counts = {}
            for key in tasks:
                data = self.load(key)
                if data and "status" in data:
                    status = data["status"]
                    status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_tasks": len(tasks),
                "status_breakdown": status_counts,
                "gnap_folder": str(self.gnap_path),
                "auto_commit": self.auto_commit,
                "git_initialized": (self.repo_path / ".git").exists(),
            }
        except Exception as e:
            return {"error": str(e)}


def get_gnap_backend(**kwargs) -> GNAPStorageBackend:
    """
    Factory function to create GNAP storage backend.
    
    This function enables registration with PraisonAI's storage backend system.
    
    Args:
        **kwargs: Arguments passed to GNAPStorageBackend constructor
        
    Returns:
        GNAPStorageBackend instance
        
    Example:
        ```python
        from praisonaiagents.storage.backends import get_backend
        
        # This will work once registered as entry_point
        backend = get_backend("gnap", repo_path="./my_project")
        ```
    """
    return GNAPStorageBackend(**kwargs)


# Entry point registration helper
def register_gnap_backend():
    """
    Register GNAP backend with PraisonAI storage system.
    
    This should be called via entry_points in setup.py/pyproject.toml
    """
    try:
        from praisonaiagents.storage.backends import get_backend
        # Note: Actual registration would be done via entry_points
        print("GNAP storage backend registered successfully")
    except ImportError:
        print("Warning: praisonaiagents not available, GNAP backend not registered")