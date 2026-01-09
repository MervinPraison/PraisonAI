"""
Workspace Writer for code block scripts.

Writes extracted code blocks to a temporary workspace as executable scripts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .extractor import CodeBlock


@dataclass
class WorkspaceEntry:
    """Entry in the workspace manifest."""
    
    script_path: str
    doc_path: str
    block_index: int
    line_start: int
    line_end: int
    language: str
    code_hash: str


class WorkspaceWriter:
    """Writes code blocks to a workspace directory as executable scripts."""
    
    def __init__(self, workspace_dir: Path):
        """
        Initialize workspace writer.
        
        Args:
            workspace_dir: Directory to write scripts to.
        """
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._manifest: List[WorkspaceEntry] = []
    
    def write(self, block: "CodeBlock") -> Path:
        """
        Write a code block to the workspace.
        
        Args:
            block: The CodeBlock to write.
            
        Returns:
            Path to the written script file.
        """
        # Create subdirectory based on doc path
        doc_slug = block.doc_path.stem.replace(" ", "_").replace("-", "_")
        subdir = self.workspace_dir / doc_slug
        subdir.mkdir(parents=True, exist_ok=True)
        
        # Create script filename
        script_name = f"block_{block.block_index}.py"
        script_path = subdir / script_name
        
        # Write the code
        script_path.write_text(block.code, encoding='utf-8')
        
        # Add to manifest
        entry = WorkspaceEntry(
            script_path=str(script_path.relative_to(self.workspace_dir)),
            doc_path=str(block.doc_path),
            block_index=block.block_index,
            line_start=block.line_start,
            line_end=block.line_end,
            language=block.language,
            code_hash=block.code_hash,
        )
        self._manifest.append(entry)
        
        return script_path
    
    def get_manifest(self) -> List[Dict]:
        """
        Get the workspace manifest as a list of dicts.
        
        Returns:
            List of manifest entries as dictionaries.
        """
        return [
            {
                "script_path": e.script_path,
                "doc_path": e.doc_path,
                "block_index": e.block_index,
                "line_start": e.line_start,
                "line_end": e.line_end,
                "language": e.language,
                "code_hash": e.code_hash,
            }
            for e in self._manifest
        ]
    
    def save_manifest(self) -> Path:
        """
        Save the manifest to a JSON file.
        
        Returns:
            Path to the manifest file.
        """
        manifest_path = self.workspace_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(self.get_manifest(), indent=2),
            encoding='utf-8',
        )
        return manifest_path
