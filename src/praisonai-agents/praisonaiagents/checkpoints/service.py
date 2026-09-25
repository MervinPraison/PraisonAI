"""
Checkpoint Service for PraisonAI Agents.

Implements shadow git repository for file-level checkpointing.
"""

import os
import re
import asyncio
from praisonaiagents._logging import get_logger
import shutil
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path

from .types import (
    CheckpointConfig, Checkpoint, CheckpointDiff, FileDiff,
    CheckpointResult, CheckpointEvent
)

logger = get_logger(__name__)

def _parse_iso_timestamp(timestamp: str) -> datetime:
    """Parse ISO format timestamp, handling 'Z' suffix for Python 3.9 compatibility."""
    # Python 3.9's fromisoformat() doesn't support 'Z' suffix
    if timestamp.endswith('Z'):
        timestamp = timestamp[:-1] + '+00:00'
    return datetime.fromisoformat(timestamp)

# Prefix used to encode a step index into a checkpoint message so per-step
# checkpoints can be rewound with restore(step=N) without any extra storage.
_STEP_TAG_RE = re.compile(r"^\[step-(\d+)\]\s*")


def _extract_step(message: str) -> Optional[int]:
    """Return the step index encoded in a checkpoint message, or None."""
    match = _STEP_TAG_RE.match(message or "")
    return int(match.group(1)) if match else None


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
            storage_dir="~/.praisonai/checkpoints"
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
        max_checkpoints: int = 100,
        user_name: str = "PraisonAI Checkpoints",
        user_email: str = "checkpoints@praison.ai",
        max_file_size: int = 2 * 1024 * 1024,
    ):
        """
        Initialize the checkpoint service.
        
        Args:
            workspace_dir: Directory to track
            storage_dir: Where to store checkpoint data
            enabled: Whether checkpoints are enabled
            auto_checkpoint: Auto-checkpoint before file modifications
            max_checkpoints: Maximum checkpoints to keep
            user_name: Git user.name for commits (default: "PraisonAI Checkpoints")
            user_email: Git user.email for commits (default: "checkpoints@praison.ai")
            max_file_size: Skip staging files larger than this many bytes
                (default 2 MB); 0 disables the cap.
        """
        self.config = CheckpointConfig(
            workspace_dir=workspace_dir,
            storage_dir=storage_dir,
            enabled=enabled,
            auto_checkpoint=auto_checkpoint,
            max_checkpoints=max_checkpoints,
            user_name=user_name,
            user_email=user_email,
            max_file_size=max_file_size,
        )
        
        self._initialized = False
        # Save counter used to run `git gc --auto` on a bounded cadence so the
        # shadow object store is periodically pruned during long sessions.
        self._saves_since_gc = 0
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
    
    async def _get_project_objects_dir(self) -> Optional[str]:
        """
        Return the object database directory of the project's real git repo if
        the workspace is inside one, else None.

        Uses ``--git-common-dir`` so worktrees resolve to the shared object
        store. Best-effort: any failure (no git, not a repo) returns None so the
        shadow repo falls back to the standalone path unchanged.
        """
        try:
            env = self._get_sanitized_env()
            for flag in ("--git-common-dir", "--git-dir"):
                process = await asyncio.create_subprocess_exec(
                    "git", "rev-parse", flag,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=self.config.workspace_dir,
                )
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
                if process.returncode != 0:
                    continue
                git_dir = stdout.decode().strip()
                if not git_dir:
                    continue
                if not os.path.isabs(git_dir):
                    git_dir = os.path.join(self.config.workspace_dir, git_dir)
                objects_dir = os.path.join(git_dir, "objects")
                if os.path.isdir(objects_dir):
                    return os.path.realpath(objects_dir)
        except Exception as e:
            logger.debug(f"Could not resolve project git objects dir: {e}")
        return None

    async def _apply_large_repo_config(self) -> None:
        """
        Apply large-repo git settings so index writes and untracked scans stay
        fast. Each setting is best-effort: older git versions may not support
        every key, and a failure must never break checkpointing.
        """
        settings = [
            ("feature.manyFiles", "true"),
            ("index.version", "4"),
            ("core.untrackedCache", "true"),
            ("core.fsmonitor", "true"),
        ]
        for key, value in settings:
            try:
                await self._run_git("config", key, value)
            except Exception as e:
                logger.debug(f"Skipping large-repo config {key}={value}: {e}")

    async def _seed_from_project_objects(self, objects_dir: str) -> bool:
        """
        Point the shadow object store at the project's objects via a file-based
        ``objects/info/alternates`` so new blobs resolve against existing
        objects instead of being re-hashed and re-stored.

        A file is used (not GIT_ALTERNATE_OBJECT_DIRECTORIES) because
        ``_get_sanitized_env`` strips that env var. Returns True on success.
        """
        try:
            info_dir = os.path.join(self.git_dir, "objects", "info")
            os.makedirs(info_dir, exist_ok=True)
            with open(os.path.join(info_dir, "alternates"), "w") as f:
                f.write(f"{objects_dir}\n")
            logger.debug(f"Seeded shadow git objects from {objects_dir}")
            return True
        except Exception as e:
            logger.debug(f"Could not seed shadow git from project objects: {e}")
            return False

    async def _init_shadow_git(self) -> bool:
        """Initialize the shadow git repository."""
        try:
            # Initialize git repo
            await self._run_git("init")
            
            # Configure git with user-provided or default identity
            await self._run_git("config", "user.name", self.config.user_name)
            await self._run_git("config", "user.email", self.config.user_email)
            
            # Set worktree to workspace
            await self._run_git("config", "core.worktree", self.config.workspace_dir)

            # Seed objects from the project's real repo (if any) so the first
            # checkpoint only stores changed files, and tune for large repos.
            # Both are best-effort: no real repo → unchanged standalone path.
            objects_dir = await self._get_project_objects_dir()
            if objects_dir and objects_dir != os.path.realpath(
                os.path.join(self.git_dir, "objects")
            ):
                await self._seed_from_project_objects(objects_dir)
            await self._apply_large_repo_config()

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
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError(f"Git command timed out after 30 seconds: {' '.join(args)}")
        
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

    async def _unstage_oversized_files(self) -> None:
        """
        Remove files larger than ``config.max_file_size`` from the index so they
        are not committed into the shadow store. Best-effort: any failure leaves
        staging exactly as ``git add -A`` produced it and never breaks the turn.
        """
        max_size = self.config.max_file_size
        if not max_size or max_size <= 0:
            return
        try:
            # NUL-delimited so paths with spaces/newlines are handled safely.
            staged = await self._run_git("diff", "--cached", "--name-only", "-z")
            for path in staged.split("\0"):
                if not path:
                    continue
                abs_path = os.path.join(self.config.workspace_dir, path)
                try:
                    if os.path.isfile(abs_path) and os.path.getsize(abs_path) > max_size:
                        # Keep the file on disk; only drop it from the index.
                        await self._run_git("rm", "--cached", "--quiet", "--", path)
                        logger.debug(f"Skipped oversized file from checkpoint: {path}")
                except Exception as e:
                    logger.debug(f"Could not evaluate size of {path}: {e}")
        except Exception as e:
            logger.debug(f"Oversized-file skip pass failed (continuing): {e}")

    async def _maybe_gc(self, cadence: int = 20) -> None:
        """
        Run ``git gc --auto`` on the shadow repo every ``cadence`` saves so loose
        objects get packed and unreachable ones pruned. ``--auto`` makes git
        decide whether work is actually needed, keeping the amortised cost low.
        Best-effort: failures are swallowed so a gc issue never breaks a turn.
        """
        self._saves_since_gc += 1
        if self._saves_since_gc < cadence:
            return
        self._saves_since_gc = 0
        try:
            await self._run_git("gc", "--auto", "--quiet")
        except Exception as e:
            logger.debug(f"Shadow-store gc skipped: {e}")
    
    async def save(
        self,
        message: str,
        allow_empty: bool = False,
        step: Optional[int] = None,
    ) -> CheckpointResult:
        """
        Save a checkpoint.
        
        Args:
            message: Checkpoint message
            allow_empty: Allow checkpoint even if no changes
            step: Optional step index. When provided, the checkpoint is tagged
                as a per-step checkpoint and can be rewound with
                ``restore(step=...)``.
            
        Returns:
            CheckpointResult with the created checkpoint
        """
        if not self._initialized:
            return CheckpointResult.fail("Service not initialized")
        
        if step is not None and step < 0:
            return CheckpointResult.fail("step must be a non-negative integer")
        
        # Encode the step index into the message so it can be recovered later
        # without any extra storage (reuses the shadow-git commit log). An
        # explicit step always wins: strip any existing tag before prepending
        # so save("[step-2] retry", step=1) is indexed as step 1.
        if step is not None:
            message = f"[step-{step}] {_STEP_TAG_RE.sub('', message)}"
        
        try:
            # Stage all changes
            await self._run_git("add", "-A")

            # Drop oversized files from the index so the shadow store never
            # copies giant blobs (build outputs, model weights, media). This
            # mirrors the existing "never fail the turn" contract: any error
            # here is swallowed and staging proceeds as before.
            await self._unstage_oversized_files()

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
                timestamp=_parse_iso_timestamp(timestamp),
                step=_extract_step(message)
            )
            
            self._checkpoints.append(checkpoint)
            
            # Prune old checkpoints if needed
            await self._prune_checkpoints()

            # Periodically let git pack loose objects and drop unreachable ones
            # so the shadow store doesn't leak disk over a long session. Bounded
            # cadence keeps the per-turn cost near zero; best-effort only.
            await self._maybe_gc()

            self._emit(CheckpointEvent.CHECKPOINT_CREATED, checkpoint)
            logger.info(f"Created checkpoint: {checkpoint.short_id} - {message}")
            
            return CheckpointResult.ok(checkpoint)
            
        except Exception as e:
            error_msg = str(e)
            self._emit(CheckpointEvent.ERROR, {"error": error_msg})
            return CheckpointResult.fail(error_msg)
    
    async def restore(
        self,
        checkpoint_id: Optional[str] = None,
        step: Optional[int] = None,
    ) -> CheckpointResult:
        """
        Restore workspace to a checkpoint.
        
        Args:
            checkpoint_id: Checkpoint ID (commit hash) to restore
            step: Restore the per-step checkpoint tagged with this step index.
                Mutually exclusive with ``checkpoint_id``.
            
        Returns:
            CheckpointResult indicating success/failure
        """
        if not self._initialized:
            return CheckpointResult.fail("Service not initialized")
        
        if checkpoint_id is not None and step is not None:
            return CheckpointResult.fail(
                "Provide either checkpoint_id or step, not both"
            )
        
        if step is not None:
            checkpoint = await self.get_checkpoint_by_step(step)
            if checkpoint is None:
                return CheckpointResult.fail(f"No checkpoint found for step {step}")
            checkpoint_id = checkpoint.id
        
        if checkpoint_id is None:
            return CheckpointResult.fail("No checkpoint id or step provided")
        
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
                timestamp=_parse_iso_timestamp(timestamp),
                step=_extract_step(message)
            )
            
            self._emit(CheckpointEvent.CHECKPOINT_RESTORED, checkpoint)
            logger.info(f"Restored to checkpoint: {checkpoint.short_id}")
            
            return CheckpointResult.ok(checkpoint)
            
        except Exception as e:
            error_msg = str(e)
            self._emit(CheckpointEvent.ERROR, {"error": error_msg})
            return CheckpointResult.fail(error_msg)
    
    async def rewind(self, steps: int = 1) -> CheckpointResult:
        """
        Rewind the workspace back ``steps`` checkpoints from the latest.

        Checkpoints form an ordered sequence (newest first). ``rewind(1)``
        restores the checkpoint immediately before the current one (undoing the
        most recent checkpointed change); ``rewind(n)`` steps back ``n``
        checkpoints.

        Note: a checkpoint is not guaranteed to correspond 1:1 with an agent
        turn — manual saves and auto-checkpoints both create checkpoints — so
        ``steps`` counts checkpoints, which is the closest turn-addressable
        primitive available without persisting a turn↔checkpoint map.

        Args:
            steps: How many checkpoints to step back (must be >= 1).

        Returns:
            CheckpointResult with the checkpoint restored to.
        """
        if not self._initialized:
            return CheckpointResult.fail("Service not initialized")

        if steps < 1:
            return CheckpointResult.fail("steps must be >= 1")

        # Query only as many checkpoints as we need to reach the target.
        # Shadow-git retains every commit (pruning only trims the in-memory
        # list), so we must not cap the lookup at ``max_checkpoints`` or valid
        # older targets would become unreachable.
        checkpoints = await self.list_checkpoints(limit=steps + 1)
        if steps >= len(checkpoints):
            return CheckpointResult.fail(
                f"Cannot rewind {steps} step(s): only {len(checkpoints)} checkpoint(s) available"
            )

        # list_checkpoints is newest-first, so index ``steps`` is the checkpoint
        # ``steps`` positions back from the latest.
        target = checkpoints[steps]
        return await self.restore(target.id)

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
                        timestamp=_parse_iso_timestamp(parts[2]),
                        step=_extract_step(parts[1])
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
        
        # Calculate how many to remove
        num_to_remove = len(self._checkpoints) - self.config.max_checkpoints
        
        # Keep only the most recent checkpoints in memory (newest-last semantics)
        # Since save() appends (newest last), keep the last N entries
        self._checkpoints = self._checkpoints[-self.config.max_checkpoints:]
        
        logger.info(f"Pruned {num_to_remove} old checkpoints to stay under limit of {self.config.max_checkpoints}")
        
        # Emit pruning event for any cleanup hooks
        self._emit(CheckpointEvent.CHECKPOINTS_PRUNED, {"action": "pruned", "removed_count": num_to_remove})
    
    async def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a specific checkpoint by ID."""
        for cp in self._checkpoints:
            if cp.id.startswith(checkpoint_id) or cp.short_id == checkpoint_id:
                return cp
        return None
    
    async def get_checkpoint_by_step(self, step: int) -> Optional[Checkpoint]:
        """Get the most recent checkpoint tagged with the given step index."""
        checkpoints = await self.list_checkpoints(limit=self.config.max_checkpoints)
        for cp in checkpoints:  # newest-first, so returns the latest match
            if cp.step == step:
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
