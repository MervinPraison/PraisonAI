import os

from praisonaiagents._logging import get_logger

from ..tools.path_safety import resolve_within_root
from .atomic_io import atomic_write_text

logger = get_logger(__name__)


def write_output_file(path: str, content: str, create_dirs: bool = True) -> str | None:
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
    atomic_write_text(file_path, content)
    return file_path
