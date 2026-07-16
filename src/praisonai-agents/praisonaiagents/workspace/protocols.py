"""Protocols for workspace isolation.

Defines the contract for provisioning per-agent/per-run isolated working
directories so concurrent agents can edit the same repository without
clobbering each other's changes.

Implementations live alongside this file:
- ``NoIsolationAdapter`` — default, no isolation (zero overhead).
- ``GitWorktreeAdapter`` — real ``git worktree`` per run (lazy stdlib subprocess).
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class WorkspaceIsolationProtocol(Protocol):
    """Contract for per-run workspace isolation.

    An isolation adapter provisions an isolated working directory for a run,
    reports its path, can reset it to a clean state, and tears it down on
    completion. Adapters must degrade gracefully when isolation is unavailable
    (e.g. cwd is not a git repository) by falling back to the original path.
    """

    def create(self, name: str) -> str:
        """Provision an isolated working directory for ``name`` and return its path.

        Args:
            name: A caller-supplied slug identifying the run/agent.

        Returns:
            Absolute path to the isolated working directory. May return the
            original workspace path when isolation is unavailable.
        """
        ...

    def path(self, name: str) -> str:
        """Return the working-directory path for ``name`` (without creating it)."""
        ...

    def reset(self, name: str) -> None:
        """Reset the isolated working directory for ``name`` to a clean state."""
        ...

    def remove(self, name: str) -> None:
        """Tear down the isolated working directory for ``name``."""
        ...
