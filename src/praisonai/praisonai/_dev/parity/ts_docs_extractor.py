"""
TypeScript/JavaScript Documentation Extractor for PraisonAI SDK.

Extracts documented topics from TypeScript/JavaScript documentation
located in /docs/js/
"""

from pathlib import Path
from typing import Optional, Set

from .docs_extractor import BaseDocsExtractor, DocsFeatures


class TypeScriptDocsExtractor(BaseDocsExtractor):
    """
    Extracts documented topics from TypeScript/JavaScript documentation.
    
    All JS/TS docs are under /docs/js/ directory.
    """
    
    def __init__(self, docs_root: Optional[Path] = None):
        """Initialize with documentation root path."""
        super().__init__(docs_root)
        self.js_docs_path = self.docs_root / "js"
    
    def extract(self) -> DocsFeatures:
        """
        Extract all documented topics from JS/TS docs.
        
        Returns:
            DocsFeatures with all TypeScript/JavaScript documentation topics
        """
        features = DocsFeatures()
        categories = {}
        
        if not self.js_docs_path.exists():
            return features
        
        # Scan the entire js directory
        topics = self._scan_directory(self.js_docs_path, self.js_docs_path)
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
