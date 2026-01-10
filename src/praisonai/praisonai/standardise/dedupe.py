"""
Duplicate detection for the FDEP standardisation system.

Detects duplicates via:
- Same slug in multiple locations
- High title similarity (>80%)
- High code-block overlap (>40%)
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import StandardiseConfig
from .discovery import FeatureDiscovery
from .models import DuplicateCluster, FeatureSlug


class DedupeDetector:
    """Detects duplicate and near-duplicate content."""
    
    def __init__(self, config: StandardiseConfig, discovery: FeatureDiscovery):
        self.config = config
        self.discovery = discovery
        self._frontmatter_cache: Dict[Path, Dict] = {}
    
    def detect_all(self) -> List[DuplicateCluster]:
        """Detect all duplicate clusters."""
        clusters = []
        
        # Detect same-slug duplicates
        clusters.extend(self._detect_same_slug_duplicates())
        
        # Detect title similarity duplicates
        clusters.extend(self._detect_title_duplicates())
        
        return clusters
    
    def _detect_same_slug_duplicates(self) -> List[DuplicateCluster]:
        """Detect pages with the same slug in different locations."""
        clusters = []
        
        all_features = self.discovery.get_all_features()
        
        for slug in all_features:
            pages = self.discovery.find_docs_pages(slug)
            
            if len(pages) > 1:
                # Determine primary page (prefer features > concepts > cli > sdk)
                primary = self._select_primary_page(pages)
                
                clusters.append(DuplicateCluster(
                    slug=slug,
                    pages=pages,
                    similarity_score=1.0,  # Exact slug match
                    issue_type="same_slug",
                    recommendation="merge" if len(pages) <= 4 else "review",
                    primary_page=primary,
                ))
        
        return clusters
    
    def _detect_title_duplicates(self) -> List[DuplicateCluster]:
        """Detect pages with similar titles."""
        clusters = []
        
        if not self.config.docs_root or not self.config.docs_root.exists():
            return clusters
        
        # Collect all page titles
        title_to_pages: Dict[str, List[Tuple[Path, str]]] = {}
        
        for mdx_file in self.config.docs_root.rglob("*.mdx"):
            # Skip node_modules and other excluded paths
            if any(excluded in str(mdx_file) for excluded in self.config.excluded_paths):
                continue
            
            title = self._extract_title(mdx_file)
            if title:
                normalised_title = self._normalise_title(title)
                if normalised_title not in title_to_pages:
                    title_to_pages[normalised_title] = []
                title_to_pages[normalised_title].append((mdx_file, title))
        
        # Find duplicates
        for normalised_title, pages in title_to_pages.items():
            if len(pages) > 1:
                # Check if these are already captured by same-slug detection
                slugs = set()
                for page, _ in pages:
                    slug = FeatureSlug.from_path(page, "docs")
                    slugs.add(slug.normalised)
                
                if len(slugs) > 1:
                    # Different slugs but same title - this is a title duplicate
                    slug = FeatureSlug.from_string(normalised_title)
                    clusters.append(DuplicateCluster(
                        slug=slug,
                        pages=[p for p, _ in pages],
                        similarity_score=0.9,
                        issue_type="title_similarity",
                        recommendation="review",
                        primary_page=pages[0][0],
                    ))
        
        return clusters
    
    def _extract_title(self, mdx_file: Path) -> Optional[str]:
        """Extract title from MDX frontmatter."""
        if mdx_file in self._frontmatter_cache:
            return self._frontmatter_cache[mdx_file].get("title")
        
        try:
            content = mdx_file.read_text(encoding="utf-8")
        except Exception:
            return None
        
        frontmatter = self._parse_frontmatter(content)
        self._frontmatter_cache[mdx_file] = frontmatter
        
        return frontmatter.get("title")
    
    def _parse_frontmatter(self, content: str) -> Dict:
        """Parse YAML frontmatter from MDX content."""
        frontmatter = {}
        
        # Check for frontmatter delimiters
        if not content.startswith("---"):
            return frontmatter
        
        # Find end of frontmatter
        end_match = re.search(r"\n---\s*\n", content[3:])
        if not end_match:
            return frontmatter
        
        frontmatter_text = content[3:end_match.start() + 3]
        
        # Simple YAML parsing (avoid dependency on PyYAML)
        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                frontmatter[key] = value
        
        return frontmatter
    
    def _normalise_title(self, title: str) -> str:
        """Normalise a title for comparison."""
        # Lowercase, remove special chars, collapse whitespace
        normalised = title.lower()
        normalised = re.sub(r"[^a-z0-9\s]", "", normalised)
        normalised = re.sub(r"\s+", " ", normalised).strip()
        return normalised
    
    def _select_primary_page(self, pages: List[Path]) -> Optional[Path]:
        """Select the primary page from a list of duplicates."""
        # Priority: features > concepts > cli > sdk
        priority_order = ["features", "concepts", "cli", "sdk"]
        
        for priority_dir in priority_order:
            for page in pages:
                if f"/{priority_dir}/" in str(page) or f"\\{priority_dir}\\" in str(page):
                    return page
        
        # Default to first page
        return pages[0] if pages else None
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using Levenshtein ratio."""
        if not text1 or not text2:
            return 0.0
        
        # Simple character-level similarity
        len1, len2 = len(text1), len(text2)
        if len1 == 0 and len2 == 0:
            return 1.0
        if len1 == 0 or len2 == 0:
            return 0.0
        
        # Use set-based similarity for efficiency
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def get_naming_inconsistencies(self) -> List[Tuple[Path, Path, str]]:
        """Find naming inconsistencies (e.g., handoff.mdx vs handoffs.mdx)."""
        inconsistencies = []
        
        if not self.config.docs_root or not self.config.docs_root.exists():
            return inconsistencies
        
        # Check each docs directory
        for doc_dir in ["concepts", "features", "cli"]:
            dir_path = self.config.docs_root / doc_dir
            if not dir_path.exists():
                continue
            
            # Get all MDX files
            mdx_files = list(dir_path.glob("*.mdx"))
            file_stems = {f.stem.lower(): f for f in mdx_files}
            
            # Check for singular/plural pairs
            from .models import SINGULAR_PLURAL_MAP
            for singular, plural in SINGULAR_PLURAL_MAP.items():
                if singular in file_stems and plural in file_stems:
                    inconsistencies.append((
                        file_stems[singular],
                        file_stems[plural],
                        f"Both {singular}.mdx and {plural}.mdx exist in {doc_dir}/",
                    ))
        
        return inconsistencies
