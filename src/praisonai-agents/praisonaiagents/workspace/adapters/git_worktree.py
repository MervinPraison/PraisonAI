"""Git-worktree isolation adapter.

Provisions a real ``git worktree`` on a fresh branch per run so concurrent
agents each get an independent working directory + branch. Uses only the
standard-library :mod:`subprocess` (lazily imported) — no new dependencies.

Degrades gracefully to the original directory when the workspace is not a git
repository or git is unavailable.
"""

import hashlib
import re
from pathlib import Path


def _slugify(name: str) -> str:
    """Return a git-ref-safe, collision-resistant slug for ``name``.

    A short deterministic hash of the original ``name`` is appended so distinct
    inputs (e.g. ``"agent one"`` vs ``"agent-one"``) never normalise to the same
    slug and accidentally share a worktree.
    """
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.") or "run"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


class GitWorktreeAdapter:
    """Per-run isolation via ``git worktree``.

    Each ``create(name)`` provisions a worktree at ``<worktrees_dir>/<slug>`` on
    a fresh branch ``<branch_prefix>/<slug>`` where ``slug`` is a deterministic,
    collision-resistant function of ``name`` — so ``path``/``reset``/``remove``
    always resolve the exact same target. ``reset`` runs ``git clean -ffdx``;
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
        # Idempotent: an existing worktree for this name is reused as-is.
        if target.exists():
            return str(target)

        self._worktrees_dir.mkdir(parents=True, exist_ok=True)

        # Drop stale worktree registrations whose directories were deleted so a
        # re-create of the same name doesn't fail on leftover bookkeeping.
        self._git("worktree", "prune")

        # ``-B`` resets/reuses a lingering branch of the same name, so the path
        # and branch are a deterministic function of ``name`` — path()/reset()/
        # remove() resolve the exact same target with no dynamic suffixes.
        result = self._git("worktree", "add", "-B", self._branch(name), str(target), "HEAD")
        if result.returncode != 0:
            # Tolerate a concurrent creator that won the race for this path.
            if target.exists():
                return str(target)
            # Fail fast: isolation was requested but could not be provisioned.
            raise RuntimeError(
                f"Failed to create isolated git worktree at {target}: "
                f"{result.stderr.strip()}"
            )
        return str(target)

    def reset(self, name: str) -> None:
        if not self._available:
            return
        target = Path(self.path(name))
        if not target.exists():
            return
        clean = self._git("clean", "-ffdx", cwd=target)
        checkout = self._git("checkout", "--", ".", cwd=target)
        if clean.returncode != 0 or checkout.returncode != 0:
            raise RuntimeError(
                f"Failed to reset git worktree at {target}: "
                f"{(clean.stderr or checkout.stderr).strip()}"
            )

    def remove(self, name: str) -> None:
        if not self._available:
            return
        target = Path(self.path(name))
        if target.exists():
            result = self._git("worktree", "remove", "--force", str(target))
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to remove git worktree at {target}: {result.stderr.strip()}"
                )
        # Best-effort branch cleanup; ignore failure if branch is checked out elsewhere.
        self._git("branch", "-D", self._branch(name))
