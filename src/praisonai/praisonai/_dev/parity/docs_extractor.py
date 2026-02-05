"""
Documentation Extractor Base Classes for PraisonAI SDK.

Extracts documented topics from MDX files for parity tracking.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set
import yaml


@dataclass
class DocsTopic:
    """Information about a documented topic."""
    name: str           # Normalized topic name (e.g., "agent")
    title: str          # Original title from frontmatter
    path: str           # Relative path to MDX file
    category: str       # Category: concepts, features, guides, cli, etc.
    sidebar_title: Optional[str] = None  # Optional sidebar title
    description: Optional[str] = None    # Optional description


@dataclass
class DocsFeatures:
    """Extracted documentation topics from an SDK."""
    topics: List[DocsTopic] = field(default_factory=list)
    categories: Dict[str, List[str]] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'topics': [
                {
                    'name': t.name,
                    'title': t.title,
                    'path': t.path,
                    'category': t.category,
                    'sidebarTitle': t.sidebar_title,
                    'description': t.description,
                }
                for t in self.topics
            ],
            'categories': self.categories,
        }
    
    def get_topic_names(self) -> Set[str]:
        """Get set of all normalized topic names."""
        return {t.name for t in self.topics}


class DocsExtractor(Protocol):
    """Protocol for documentation extraction."""
    
    def extract(self) -> DocsFeatures:
        """Extract all documented topics."""
        ...
    
    def get_topic_names(self) -> Set[str]:
        """Get normalized topic names."""
        ...


class BaseDocsExtractor:
    """
    Base class for documentation extractors.
    
    Provides common functionality for parsing MDX frontmatter
    and normalizing topic names.
    """
    
    def __init__(self, docs_root: Optional[Path] = None):
        """Initialize extractor with documentation root path."""
        if docs_root is None:
            docs_root = Path("/Users/praison/PraisonAIDocs/docs")
        self.docs_root = Path(docs_root).resolve()
    
    def _parse_frontmatter(self, file_path: Path) -> Dict[str, str]:
        """
        Parse YAML frontmatter from an MDX file.
        
        Returns dict with title, sidebarTitle, description, icon.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return {}
        
        # Match YAML frontmatter between --- markers
        match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return {}
        
        try:
            frontmatter = yaml.safe_load(match.group(1))
            if isinstance(frontmatter, dict):
                return frontmatter
        except yaml.YAMLError:
            pass
        
        return {}
    
    def _normalize_topic_name(self, name: str) -> str:
        """
        Normalize a topic name for comparison.
        
        - Lowercase
        - Replace underscores with hyphens
        - Handle common variations
        """
        from .topic_normalizer import normalize_topic
        return normalize_topic(name)
    
    def _extract_topic_from_path(self, file_path: Path, base_path: Path) -> Optional[DocsTopic]:
        """
        Extract a DocsTopic from an MDX file.
        
        Args:
            file_path: Path to the MDX file
            base_path: Base path for calculating relative paths
            
        Returns:
            DocsTopic or None if extraction fails
        """
        frontmatter = self._parse_frontmatter(file_path)
        
        # Get title - prefer sidebarTitle, then title, then filename
        title = frontmatter.get('sidebarTitle') or frontmatter.get('title')
        if not title:
            title = file_path.stem.replace('-', ' ').title()
        
        # Determine category from path
        rel_path = file_path.relative_to(base_path)
        parts = rel_path.parts
        category = parts[0] if len(parts) > 1 else 'root'
        
        # Normalize the topic name from the filename
        raw_name = file_path.stem
        normalized_name = self._normalize_topic_name(raw_name)
        
        return DocsTopic(
            name=normalized_name,
            title=title,
            path=str(rel_path),
            category=category,
            sidebar_title=frontmatter.get('sidebarTitle'),
            description=frontmatter.get('description'),
        )
    
    def _scan_directory(self, directory: Path, base_path: Path) -> List[DocsTopic]:
        """
        Recursively scan a directory for MDX files.
        
        Args:
            directory: Directory to scan
            base_path: Base path for relative path calculation
            
        Returns:
            List of DocsTopic objects
        """
        topics = []
        
        if not directory.exists():
            return topics
        
        for mdx_file in directory.rglob("*.mdx"):
            topic = self._extract_topic_from_path(mdx_file, base_path)
            if topic:
                topics.append(topic)
        
        return topics
