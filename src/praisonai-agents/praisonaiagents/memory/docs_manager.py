"""
Docs Manager for PraisonAI Agents.

Provides reusable documentation context support similar to:
- Cursor Notepads (deprecated in favor of docs)
- Cursor .cursor/docs/
- Project documentation for AI context

Features:
- Auto-discovery of docs from .praison/docs/
- Support for markdown, text, and code files
- @doc mentions for including specific docs
- Priority ordering for docs
- Character limits for context window management

Storage Structure:
    .praison/docs/
    ├── project-overview.md      # Project overview
    ├── architecture.md          # Architecture decisions
    ├── api-reference.md         # API documentation
    └── coding-standards.md      # Coding guidelines

Doc File Format (YAML frontmatter + Markdown):
    ---
    description: Project architecture overview
    priority: 10
    tags: [architecture, design]
    ---
    
    # Architecture Overview
    This project uses...
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Doc:
    """A single documentation file with metadata and content."""
    name: str
    content: str
    description: str = ""
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    file_path: Optional[str] = None
    
    def matches_tag(self, tag: str) -> bool:
        """Check if this doc has a specific tag."""
        return tag.lower() in [t.lower() for t in self.tags]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content,
            "description": self.description,
            "priority": self.priority,
            "tags": self.tags,
            "file_path": self.file_path
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Doc':
        return cls(**data)


class DocsManager:
    """
    Manages documentation context for AI agents.
    
    Provides:
    - Auto-discovery of docs from .praison/docs/
    - Global docs from ~/.praison/docs/
    - @doc mentions for including specific docs
    - Priority-based ordering
    """
    
    DOCS_DIR_NAME = ".praison/docs"
    SUPPORTED_EXTENSIONS = [".md", ".txt", ".rst"]
    
    # Maximum characters per doc (context window management)
    MAX_DOC_CHARS = 12000
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        global_docs_path: Optional[str] = None,
        verbose: int = 0
    ):
        """
        Initialize DocsManager.
        
        Args:
            workspace_path: Path to workspace/project root
            global_docs_path: Path to global docs (default: ~/.praison/docs)
            verbose: Verbosity level
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.global_docs_path = Path(global_docs_path) if global_docs_path else Path.home() / ".praison" / "docs"
        self.verbose = verbose
        
        self._docs: Dict[str, Doc] = {}
        self._load_all_docs()
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _parse_frontmatter(self, content: str) -> tuple:
        """
        Parse YAML frontmatter from content.
        
        Returns:
            Tuple of (frontmatter_dict, remaining_content)
        """
        frontmatter = {}
        remaining = content
        
        # Check for YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    remaining = parts[2].strip()
                except Exception:
                    # If YAML parsing fails, use content as-is
                    pass
        
        return frontmatter, remaining
    
    def _load_doc_file(self, file_path: Path, scope: str = "workspace") -> Optional[Doc]:
        """Load a single doc file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, doc_content = self._parse_frontmatter(content)
            
            name = file_path.stem
            
            # Determine priority based on scope
            base_priority = 100 if scope == "workspace" else 0
            
            doc = Doc(
                name=name,
                content=doc_content,
                description=frontmatter.get("description", ""),
                priority=frontmatter.get("priority", base_priority),
                tags=frontmatter.get("tags", []),
                file_path=str(file_path)
            )
            
            return doc
        except Exception as e:
            self._log(f"Failed to load doc {file_path}: {e}", logging.WARNING)
            return None
    
    def _load_docs_from_dir(self, docs_dir: Path, scope: str = "workspace"):
        """Load all docs from a directory."""
        if not docs_dir.exists():
            return
        
        for ext in self.SUPPORTED_EXTENSIONS:
            for file_path in docs_dir.glob(f"*{ext}"):
                if file_path.is_file():
                    doc = self._load_doc_file(file_path, scope)
                    if doc:
                        key = f"{scope}:{doc.name}"
                        self._docs[key] = doc
                        self._log(f"Loaded doc: {key}")
    
    def _load_all_docs(self):
        """Load all docs from global and workspace directories."""
        self._docs.clear()
        
        # 1. Load global docs (lowest priority)
        if self.global_docs_path.exists():
            self._load_docs_from_dir(self.global_docs_path, "global")
            for key, doc in self._docs.items():
                if key.startswith("global:"):
                    doc.priority = doc.priority - 1000  # Lower priority for global
        
        # 2. Load workspace docs
        workspace_docs_dir = self.workspace_path / self.DOCS_DIR_NAME.replace("/", os.sep)
        if workspace_docs_dir.exists():
            self._load_docs_from_dir(workspace_docs_dir, "workspace")
        
        self._log(f"Loaded {len(self._docs)} docs total")
    
    def reload(self):
        """Reload all docs from disk."""
        self._load_all_docs()
    
    def get_all_docs(self) -> List[Doc]:
        """Get all loaded docs, sorted by priority."""
        docs = list(self._docs.values())
        docs.sort(key=lambda d: d.priority, reverse=True)
        return docs
    
    def get_doc(self, name: str) -> Optional[Doc]:
        """Get a specific doc by name."""
        # Try workspace first, then global
        for scope in ["workspace", "global"]:
            key = f"{scope}:{name}"
            if key in self._docs:
                return self._docs[key]
        return None
    
    def get_docs_by_tag(self, tag: str) -> List[Doc]:
        """Get all docs with a specific tag."""
        docs = [d for d in self._docs.values() if d.matches_tag(tag)]
        docs.sort(key=lambda d: d.priority, reverse=True)
        return docs
    
    def get_docs_for_context(
        self,
        include_docs: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None,
        max_chars: int = 50000
    ) -> List[Doc]:
        """
        Get docs for inclusion in agent context.
        
        Args:
            include_docs: Specific doc names to include (via @doc mentions)
            include_tags: Tags to filter by
            max_chars: Maximum total characters
            
        Returns:
            List of docs sorted by priority
        """
        active = []
        
        # Include specific docs by name
        if include_docs:
            for name in include_docs:
                doc = self.get_doc(name)
                if doc and doc not in active:
                    active.append(doc)
        
        # Include docs by tag
        if include_tags:
            for tag in include_tags:
                for doc in self.get_docs_by_tag(tag):
                    if doc not in active:
                        active.append(doc)
        
        # If no specific docs requested, include all high-priority docs
        if not include_docs and not include_tags:
            for doc in self.get_all_docs():
                if doc.priority >= 100:  # Only high-priority docs by default
                    active.append(doc)
        
        # Sort by priority
        active.sort(key=lambda d: d.priority, reverse=True)
        
        return active
    
    def format_docs_for_prompt(
        self,
        include_docs: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None,
        max_chars: int = 50000
    ) -> str:
        """
        Format docs as a string for inclusion in prompts.
        
        Args:
            include_docs: Specific doc names to include
            include_tags: Tags to filter by
            max_chars: Maximum total characters
            
        Returns:
            Formatted docs string
        """
        active_docs = self.get_docs_for_context(include_docs, include_tags, max_chars)
        
        if not active_docs:
            return ""
        
        parts = ["# Project Documentation\n"]
        total_chars = len(parts[0])
        
        for doc in active_docs:
            if total_chars >= max_chars:
                break
            
            doc_text = doc.content.strip()
            if not doc_text:
                continue
            
            # Add doc with header
            if doc.description:
                header = f"## {doc.name}: {doc.description}"
            else:
                header = f"## {doc.name}"
            
            section = f"{header}\n{doc_text}\n"
            
            if total_chars + len(section) <= max_chars:
                parts.append(section)
                total_chars += len(section)
            else:
                # Truncate last doc
                remaining = max_chars - total_chars
                if remaining > 100:
                    parts.append(section[:remaining] + "\n... (truncated)")
                break
        
        return "\n".join(parts)
    
    def create_doc(
        self,
        name: str,
        content: str,
        description: str = "",
        priority: int = 0,
        tags: Optional[List[str]] = None,
        scope: Literal["global", "workspace"] = "workspace"
    ) -> Doc:
        """
        Create a new doc file.
        
        Args:
            name: Doc name (used as filename)
            content: Doc content (markdown)
            description: Short description
            priority: Priority (higher = applied first)
            tags: Tags for categorization
            scope: Where to save (global or workspace)
            
        Returns:
            Created Doc object
        """
        # Determine save path
        if scope == "global":
            docs_dir = self.global_docs_path
        else:
            docs_dir = self.workspace_path / self.DOCS_DIR_NAME.replace("/", os.sep)
        
        docs_dir.mkdir(parents=True, exist_ok=True)
        file_path = docs_dir / f"{name}.md"
        
        # Build frontmatter
        frontmatter_lines = ["---"]
        if description:
            frontmatter_lines.append(f'description: "{description}"')
        if priority != 0:
            frontmatter_lines.append(f"priority: {priority}")
        if tags:
            tags_str = ", ".join(f'"{t}"' for t in tags)
            frontmatter_lines.append(f"tags: [{tags_str}]")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")
        
        # Write file
        full_content = "\n".join(frontmatter_lines) + content
        file_path.write_text(full_content, encoding="utf-8")
        
        # Create and register doc
        doc = Doc(
            name=name,
            content=content,
            description=description,
            priority=priority,
            tags=tags or [],
            file_path=str(file_path)
        )
        
        self._docs[f"{scope}:{name}"] = doc
        self._log(f"Created doc '{name}' at {file_path}")
        
        return doc
    
    def delete_doc(self, name: str, scope: Optional[str] = None) -> bool:
        """
        Delete a doc file.
        
        Args:
            name: Doc name to delete
            scope: Scope to delete from (None = try both)
            
        Returns:
            True if deleted, False if not found
        """
        scopes = [scope] if scope else ["workspace", "global"]
        
        for s in scopes:
            key = f"{s}:{name}"
            if key in self._docs:
                doc = self._docs[key]
                if doc.file_path:
                    try:
                        Path(doc.file_path).unlink()
                        del self._docs[key]
                        self._log(f"Deleted doc '{name}' from {s}")
                        return True
                    except Exception as e:
                        self._log(f"Failed to delete doc file: {e}", logging.ERROR)
        
        return False
    
    def list_docs(self) -> List[Dict[str, Any]]:
        """
        List all docs with metadata.
        
        Returns:
            List of doc info dicts
        """
        docs = []
        for key, doc in self._docs.items():
            scope = key.split(":")[0]
            docs.append({
                "name": doc.name,
                "scope": scope,
                "description": doc.description,
                "priority": doc.priority,
                "tags": doc.tags,
                "file_path": doc.file_path,
                "content_length": len(doc.content)
            })
        
        # Sort by priority
        docs.sort(key=lambda d: d["priority"], reverse=True)
        return docs
