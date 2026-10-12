import os

from praisonaiagents._logging import get_logger

from ..tools.path_safety import resolve_within_root

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
    # Plain open() keeps an existing file's permissions and umask for new files.
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path
