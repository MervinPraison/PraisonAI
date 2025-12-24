"""
Checkpoint Service for PraisonAI Agents.

Implements shadow git repository for file-level checkpointing.
"""

import os
import asyncio
import logging
import shutil
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path

from .types import (
    CheckpointConfig, Checkpoint, CheckpointDiff, FileDiff,
    CheckpointResult, CheckpointEvent
)

logger = logging.getLogger(__name__)

# Protected paths that should never be checkpointed
PROTECTED_PATHS = [
    os.path.expanduser("~"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
    "/",
    "/tmp",
    "/var",
    "/etc",
]


class CheckpointService:
    """
    Shadow Git Checkpoint Service.
    
    Uses a separate git repository to track file changes in the workspace,
    enabling checkpoint creation, restoration, and diffing without
    interfering with the workspace's own git repository.
    
    Example:
        service = CheckpointService(
            workspace_dir="/path/to/project",
            storage_dir="~/.praison/checkpoints"
        )
        
        await service.initialize()
        
        # Save checkpoint before making changes
        result = await service.save("Before refactoring")
        
        # Make changes...
        
        # Restore if needed
        await service.restore(result.checkpoint.id)
    """
    
    def __init__(
        self,
        workspace_dir: str,
        storage_dir: Optional[str] = None,
        enabled: bool = True,
        auto_checkpoint: bool = True,
        max_checkpoints: int = 100
    ):
        """
        Initialize the checkpoint service.
        
        Args:
            workspace_dir: Directory to track
            storage_dir: Where to store checkpoint data
            enabled: Whether checkpoints are enabled
            auto_checkpoint: Auto-checkpoint before file modifications
            max_checkpoints: Maximum checkpoints to keep
        """
        self.config = CheckpointConfig(
            workspace_dir=workspace_dir,
            storage_dir=storage_dir,
            enabled=enabled,
            auto_checkpoint=auto_checkpoint,
            max_checkpoints=max_checkpoints
        )
        
        self._initialized = False
        self._checkpoints: List[Checkpoint] = []
        self._event_handlers: Dict[CheckpointEvent, List[Callable]] = {
            event: [] for event in CheckpointEvent
        }
    
    @property
    def workspace_dir(self) -> str:
        """Get the workspace directory."""
        return self.config.workspace_dir
    
    @property
    def checkpoint_dir(self) -> str:
        """Get the checkpoint storage directory."""
        return self.config.get_checkpoint_dir()
    
    @property
    def git_dir(self) -> str:
        """Get the shadow git directory."""
        return os.path.join(self.checkpoint_dir, ".git")
    
    @property
    def is_initialized(self) -> bool:
        """Check if the service is initialized."""
        return self._initialized
    
    def on(self, event: CheckpointEvent, handler: Callable):
        """Register an event handler."""
        self._event_handlers[event].append(handler)
    
    def _emit(self, event: CheckpointEvent, data: Any = None):
        """Emit an event to all handlers."""
        for handler in self._event_handlers[event]:
            try:
                handler(data)
            except Exception as e:
                logger.warning(f"Event handler error: {e}")
    
    async def initialize(self) -> bool:
        """
        Initialize the shadow git repository.
        
        Returns:
            True if initialization succeeded
        """
        if not self.config.enabled:
            return False
        
        # Check for protected paths
        workspace_real = os.path.realpath(self.config.workspace_dir)
        for protected in PROTECTED_PATHS:
            if workspace_real == os.path.realpath(protected):
                logger.warning(f"Cannot checkpoint protected path: {workspace_real}")
                return False
        
        # Check if workspace exists
        if not os.path.isdir(self.config.workspace_dir):
            logger.error(f"Workspace does not exist: {self.config.workspace_dir}")
            return False
        
        # Create checkpoint directory
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        
        # Initialize shadow git if needed
        if not os.path.exists(self.git_dir):
            success = await self._init_shadow_git()
            if not success:
                return False
        
        # Load existing checkpoints
        await self._load_checkpoints()
        
        self._initialized = True
        self._emit(CheckpointEvent.INITIALIZED, {"workspace": self.config.workspace_dir})
        
        return True
    
    async def _init_shadow_git(self) -> bool:
        """Initialize the shadow git repository."""
        try:
            # Initialize git repo
            await self._run_git("init")
            
            # Configure git
            await self._run_git("config", "user.name", "PraisonAI Checkpoints")
            await self._run_git("config", "user.email", "checkpoints@praison.ai")
            
            # Set worktree to workspace
            await self._run_git("config", "core.worktree", self.config.workspace_dir)
            
            # Create exclude file
            exclude_dir = os.path.join(self.git_dir, "info")
            os.makedirs(exclude_dir, exist_ok=True)
            
            exclude_file = os.path.join(exclude_dir, "exclude")
            with open(exclude_file, "w") as f:
                for pattern in self.config.exclude_patterns:
                    f.write(f"{pattern}\n")
                
                # Also exclude the checkpoint directory itself
                f.write(f"{self.checkpoint_dir}\n")
            
            # Create initial empty commit
            await self._run_git("commit", "--allow-empty", "-m", "Initial checkpoint")
            
            logger.info(f"Initialized shadow git at {self.checkpoint_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize shadow git: {e}")
            return False
    
    async def _run_git(self, *args: str) -> str:
        """Run a git command in the shadow repository."""
        env = self._get_sanitized_env()
        
        cmd = ["git", f"--git-dir={self.git_dir}", f"--work-tree={self.config.workspace_dir}"]
        cmd.extend(args)
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.config.workspace_dir
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{error_msg}")
        
        return stdout.decode().strip()
    
    def _get_sanitized_env(self) -> Dict[str, str]:
        """Get environment with git variables sanitized."""
        env = os.environ.copy()
        
        # Remove git environment variables that could interfere
        git_vars = [
            "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"
        ]
        for var in git_vars:
            env.pop(var, None)
        
        return env
    
    async def save(self, message: str, allow_empty: bool = False) -> CheckpointResult:
        """
        Save a checkpoint.
        
        Args:
            message: Checkpoint message
            allow_empty: Allow checkpoint even if no changes
            
        Returns:
            CheckpointResult with the created checkpoint
        """
        if not self._initialized:
            return CheckpointResult.fail("Service not initialized")
        
        try:
            # Stage all changes
            await self._run_git("add", "-A")
            
            # Check if there are changes
            try:
                await self._run_git("diff", "--cached", "--quiet")
                has_changes = False
            except RuntimeError:
                has_changes = True
            
            if not has_changes and not allow_empty:
                return CheckpointResult.fail("No changes to checkpoint")
            
            # Create commit
            commit_args = ["commit", "-m", message]
            if allow_empty:
                commit_args.append("--allow-empty")
            
            await self._run_git(*commit_args)
            
            # Get commit info
            commit_hash = await self._run_git("rev-parse", "HEAD")
            timestamp = await self._run_git("log", "-1", "--format=%aI")
            
            checkpoint = Checkpoint(
                id=commit_hash,
                short_id=commit_hash[:8],
                message=message,
                timestamp=datetime.fromisoformat(timestamp)
            )
            
            self._checkpoints.append(checkpoint)
            
            # Prune old checkpoints if needed
            await self._prune_checkpoints()
            
            self._emit(CheckpointEvent.CHECKPOINT_CREATED, checkpoint)
            logger.info(f"Created checkpoint: {checkpoint.short_id} - {message}")
            
            return CheckpointResult.ok(checkpoint)
            
        except Exception as e:
            error_msg = str(e)
            self._emit(CheckpointEvent.ERROR, {"error": error_msg})
            return CheckpointResult.fail(error_msg)
    
    async def restore(self, checkpoint_id: str) -> CheckpointResult:
        """
        Restore workspace to a checkpoint.
        
        Args:
            checkpoint_id: Checkpoint ID (commit hash) to restore
            
        Returns:
            CheckpointResult indicating success/failure
        """
        if not self._initialized:
            return CheckpointResult.fail("Service not initialized")
        
        try:
            # Clean untracked files
            await self._run_git("clean", "-f", "-d")
            
            # Reset to checkpoint
            await self._run_git("reset", "--hard", checkpoint_id)
            
            # Get checkpoint info
            message = await self._run_git("log", "-1", "--format=%s", checkpoint_id)
            timestamp = await self._run_git("log", "-1", "--format=%aI", checkpoint_id)
            
            checkpoint = Checkpoint(
                id=checkpoint_id,
                short_id=checkpoint_id[:8],
                message=message,
                timestamp=datetime.fromisoformat(timestamp)
            )
            
            self._emit(CheckpointEvent.CHECKPOINT_RESTORED, checkpoint)
            logger.info(f"Restored to checkpoint: {checkpoint.short_id}")
            
            return CheckpointResult.ok(checkpoint)
            
        except Exception as e:
            error_msg = str(e)
            self._emit(CheckpointEvent.ERROR, {"error": error_msg})
            return CheckpointResult.fail(error_msg)
    
    async def diff(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None
    ) -> CheckpointDiff:
        """
        Get diff between checkpoints.
        
        Args:
            from_id: Starting checkpoint (default: previous checkpoint)
            to_id: Ending checkpoint (default: current working directory)
            
        Returns:
            CheckpointDiff with file changes
        """
        if not self._initialized:
            return CheckpointDiff(from_checkpoint="", to_checkpoint="", files=[])
        
        try:
            # Default from_id to HEAD~1
            if from_id is None:
                try:
                    from_id = await self._run_git("rev-parse", "HEAD~1")
                except RuntimeError:
                    from_id = await self._run_git("rev-parse", "HEAD")
            
            # Build diff command
            if to_id:
                diff_output = await self._run_git(
                    "diff", "--stat", "--numstat", from_id, to_id
                )
            else:
                # Diff against working directory
                await self._run_git("add", "-A")  # Stage to include untracked
                diff_output = await self._run_git(
                    "diff", "--stat", "--numstat", "--cached", from_id
                )
            
            # Parse diff output
            files = self._parse_diff_output(diff_output)
            
            return CheckpointDiff(
                from_checkpoint=from_id[:8] if from_id else "",
                to_checkpoint=to_id[:8] if to_id else None,
                files=files
            )
            
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return CheckpointDiff(from_checkpoint="", to_checkpoint="", files=[])
    
    def _parse_diff_output(self, output: str) -> List[FileDiff]:
        """Parse git diff --numstat output."""
        files = []
        
        for line in output.strip().split("\n"):
            if not line or "\t" not in line:
                continue
            
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    additions = int(parts[0]) if parts[0] != "-" else 0
                    deletions = int(parts[1]) if parts[1] != "-" else 0
                    path = parts[2]
                    
                    # Determine status
                    if additions > 0 and deletions == 0:
                        status = "added"
                    elif additions == 0 and deletions > 0:
                        status = "deleted"
                    else:
                        status = "modified"
                    
                    files.append(FileDiff(
                        path=path,
                        absolute_path=os.path.join(self.config.workspace_dir, path),
                        status=status,
                        additions=additions,
                        deletions=deletions
                    ))
                except ValueError:
                    continue
        
        return files
    
    async def list_checkpoints(self, limit: int = 50) -> List[Checkpoint]:
        """
        List all checkpoints.
        
        Args:
            limit: Maximum number of checkpoints to return
            
        Returns:
            List of checkpoints, newest first
        """
        if not self._initialized:
            return []
        
        try:
            # Get commit log
            log_output = await self._run_git(
                "log", f"-{limit}", "--format=%H|%s|%aI"
            )
            
            checkpoints = []
            for line in log_output.strip().split("\n"):
                if not line or "|" not in line:
                    continue
                
                parts = line.split("|", 2)
                if len(parts) >= 3:
                    checkpoints.append(Checkpoint(
                        id=parts[0],
                        short_id=parts[0][:8],
                        message=parts[1],
                        timestamp=datetime.fromisoformat(parts[2])
                    ))
            
            return checkpoints
            
        except Exception as e:
            logger.error(f"Failed to list checkpoints: {e}")
            return []
    
    async def _load_checkpoints(self):
        """Load existing checkpoints from git log."""
        self._checkpoints = await self.list_checkpoints()
    
    async def _prune_checkpoints(self):
        """Prune old checkpoints if over limit."""
        if len(self._checkpoints) <= self.config.max_checkpoints:
            return
        
        # Keep only the most recent checkpoints
        # Note: This doesn't actually delete git history, just our tracking
        self._checkpoints = self._checkpoints[:self.config.max_checkpoints]
    
    async def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a specific checkpoint by ID."""
        for cp in self._checkpoints:
            if cp.id.startswith(checkpoint_id) or cp.short_id == checkpoint_id:
                return cp
        return None
    
    async def cleanup(self):
        """Clean up the checkpoint service."""
        # Nothing to clean up currently
        self._initialized = False
    
    async def delete_all(self) -> bool:
        """Delete all checkpoint data for this workspace."""
        try:
            if os.path.exists(self.checkpoint_dir):
                shutil.rmtree(self.checkpoint_dir)
            self._checkpoints = []
            self._initialized = False
            return True
        except Exception as e:
            logger.error(f"Failed to delete checkpoints: {e}")
            return False
