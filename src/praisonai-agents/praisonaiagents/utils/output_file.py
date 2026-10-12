import functools
import os
import stat

from praisonaiagents._logging import get_logger

from ..tools.path_safety import resolve_within_root

logger = get_logger(__name__)


def _open_nofollow(path, flags, mode=0o666):
    return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)


def write_output_file(path: str, content: str, create_dirs: bool = True) -> str | None:
    """Write *content* to *path* if it resolves inside the project root.

    The root is ``PRAISONAI_PROJECT_ROOT`` or the cwd, matching ``Agent.output_file``.
    Returns the resolved path, or ``None`` when the path escapes the root.
    """
    project_root = os.environ.get("PRAISONAI_PROJECT_ROOT") or os.getcwd()
    file_path = resolve_within_root(path, project_root)
    if file_path is None:
        logger.warning(
            "Output file %r is outside project root %r; skipping save",
            path,
            project_root,
        )
        return None
    if create_dirs:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "a", encoding="utf-8", opener=_open_nofollow) as f:
        st = os.fstat(f.fileno())
        if st.st_nlink == 1:
            f.truncate(0)
            f.write(content)
            return file_path
    # A hardlink may share its inode with a file outside the root, so write a
    # new file under the same name instead of truncating the shared one.
    os.unlink(file_path)
    opener = functools.partial(_open_nofollow, mode=stat.S_IMODE(st.st_mode))
    with open(file_path, "x", encoding="utf-8", opener=opener) as f:
        f.write(content)
    return file_path
