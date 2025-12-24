"""
Checkpoints Module for PraisonAI Agents.

Provides file-level checkpointing using a shadow git repository to track
and restore file changes made by agents. This enables:

- Automatic checkpointing before file modifications
- Rewind to any previous checkpoint
- Diff between checkpoints
- Restore files and conversation state together

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Checkpoints only created when enabled
- No overhead when checkpoints are disabled

Usage:
    from praisonaiagents.checkpoints import CheckpointService
    
    # Create checkpoint service
    service = CheckpointService(
        workspace_dir="/path/to/project",
        storage_dir="~/.praison/checkpoints"
    )
    
    # Initialize shadow git
    await service.initialize()
    
    # Save a checkpoint
    checkpoint_id = await service.save("Before refactoring")
    
    # Restore to a checkpoint
    await service.restore(checkpoint_id)
    
    # Get diff between checkpoints
    diff = await service.diff(from_id, to_id)
"""

__all__ = [
    # Core service
    "CheckpointService",
    # Data types
    "Checkpoint",
    "CheckpointDiff",
    "CheckpointConfig",
    # Events
    "CheckpointEvent",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "CheckpointService":
        from .service import CheckpointService
        return CheckpointService
    
    if name in ("Checkpoint", "CheckpointDiff", "CheckpointConfig"):
        from .types import Checkpoint, CheckpointDiff, CheckpointConfig
        return locals()[name]
    
    if name == "CheckpointEvent":
        from .types import CheckpointEvent
        return CheckpointEvent
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
