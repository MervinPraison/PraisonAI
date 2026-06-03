"""AGENTS.md-style context file injection for host apps."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def load_context_files(
    paths: Optional[List[str]] = None,
    *,
    cwd: Optional[Path] = None,
) -> str:
    """Load context from AGENTS.md-style files and return combined text."""
    base = cwd or Path.cwd()
    candidates = paths or ["AGENTS.md", "agents.md", ".agents/AGENTS.md"]
    chunks: List[str] = []
    for name in candidates:
        path = base / name
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(chunks)
