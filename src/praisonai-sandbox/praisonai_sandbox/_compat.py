"""Path-safety helper for sandbox backends."""

import errno
import logging
import os

logger = logging.getLogger(__name__)

# The descriptor-relative walk relies on POSIX-only openat semantics:
# O_DIRECTORY / O_NOFOLLOW and os.open()'s dir_fd argument. Windows has none of
# them -- referencing os.O_DIRECTORY there is an AttributeError, and dir_fd is
# unsupported -- so the whole approach is guarded behind this flag. Docker on
# Windows talks to a Linux daemon, so the container-side race these helpers
# defend against does not exist on the host; falling back to the resolved-string
# guard there is both correct and the only thing that runs.
_HAS_OPENAT = (
    hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and os.open in getattr(os, "supports_dir_fd", set())
)


def safe_sandbox_path(temp_dir: str | None, path: str) -> str | None:
    """Resolve a caller-supplied path to an absolute path inside temp_dir.

    Returns None if the resolved path would escape the sandbox root,
    preventing path-traversal attacks via sequences like `../../../etc/passwd`.
    
    Args:
        temp_dir: The sandbox root directory
        path: User-supplied path to resolve
        
    Returns:
        Safe absolute path within sandbox, or None if path escapes sandbox
    """
    if not temp_dir:
        return None
    candidate = os.path.realpath(os.path.join(temp_dir, path.lstrip("/")))
    sandbox_root = os.path.realpath(temp_dir)
    if not (candidate == sandbox_root or candidate.startswith(sandbox_root + os.sep)):
        logger.warning("Path traversal attempt blocked: %s", path)
        return None
    return candidate


def _components(path: str) -> list | None:
    """Split a caller path into components, rejecting anything that climbs."""
    parts = [p for p in path.lstrip("/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return parts


def open_in_sandbox(temp_dir: str | None, path: str, flags: int, mode: int = 0o600):
    """Open a path strictly inside ``temp_dir``, refusing symlinks at every level.

    ``safe_sandbox_path`` validates a path *string* and the caller then opens
    that string -- two syscalls with a gap between them. That was harmless while
    only the host could write to the sandbox directory. Once the directory is
    bind-mounted into the container, code inside it can swap a name between a
    regular file and a symlink and win the race: a loop of
    ``ln -s /etc/passwd notes.txt`` against repeated writes escaped to arbitrary
    host files within a few hundred attempts, and leaked a host secret on the
    fourth read.

    Resolving the string more carefully cannot fix that -- any check performed
    before the open can be invalidated after it. So this never re-opens by name.
    It walks the path one component at a time relative to an open directory
    descriptor, with ``O_NOFOLLOW`` on each step, so a symlink substituted at
    any level fails the open instead of redirecting it.

    Returns an open file descriptor, or None if the path escapes or a component
    is a symlink. The caller owns the descriptor.
    """
    if not temp_dir:
        return None
    parts = _components(path)
    if parts is None or not parts:
        logger.warning("Path traversal attempt blocked: %s", path)
        return None

    if not _HAS_OPENAT:
        # No openat here (Windows). The container-side symlink race this walk
        # defends against cannot occur -- Docker Desktop runs Linux containers
        # in a VM, so nothing shares this host directory -- so the resolved
        # string guard is sufficient and is the only thing that can run.
        resolved = safe_sandbox_path(temp_dir, path)
        if resolved is None:
            return None
        try:
            return os.open(resolved, flags, mode)
        except OSError:
            return None

    try:
        root_fd = os.open(temp_dir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None

    opened = [root_fd]
    try:
        dir_fd = root_fd
        for part in parts[:-1]:
            try:
                dir_fd = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=dir_fd,
                )
            except OSError:
                logger.warning("Blocked traversal through %r in %s", part, path)
                return None
            opened.append(dir_fd)
        try:
            return os.open(parts[-1], flags | os.O_NOFOLLOW, mode, dir_fd=dir_fd)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.EMLINK):
                logger.warning("Refused to follow a symlink at %s", path)
            return None
    finally:
        for fd in opened:
            try:
                os.close(fd)
            except OSError:
                pass


def makedirs_in_sandbox(temp_dir: str | None, path: str) -> bool:
    """Create the parent directories of ``path`` without following symlinks."""
    if not temp_dir:
        return False
    parts = _components(path)
    if parts is None:
        return False

    if not _HAS_OPENAT:
        # Windows fallback: no openat, and no host-shared directory to race.
        # Create the parent chain through the resolved string guard.
        if len(parts) <= 1:
            return True
        resolved = safe_sandbox_path(temp_dir, "/".join(parts[:-1]))
        if resolved is None:
            return False
        try:
            os.makedirs(resolved, exist_ok=True)
            return True
        except OSError:
            return False

    try:
        dir_fd = os.open(temp_dir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return False

    opened = [dir_fd]
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=dir_fd)
            except FileExistsError:
                pass
            except OSError:
                return False
            try:
                dir_fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd
                )
            except OSError:
                logger.warning("Blocked traversal through %r in %s", part, path)
                return False
            opened.append(dir_fd)
        return True
    finally:
        for fd in opened:
            try:
                os.close(fd)
            except OSError:
                pass
