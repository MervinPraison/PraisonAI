"""Fast, capped code-search built-ins: ``grep`` and ``glob``.

These are the two most common moves a coding/repo-exploration agent makes:
"where is this string/symbol used?" (``grep``) and "which files match this
pattern?" (``glob``). Both are bounded (hard result cap with a "narrow your
query" hint), path-safe (contained to the workspace, no traversal), and
zero-config.

``grep`` prefers ``ripgrep`` (``rg``) when present for speed and falls back to a
pure-Python tree walk so it always works with zero external dependencies.
``glob`` uses :mod:`pathlib`/:mod:`fnmatch` and honours ``.gitignore`` when
available.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import grep, glob

    agent = Agent(name="coder", tools=[grep, glob])

or directly::

    from praisonaiagents.tools import grep, glob
    print(grep("deprecated_fn", path="src", glob="*.py"))
    print(glob("**/*.py", path="src"))
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import fnmatch
import logging
from pathlib import Path
from typing import List, Optional

from .path_safety import resolve_within_root

logger = logging.getLogger(__name__)

# Default hard cap on returned results to keep output bounded and agent-friendly.
_DEFAULT_MAX_RESULTS = 100

# Directories that are almost never useful to search and are expensive to walk.
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build",
    ".eggs", ".idea", ".vscode",
})


def _validate_within_workspace(path: str) -> Optional[str]:
    """Resolve *path* under the current workspace, rejecting traversal.

    Returns the resolved absolute path, or ``None`` when *path* escapes the
    workspace root (mirrors the containment used by ``file_tools``).
    """
    return resolve_within_root(path or ".")


def _truncation_hint(count: int, max_results: int, what: str) -> str:
    return (
        f"... {count}+ {what} (truncated at {max_results}); "
        f"refine the pattern or narrow `path`/`glob`."
    )


def _load_gitignore_spec(root: str):
    """Best-effort load of ``.gitignore`` patterns from *root*.

    Returns a callable ``matcher(relpath, is_dir) -> bool`` or ``None`` when no
    ignore file is present. Uses a small self-contained matcher so no external
    dependency is required.
    """
    gitignore = os.path.join(root, ".gitignore")
    if not os.path.isfile(gitignore):
        return None
    patterns: List[str] = []
    try:
        with open(gitignore, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)
    except Exception:
        return None
    if not patterns:
        return None

    def _matches(relpath: str, is_dir: bool) -> bool:
        name = os.path.basename(relpath)
        posix = relpath.replace(os.sep, "/")
        # Last matching pattern wins so re-includes (``!important.log``) can
        # override an earlier broad exclude, mirroring Git's own semantics.
        ignored = False
        for pat in patterns:
            neg = pat.startswith("!")
            p = pat[1:] if neg else pat
            dir_only = p.endswith("/")
            p = p.rstrip("/")
            if dir_only and not is_dir:
                continue
            hit = False
            if "/" in p:
                candidate = p[1:] if p.startswith("/") else p
                if fnmatch.fnmatch(posix, candidate) or fnmatch.fnmatch(posix, candidate + "/*"):
                    hit = True
            else:
                # A bare name matches the entry itself or any path segment,
                # so ``build/`` also ignores ``build/foo.py``.
                if fnmatch.fnmatch(name, p) or any(
                    fnmatch.fnmatch(seg, p) for seg in posix.split("/")
                ):
                    hit = True
            if hit:
                ignored = not neg
        return ignored

    return _matches


def _matches_glob(fname: str, rel: str, glob: Optional[str]) -> bool:
    """True when *glob* is empty or matches the filename or workspace-relative path."""
    if not glob:
        return True
    posix = rel.replace(os.sep, "/")
    return (
        fnmatch.fnmatch(fname, glob)
        or fnmatch.fnmatch(rel, glob)
        or fnmatch.fnmatch(posix, glob)
    )


def _iter_files(root: str, glob: Optional[str], ignore_matcher):
    """Yield files under *root*, skipping noise dirs and ``.gitignore`` matches.

    When *root* is a single file it is yielded directly (subject to *glob*), so
    callers work identically whether given a directory or a file path.
    """
    if os.path.isfile(root):
        rel = os.path.basename(root)
        if _matches_glob(rel, rel, glob):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS
            and not (ignore_matcher and ignore_matcher(
                os.path.relpath(os.path.join(dirpath, d), root), True))
        ]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            if ignore_matcher and ignore_matcher(rel, False):
                continue
            if not _matches_glob(fname, rel, glob):
                continue
            yield full


_MAX_PATTERN_LEN = 1000


def _python_grep(pattern, root, glob, case_insensitive, max_results):
    """Pure-Python fallback content search (regex/literal)."""
    # Python's backtracking ``re`` engine has no execution-time bound, so cap
    # the pattern length to reduce catastrophic-backtracking (ReDoS) exposure
    # on this fallback path (ripgrep's RE2-style engine is linear-time).
    if len(pattern) > _MAX_PATTERN_LEN:
        return f"Error: pattern too long (>{_MAX_PATTERN_LEN} chars); please narrow it."
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        return f"Error: invalid regex pattern {pattern!r}: {exc}"

    ignore_matcher = _load_gitignore_spec(root)
    lines: List[str] = []
    count = 0
    truncated = False
    for full in _iter_files(root, glob, ignore_matcher):
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if regex.search(line):
                        count += 1
                        if count > max_results:
                            truncated = True
                            break
                        rel = os.path.relpath(full)
                        lines.append(f"{rel}:{lineno}: {line.rstrip()}")
        except (OSError, UnicodeError):
            continue
        if truncated:
            break

    if not lines:
        return "No matches found."
    if truncated:
        lines.append(_truncation_hint(max_results, max_results, "matches"))
    return "\n".join(lines)


def _relativize(line: str) -> str:
    """Rewrite a ``file:line:match`` entry to use a workspace-relative path."""
    head, sep, rest = line.partition(":")
    if not sep:
        return line
    try:
        return os.path.relpath(head) + sep + rest
    except ValueError:
        return line


def _cap_rg_output(stdout: str, max_results: int) -> str:
    lines = [_relativize(ln) for ln in stdout.splitlines() if ln]
    if not lines:
        return "No matches found."
    if len(lines) > max_results:
        lines = lines[:max_results]
        lines.append(_truncation_hint(max_results, max_results, "matches"))
    return "\n".join(lines)


def grep(
    pattern: str,
    path: str = ".",
    glob: Optional[str] = None,
    case_insensitive: bool = False,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> str:
    """Search file contents for *pattern* (regex/literal), capped and bounded.

    Prefers ``ripgrep`` (``rg``) when available for speed; otherwise falls back
    to a pure-Python walker so it always works with zero external dependencies.

    Args:
        pattern: Regex/literal to search for.
        path: Directory (or file) to search under. Contained to the workspace.
        glob: Optional filename glob to restrict the search (e.g. ``"*.py"``).
        case_insensitive: Case-insensitive matching when True.
        max_results: Hard cap on the number of matching lines returned.

    Returns:
        ``path:line: matched line`` entries (newline-joined), hard-capped with a
        truncation hint when there are more matches. Returns a short message on
        no matches or on error.
    """
    if not pattern:
        return "Error: `pattern` must be a non-empty string."
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = _DEFAULT_MAX_RESULTS
    if max_results <= 0:
        max_results = _DEFAULT_MAX_RESULTS

    safe = _validate_within_workspace(path)
    if safe is None:
        return f"Error: path {path!r} escapes the workspace."
    if not os.path.exists(safe):
        return f"Error: path not found: {path}"

    rg = shutil.which("rg")
    if rg:
        # NOTE: no ``--max-count`` — that caps *per file*, which diverges from
        # the pure-Python fallback's total cap. We cap the total afterwards so
        # both paths return identical truncated results.
        argv = [rg, "--line-number", "--with-filename", "--color=never"]
        if case_insensitive:
            argv.append("-i")
        if glob:
            argv += ["--glob", glob]
        argv += ["--", pattern, safe]
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=30, check=False)
            # rg exit code 1 == no matches (not an error); >1 == real error.
            if proc.returncode not in (0, 1):
                logger.debug("ripgrep failed (%s); falling back to python grep: %s",
                             proc.returncode, proc.stderr.strip())
                return _python_grep(pattern, safe, glob, case_insensitive, max_results)
            return _cap_rg_output(proc.stdout, max_results)
        except (subprocess.SubprocessError, OSError) as exc:
            logger.debug("ripgrep invocation error; falling back: %s", exc)

    return _python_grep(pattern, safe, glob, case_insensitive, max_results)


def glob(
    pattern: str,
    path: str = ".",
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> str:
    """Return files matching a glob *pattern* under *path*, capped and sorted.

    Supports recursive globs (``**/*.py``, ``src/**/test_*.py``). Honours
    ``.gitignore`` when available and skips common noise directories. Results
    are sorted by modification time (newest first) and hard-capped.

    Args:
        pattern: Glob pattern (e.g. ``"**/*.ts"``).
        path: Directory to search under. Contained to the workspace.
        max_results: Hard cap on the number of paths returned.

    Returns:
        Newline-joined relative file paths, hard-capped with a truncation hint
        when there are more matches. Returns a short message on no matches or
        on error.
    """
    if not pattern:
        return "Error: `pattern` must be a non-empty string."
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = _DEFAULT_MAX_RESULTS
    if max_results <= 0:
        max_results = _DEFAULT_MAX_RESULTS

    safe = _validate_within_workspace(path)
    if safe is None:
        return f"Error: path {path!r} escapes the workspace."
    if not os.path.isdir(safe):
        return f"Error: directory not found: {path}"

    ignore_matcher = _load_gitignore_spec(safe)
    root = Path(safe)

    def _ignored(rel: str, parts: List[str]) -> bool:
        # Skip noise dirs and any file whose own path OR an ancestor directory
        # matches ``.gitignore`` (so directory-only rules like ``build/`` also
        # exclude ``build/foo.py``).
        if any(part in _SKIP_DIRS for part in parts):
            return True
        if not ignore_matcher:
            return False
        if ignore_matcher(rel, False):
            return True
        ancestor = ""
        for part in parts[:-1]:
            ancestor = os.path.join(ancestor, part) if ancestor else part
            if ignore_matcher(ancestor, True):
                return True
        return False

    try:
        matches = []
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            rel = os.path.relpath(p, safe)
            if _ignored(rel, rel.split(os.sep)):
                continue
            matches.append(p)
    except (OSError, ValueError) as exc:
        return f"Error: invalid glob pattern {pattern!r}: {exc}"

    if not matches:
        return "No files found."

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    matches.sort(key=_mtime, reverse=True)
    truncated = len(matches) > max_results
    shown = matches[:max_results]
    lines = [os.path.relpath(p) for p in shown]
    if truncated:
        lines.append(_truncation_hint(max_results, max_results, "files"))
    return "\n".join(lines)


if __name__ == "__main__":
    print("grep('def ', path='.', glob='*.py'):")
    print(grep("def ", path=".", glob="*.py", max_results=10))
    print("\nglob('**/*.py'):")
    print(glob("**/*.py", max_results=10))
