"""Rendering for ``--file`` / ``-f`` attachments.

``chat``, ``code`` and the interactive core all accept file attachments and must
agree on the wrapper the model sees, so the format lives in one place.
"""

import logging
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


def render_file_attachments(files: Optional[Iterable[str]]) -> str:
    """Return attached file contents as one ``<attached_files>`` block.

    Unreadable and missing paths are warned about and skipped rather than
    aborting the run. Returns "" when nothing could be attached.
    """
    parts: List[str] = []
    for filepath in files or []:
        path = Path(filepath)
        if not (path.exists() and path.is_file()):
            logger.warning(f"Attachment not found, skipping: {filepath}")
            continue
        try:
            content = path.read_text()
        except Exception as e:
            logger.warning(f"Could not read file {filepath}: {e}")
            continue
        parts.append(f'<file path="{filepath}">\n{content}\n</file>')

    if parts:
        return "<attached_files>\n" + "\n".join(parts) + "\n</attached_files>"
    return ""


def prepend_attachments(prompt: Optional[str], files: Optional[Iterable[str]]) -> Optional[str]:
    """Put attached files in front of ``prompt``.

    ``praisonai chat --file a.py`` with no prompt is a legitimate "here, read
    this" opener, so attachments alone still produce a prompt.
    """
    block = render_file_attachments(files)
    if not block:
        return prompt
    return f"{block}\n\n{prompt}" if prompt else block
