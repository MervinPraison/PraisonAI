"""
GNAP Plugin Implementation.

Implements both PluginProtocol and StorageBackendProtocol for seamless integration
with the PraisonAI plugin system and storage infrastructure.
"""

import os
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Lazy imports for optional dependencies
GitPython = None


class GnapPlugin:
    """
    GNAP Plugin implementing both PluginProtocol and StorageBackendProtocol.
    
    Provides git-native task persistence for distributed multi-agent workflows.
    """
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize GNAP plugin.
        
        Args:
            repo_path: Path to the git repository (default: current directory)
        """
        self.repo_path = Path(repo_path).resolve()
        self._repo = None
        self._lock = threading.Lock()
        self._initialized = False
    
    # PluginProtocol implementation
    @property
    def name(self) -> str:
        """Get the plugin name."""
        return "gnap"
    
    @property
    def version(self) -> str:
        """Get the plugin version."""
        return "1.0.0"
    
    def on_init(self, context: Dict[str, Any]) -> None:
        """Called when plugin is initialized."""
        self._initialize_repo()
        self._initialized = True
    
    def on_shutdown(self) -> None:
        """Called when plugin is shutting down."""
        if self._repo:
            self._repo.close()
    
    # StorageBackendProtocol implementation
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with automatic git commit."""
        if not self._initialized:
            self._initialize_repo()
            
        with self._lock:
            # Create .gnap directory if it doesn't exist
            gnap_dir = self.repo_path / ".gnap" / "tasks"
            gnap_dir.mkdir(parents=True, exist_ok=True)
            
            # Add GNAP metadata
            gnap_data = {
                "_gnap": {
                    "task_id": key,
                    "timestamp": datetime.utcnow().isoformat(),
                    "branch": self._get_current_branch(),
                    "agent_id": os.getenv("GNAP_AGENT_ID", "default"),
                },
                **data
            }
            
            # Save task data as JSON
            task_file = gnap_dir / f"{key}.json"
            with open(task_file, 'w') as f:
                json.dump(gnap_data, f, indent=2)
            
            # Auto-commit if enabled
            if os.getenv("GNAP_AUTO_COMMIT", "true").lower() == "true":
                self._commit_changes(f"GNAP: Update task {key}")
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        if not self._initialized:
            self._initialize_repo()
            
        task_file = self.repo_path / ".gnap" / "tasks" / f"{key}.json"
        
        if not task_file.exists():
            return None
        
        try:
            with open(task_file, 'r') as f:
                data = json.load(f)
            
            # Remove GNAP metadata from returned data
            data.pop("_gnap", None)
            return data
        except (json.JSONDecodeError, IOError):
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        if not self._initialized:
            self._initialize_repo()
            
        task_file = self.repo_path / ".gnap" / "tasks" / f"{key}.json"
        
        if not task_file.exists():
            return False
        
        with self._lock:
            try:
                task_file.unlink()
                
                # Auto-commit if enabled
                if os.getenv("GNAP_AUTO_COMMIT", "true").lower() == "true":
                    self._commit_changes(f"GNAP: Delete task {key}")
                
                return True
            except OSError:
                return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all task keys, optionally filtered by prefix."""
        if not self._initialized:
            self._initialize_repo()
            
        tasks_dir = self.repo_path / ".gnap" / "tasks"
        
        if not tasks_dir.exists():
            return []
        
        keys = []
        for task_file in tasks_dir.glob("*.json"):
            key = task_file.stem
            if not prefix or key.startswith(prefix):
                keys.append(key)
        
        return sorted(keys)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if not self._initialized:
            self._initialize_repo()
            
        task_file = self.repo_path / ".gnap" / "tasks" / f"{key}.json"
        return task_file.exists()
    
    # GNAP-specific methods
    def get_storage_backend(self):
        """Get this plugin as a storage backend."""
        return self
    
    def get_task_history(self, key: str) -> List[Dict[str, Any]]:
        """Get the git history for a specific task."""
        if not self._repo:
            return []
        
        try:
            task_file = f".gnap/tasks/{key}.json"
            commits = list(self._repo.iter_commits(paths=task_file, max_count=50))
            
            history = []
            for commit in commits:
                history.append({
                    "commit_hash": commit.hexsha[:8],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "timestamp": datetime.fromtimestamp(commit.committed_date).isoformat(),
                })
            
            return history
        except Exception:
            return []
    
    def create_workflow_branch(self, workflow_id: str) -> str:
        """Create a new branch for workflow isolation."""
        if not self._repo:
            self._initialize_repo()
        
        branch_name = f"gnap-workflow-{workflow_id}"
        
        try:
            # Create and checkout new branch
            new_branch = self._repo.create_head(branch_name)
            new_branch.checkout()
            return branch_name
        except Exception:
            # Branch might already exist
            try:
                self._repo.heads[branch_name].checkout()
                return branch_name
            except Exception:
                return self._get_current_branch()
    
    def merge_workflow_to_main(self, workflow_branch: str) -> bool:
        """Merge completed workflow branch back to main."""
        if not self._repo:
            return False
        
        try:
            # Switch to main branch
            main_branch = self._repo.heads.main if "main" in [h.name for h in self._repo.heads] else self._repo.heads.master
            main_branch.checkout()
            
            # Merge workflow branch
            workflow_head = self._repo.heads[workflow_branch]
            self._repo.git.merge(workflow_head.commit)
            
            # Delete workflow branch
            self._repo.delete_head(workflow_head)
            
            return True
        except Exception:
            return False
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of all tasks and their statuses."""
        if not self._initialized:
            self._initialize_repo()
        
        summary = {
            "total_tasks": 0,
            "by_status": {},
            "by_agent": {},
            "recent_activity": []
        }
        
        for key in self.list_keys():
            # Load task data including GNAP metadata
            task_file = self.repo_path / ".gnap" / "tasks" / f"{key}.json"
            
            try:
                with open(task_file, 'r') as f:
                    data = json.load(f)
                
                summary["total_tasks"] += 1
                
                # Count by status
                status = data.get("status", "unknown")
                summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
                
                # Count by agent
                agent_id = data.get("_gnap", {}).get("agent_id", "unknown")
                summary["by_agent"][agent_id] = summary["by_agent"].get(agent_id, 0) + 1
                
                # Add to recent activity
                timestamp = data.get("_gnap", {}).get("timestamp")
                if timestamp:
                    summary["recent_activity"].append({
                        "task_id": key,
                        "status": status,
                        "timestamp": timestamp,
                        "agent_id": agent_id
                    })
            except (json.JSONDecodeError, IOError):
                continue
        
        # Sort recent activity by timestamp
        summary["recent_activity"].sort(key=lambda x: x["timestamp"], reverse=True)
        summary["recent_activity"] = summary["recent_activity"][:10]  # Keep only last 10
        
        return summary
    
    # Private methods
    def _initialize_repo(self) -> None:
        """Initialize or open git repository."""
        global GitPython
        if GitPython is None:
            try:
                import git as GitPython
            except ImportError:
                raise ImportError(
                    "GitPython is required for GNAP. Install with: pip install praisonai-tools[gnap]"
                )
        
        try:
            # Try to open existing repo
            self._repo = GitPython.Repo(self.repo_path)
        except GitPython.InvalidGitRepositoryError:
            # Initialize new repo
            self._repo = GitPython.Repo.init(self.repo_path)
            
            # Create initial commit if repo is empty
            if not list(self._repo.iter_commits()):
                # Create .gnap directory structure
                gnap_dir = self.repo_path / ".gnap"
                gnap_dir.mkdir(exist_ok=True)
                (gnap_dir / "tasks").mkdir(exist_ok=True)
                
                # Create config file
                config_file = gnap_dir / "config.json"
                config = {
                    "version": "1.0",
                    "created": datetime.utcnow().isoformat(),
                    "description": "GNAP (Git-Native Agent Persistence) configuration"
                }
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                
                # Initial commit
                self._repo.index.add([str(config_file.relative_to(self.repo_path))])
                self._repo.index.commit("Initial GNAP setup")
    
    def _get_current_branch(self) -> str:
        """Get the current git branch name."""
        if not self._repo:
            return "main"
        
        try:
            return self._repo.active_branch.name
        except Exception:
            return "main"
    
    def _commit_changes(self, message: str) -> None:
        """Commit pending changes to git."""
        if not self._repo:
            return
        
        try:
            # Add all changes in .gnap directory
            gnap_files = list(self.repo_path.rglob(".gnap/**/*"))
            relative_paths = []
            
            for file_path in gnap_files:
                if file_path.is_file():
                    relative_paths.append(str(file_path.relative_to(self.repo_path)))
            
            if relative_paths:
                self._repo.index.add(relative_paths)
                
                # Only commit if there are staged changes
                if self._repo.index.diff("HEAD"):
                    self._repo.index.commit(message)
        except Exception:
            # Silently fail if commit fails (e.g., no changes to commit)
            pass