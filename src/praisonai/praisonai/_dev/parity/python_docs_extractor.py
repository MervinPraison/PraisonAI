"""
Python Documentation Extractor for PraisonAI SDK.

Extracts documented topics from Python documentation (source of truth).
Python docs are spread across multiple directories:
- docs/concepts/
- docs/features/
- docs/guides/
- docs/cli/
- docs/memory/
- docs/knowledge/
- docs/rag/
- etc.
"""

from pathlib import Path
from typing import List, Optional, Set

from .docs_extractor import BaseDocsExtractor, DocsFeatures, DocsTopic


# Directories containing Python documentation (source of truth)
# Focus on conceptual/guide documentation, not auto-generated API docs
PYTHON_DOC_DIRECTORIES = [
    'concepts',
    'features',
    'guides',
    'cli',
    'memory',
    'knowledge',
    'rag',
    'persistence',
    'databases',
    'observability',
    'configuration',
    'best-practices',
    'models',
    'embeddings',
    'capabilities',
    'agents',
    'tools',
    'mcp',
    'eval',
    'deploy',
    'developers',
    'tutorials',
    # Exclude: 'api', 'api-reference', 'reference', 'sdk' - auto-generated API docs
    'nocode',
    'audio',
    'video',
    'image',
    'code',
    'ui',
    'framework',
    'install',
    'storage',
    'integrations',
    'recipes',
    'ocr',  # OCR agent documentation
]

# Patterns to exclude from topic extraction (method-level docs)
EXCLUDE_TOPIC_PATTERNS = [
    '-get-',
    '-set-',
    '-add-',
    '-remove-',
    '-run-',
    '-start-',
    '-stop-',
    '-execute-',
    '-create-',
    '-delete-',
    '-update-',
    '-list-',
    '-is-',
    '-has-',
    '-from-',
    '-to-',
    '-with-',
    'protocol-',  # Protocol method docs
    'interface-',  # Interface method docs
]

# Directories to exclude (other SDK docs or non-content)
EXCLUDE_DIRECTORIES = [
    'js',
    'rust',
    'course',
    'demo',
    'todo',
    'tools_test',
    'node_modules',
    'overrides',
    '.netlify',
    'public',
    'images',
]


class PythonDocsExtractor(BaseDocsExtractor):
    """
    Extracts documented topics from Python documentation.
    
    Python documentation is the source of truth for parity tracking.
    It scans multiple directories under /docs/ excluding JS and Rust folders.
    """
    
    def __init__(self, docs_root: Optional[Path] = None):
        """Initialize with documentation root path."""
        super().__init__(docs_root)
    
    def _should_exclude_topic(self, topic_name: str) -> bool:
        """Check if a topic should be excluded based on patterns."""
        for pattern in EXCLUDE_TOPIC_PATTERNS:
            if pattern in topic_name:
                return True
        return False
    
    def extract(self) -> DocsFeatures:
        """
        Extract all documented topics from Python docs.
        
        Returns:
            DocsFeatures with all Python documentation topics
        """
        features = DocsFeatures()
        categories = {}
        
        # Scan each Python doc directory
        for dir_name in PYTHON_DOC_DIRECTORIES:
            dir_path = self.docs_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                topics = self._scan_directory(dir_path, self.docs_root)
                # Filter out method-level docs
                topics = [t for t in topics if not self._should_exclude_topic(t.name)]
                features.topics.extend(topics)
                
                # Group by category
                if topics:
                    categories[dir_name] = [t.name for t in topics]
        
        # Also scan root-level MDX files
        root_topics = self._scan_root_files()
        root_topics = [t for t in root_topics if not self._should_exclude_topic(t.name)]
        features.topics.extend(root_topics)
        if root_topics:
            categories['root'] = [t.name for t in root_topics]
        
        features.categories = categories
        return features
    
    def _scan_root_files(self) -> List[DocsTopic]:
        """Scan MDX files directly in the docs root."""
        topics = []
        
        for mdx_file in self.docs_root.glob("*.mdx"):
            topic = self._extract_topic_from_path(mdx_file, self.docs_root)
            if topic:
                topic.category = 'root'
                topics.append(topic)
        
        return topics
    
    def get_topic_names(self) -> Set[str]:
        """Get set of all normalized topic names."""
        return self.extract().get_topic_names()
