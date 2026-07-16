"""No-isolation adapter — the default, zero-overhead behaviour."""

from pathlib import Path


class NoIsolationAdapter:
    """Default adapter: every run shares the same working directory.

    Implements ``WorkspaceIsolationProtocol`` without provisioning anything, so
    it adds no overhead when isolation is disabled.
    """

    def __init__(self, root: str | Path | None = None):
        self._root = str(Path(root).resolve()) if root is not None else str(Path.cwd())

    def create(self, name: str) -> str:  # noqa: D401 - see protocol
        return self._root

    def path(self, name: str) -> str:
        return self._root

    def reset(self, name: str) -> None:
        return None

    def remove(self, name: str) -> None:
        return None
