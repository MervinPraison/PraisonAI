import os
import stat

from praisonaiagents._logging import get_logger

from ..tools.path_safety import resolve_within_root
from .atomic_io import atomic_write_text

logger = get_logger(__name__)


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
    try:
        with open(file_path, "x", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        # Replace rather than truncate so a hardlink to a file outside the
        # root is not written through, then restore the old mode (mkstemp is 0600).
        mode = stat.S_IMODE(os.stat(file_path).st_mode)
        atomic_write_text(file_path, content)
        os.chmod(file_path, mode)
    return file_path
