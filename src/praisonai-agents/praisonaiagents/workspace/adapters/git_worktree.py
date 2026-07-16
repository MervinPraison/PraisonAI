"""Git-worktree isolation adapter.

Provisions a real ``git worktree`` on a fresh branch per run so concurrent
agents each get an independent working directory + branch. Uses only the
standard-library :mod:`subprocess` (lazily imported) — no new dependencies.

Degrades gracefully to the original directory when the workspace is not a git
repository or git is unavailable.
"""

import re
from pathlib import Path


def _slugify(name: str) -> str:
    """Return a git-ref-safe slug for ``name``."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    return slug or "run"


class GitWorktreeAdapter:
    """Per-run isolation via ``git worktree``.

    Each ``create(name)`` provisions a worktree at ``<worktrees_dir>/<slug>`` on
    a fresh branch ``<branch_prefix>/<slug>``. ``reset`` runs ``git clean -ffdx``;
    ``remove`` tears down the worktree and its branch.

    When the root is not a git repository (or git is missing), the adapter
    degrades to returning the original root and all operations become no-ops,
    so callers can use it unconditionally.
    """

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        branch_prefix: str = "praisonai",
        worktrees_dir: str | Path | None = None,
    ):
        self._root = Path(root).resolve() if root is not None else Path.cwd()
        self._branch_prefix = branch_prefix.strip("/") or "praisonai"
        if worktrees_dir is not None:
            self._worktrees_dir = Path(worktrees_dir).resolve()
        else:
            self._worktrees_dir = self._root / ".praisonai" / "worktrees"
        self._available = self._is_git_repo()

    @property
    def available(self) -> bool:
        """Whether git-worktree isolation is available for this root."""
        return self._available

    def _git(self, *args: str, cwd: Path | None = None):
        import subprocess

        return subprocess.run(
            ["git", *args],
            cwd=str(cwd or self._root),
            capture_output=True,
            text=True,
        )

    def _is_git_repo(self) -> bool:
        try:
            result = self._git("rev-parse", "--is-inside-work-tree")
        except (FileNotFoundError, OSError):
            return False
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _branch(self, name: str) -> str:
        return f"{self._branch_prefix}/{_slugify(name)}"

    def path(self, name: str) -> str:
        if not self._available:
            return str(self._root)
        return str(self._worktrees_dir / _slugify(name))

    def create(self, name: str) -> str:
        if not self._available:
            return str(self._root)

        target = Path(self.path(name))
        if target.exists():
            return str(target)

        self._worktrees_dir.mkdir(parents=True, exist_ok=True)

        slug = _slugify(name)
        base_branch = self._branch(name)
        # Unique-name retries so concurrent runs never collide on a branch name.
        for attempt in range(100):
            branch = base_branch if attempt == 0 else f"{base_branch}-{attempt}"
            candidate = target if attempt == 0 else self._worktrees_dir / f"{slug}-{attempt}"
            if candidate.exists():
                continue
            result = self._git(
                "worktree", "add", "-b", branch, str(candidate), "HEAD"
            )
            if result.returncode == 0:
                return str(candidate)
        # Fall back to the original root if a worktree could not be created.
        return str(self._root)

    def reset(self, name: str) -> None:
        if not self._available:
            return
        target = Path(self.path(name))
        if target.exists():
            self._git("clean", "-ffdx", cwd=target)
            self._git("checkout", "--", ".", cwd=target)

    def remove(self, name: str) -> None:
        if not self._available:
            return
        target = Path(self.path(name))
        if target.exists():
            self._git("worktree", "remove", "--force", str(target))
        # Best-effort branch cleanup; ignore failure if branch is checked out elsewhere.
        self._git("branch", "-D", self._branch(name))
