"""
Rust Documentation Extractor for PraisonAI SDK.

Extracts documented topics from Rust documentation
located in /docs/rust/
"""

from pathlib import Path
from typing import Optional, Set

from .docs_extractor import BaseDocsExtractor, DocsFeatures


class RustDocsExtractor(BaseDocsExtractor):
    """
    Extracts documented topics from Rust documentation.
    
    All Rust docs are under /docs/rust/ directory.
    """
    
    def __init__(self, docs_root: Optional[Path] = None):
        """Initialize with documentation root path."""
        super().__init__(docs_root)
        self.rust_docs_path = self.docs_root / "rust"
    
    def extract(self) -> DocsFeatures:
        """
        Extract all documented topics from Rust docs.
        
        Returns:
            DocsFeatures with all Rust documentation topics
        """
        features = DocsFeatures()
        categories = {}
        
        if not self.rust_docs_path.exists():
            return features
        
        # Scan the entire rust directory
        topics = self._scan_directory(self.rust_docs_path, self.rust_docs_path)
        features.topics = topics
        
        # Group by subdirectory (category)
        for topic in topics:
            category = topic.category
            if category not in categories:
                categories[category] = []
            categories[category].append(topic.name)
        
        features.categories = categories
        return features
    
    def get_topic_names(self) -> Set[str]:
        """Get set of all normalized topic names."""
        return self.extract().get_topic_names()
