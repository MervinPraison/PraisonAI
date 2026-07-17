"""Path-safety helper for sandbox backends."""

import logging
import os

logger = logging.getLogger(__name__)


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
