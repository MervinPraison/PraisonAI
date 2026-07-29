"""Declarative remote skill sources with a versioned local cache.

A remote skill source is fetched at discovery time, cached under
``~/.praisonai/cache/remote-skills/<source-id>/`` in a versioned directory, and
atomically swapped in when the remote changes. Sync is opt-in, offline-safe
(falls back to the last-good cache), and adds zero import-time cost — the module
is only imported when a caller passes ``sources=`` to ``discover_skills``.

Remote content is untrusted: callers re-run the existing skill validator on the
returned directories before injecting anything into a prompt.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

CACHE_SUBDIR = "remote-skills"
_CURRENT_LINK = "current"


def get_remote_cache_root() -> Path:
    """Return the root cache directory for remote skill sources."""
    from ..paths import get_cache_dir

    return get_cache_dir() / CACHE_SUBDIR


def _source_id(source: str) -> str:
    """Stable, filesystem-safe id for a source URL/spec."""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return digest


def _has_skill(directory: Path) -> bool:
    """True if ``directory`` or any child looks like a skill dir."""
    if (directory / "SKILL.md").exists():
        return True
    try:
        for child in directory.iterdir():
            if child.is_dir() and (child / "SKILL.md").exists():
                return True
    except OSError:
        return False
    return False


class GitRemoteSkillSource:
    """Default remote skill source backed by a shallow git clone.

    The source URL is a git-cloneable HTTP(S) URL. On ``fetch`` the repo is
    shallow-cloned into a temporary directory, its resolved commit becomes the
    cache version, and the tree is atomically swapped into a versioned cache
    dir. When the remote is unreachable the last-good cache is returned so
    discovery keeps working offline.

    ``ref`` optionally pins a branch/tag/commit for reproducible syncs.
    """

    def __init__(self, url: str, ref: Optional[str] = None):
        self.url = url
        self.ref = ref

    def _cache_base(self, cache_dir: Path) -> Path:
        return cache_dir / _source_id(f"{self.url}@{self.ref or ''}")

    def _last_good(self, cache_dir: Path) -> List[Path]:
        base = self._cache_base(cache_dir)
        current = base / _CURRENT_LINK
        if current.exists():
            return [current]
        return []

    def fetch(self, cache_dir: Path) -> List[Path]:
        base = self._cache_base(cache_dir)
        base.mkdir(parents=True, exist_ok=True)

        tmp_clone: Optional[str] = None
        try:
            tmp_clone = tempfile.mkdtemp(prefix="praison-skill-clone-")
            clone_path = Path(tmp_clone) / "repo"
            cmd = ["git", "clone", "--depth=1"]
            if self.ref:
                cmd += ["--branch", self.ref]
            cmd += [self.url, str(clone_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                logger.warning(
                    "Remote skill sync failed for %s: %s; using cached copy.",
                    self.url, proc.stderr.strip(),
                )
                return self._last_good(cache_dir)

            version = self._resolve_version(clone_path)
            versioned = base / version
            current = base / _CURRENT_LINK

            if not versioned.exists():
                shutil.rmtree(clone_path / ".git", ignore_errors=True)
                self._atomic_swap(clone_path, versioned, current)
            else:
                # Already have this version cached; just point current at it.
                self._point_current(current, versioned)

            self._prune_old(base, keep=versioned.name)
            return [current] if current.exists() else [versioned]
        except Exception as exc:  # noqa: BLE001 - offline-safe fallback
            logger.warning(
                "Remote skill sync error for %s: %s; using cached copy.",
                self.url, exc,
            )
            return self._last_good(cache_dir)
        finally:
            if tmp_clone:
                shutil.rmtree(tmp_clone, ignore_errors=True)

    def _resolve_version(self, clone_path: Path) -> str:
        proc = subprocess.run(
            ["git", "-C", str(clone_path), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()[:16]
        return _source_id(str(clone_path))

    def _atomic_swap(self, src: Path, versioned: Path, current: Path) -> None:
        staging = versioned.parent / (versioned.name + ".tmp")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        shutil.move(str(src), str(staging))
        os.replace(staging, versioned)
        self._point_current(current, versioned)

    def _point_current(self, current: Path, versioned: Path) -> None:
        try:
            tmp_link = current.parent / (_CURRENT_LINK + ".tmp")
            if tmp_link.exists() or tmp_link.is_symlink():
                tmp_link.unlink()
            tmp_link.symlink_to(versioned.name, target_is_directory=True)
            os.replace(tmp_link, current)
        except (OSError, NotImplementedError):
            # Filesystems without symlink support: copy the tree instead.
            if current.exists():
                shutil.rmtree(current, ignore_errors=True)
            shutil.copytree(versioned, current)

    def _prune_old(self, base: Path, keep: str) -> None:
        try:
            for child in base.iterdir():
                if child.name in (keep, _CURRENT_LINK):
                    continue
                if child.is_symlink():
                    continue
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def _coerce_source(source) -> Optional[object]:
    """Turn a config entry into a RemoteSkillSourceProtocol implementation.

    Accepts an object that already has a ``fetch`` method, a plain URL string,
    or a ``{"url": ..., "ref": ...}`` mapping.
    """
    if hasattr(source, "fetch"):
        return source
    if isinstance(source, str):
        return GitRemoteSkillSource(source)
    if isinstance(source, dict) and source.get("url"):
        return GitRemoteSkillSource(source["url"], source.get("ref"))
    logger.warning("Ignoring unrecognised remote skill source: %r", source)
    return None


def fetch_remote_skill_dirs(sources, cache_dir: Optional[Path] = None) -> List[Path]:
    """Fetch all remote skill sources and return validated cache directories.

    Args:
        sources: Iterable of URL strings, ``{"url","ref"}`` dicts, or objects
            implementing ``fetch(cache_dir)``.
        cache_dir: Override cache root (defaults to the shared remote cache).

    Returns:
        Existing local directories holding fetched skills. Directories with no
        valid skill are dropped. Failures are logged and skipped, never raised.
    """
    root = cache_dir or get_remote_cache_root()
    root.mkdir(parents=True, exist_ok=True)

    dirs: List[Path] = []
    for entry in sources or []:
        impl = _coerce_source(entry)
        if impl is None:
            continue
        try:
            for d in impl.fetch(root):
                p = Path(d)
                if not (p.exists() and p.is_dir()):
                    continue
                # discover_skills scans the *children* of each returned dir for
                # skill subdirectories, but also treats a returned dir that is
                # *itself* a skill (SKILL.md at its root) as a single skill.
                # So we always return the fetched dir as-is: never its parent,
                # which for a root-level skill would also contain the versioned
                # cache dir and its ``current`` alias and double-count the skill.
                if _has_skill(p) and p not in dirs:
                    dirs.append(p)
        except Exception as exc:  # noqa: BLE001 - never break discovery
            logger.warning("Remote skill source failed: %s", exc)
    return dirs
