"""Workspace isolation adapters."""

from .no_isolation import NoIsolationAdapter
from .git_worktree import GitWorktreeAdapter

__all__ = ["NoIsolationAdapter", "GitWorktreeAdapter"]
