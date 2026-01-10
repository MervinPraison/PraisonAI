"""
Feature discovery for the FDEP standardisation system.

Discovers features from:
- SDK modules (praisonaiagents/*)
- CLI features (praisonai/cli/features/*)
- Docs pages (docs/**)
- Examples (examples/python/**)
"""

from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import StandardiseConfig
from .models import FeatureSlug


class FeatureDiscovery:
    """Discovers features from various sources in the codebase."""
    
    # Directories to skip during discovery
    SKIP_DIRS = {
        "__pycache__", ".git", ".venv", "venv", "node_modules",
        "dist", "build", ".pytest_cache", ".mypy_cache",
    }
    
    # Files to skip
    SKIP_FILES = {"__init__.py", "base.py", "utils.py", "helpers.py"}
    
    def __init__(self, config: StandardiseConfig):
        self.config = config
        self._sdk_features: Optional[Set[FeatureSlug]] = None
        self._cli_features: Optional[Set[FeatureSlug]] = None
        self._docs_features: Optional[Set[FeatureSlug]] = None
        self._example_features: Optional[Set[FeatureSlug]] = None
    
    def discover_all(self) -> Dict[str, Set[FeatureSlug]]:
        """Discover features from all sources."""
        return {
            "sdk": self.discover_sdk_features(),
            "cli": self.discover_cli_features(),
            "docs": self.discover_docs_features(),
            "examples": self.discover_example_features(),
        }
    
    def get_all_features(self) -> Set[FeatureSlug]:
        """Get union of all discovered features."""
        all_sources = self.discover_all()
        result: Set[FeatureSlug] = set()
        for features in all_sources.values():
            result.update(features)
        return result
    
    def discover_sdk_features(self) -> Set[FeatureSlug]:
        """Discover features from SDK modules."""
        if self._sdk_features is not None:
            return self._sdk_features
        
        self._sdk_features = set()
        
        if not self.config.sdk_root or not self.config.sdk_root.exists():
            return self._sdk_features
        
        # Each top-level directory in SDK is a feature module
        for item in self.config.sdk_root.iterdir():
            if not item.is_dir():
                continue
            if item.name in self.SKIP_DIRS:
                continue
            if item.name.startswith("."):
                continue
            
            slug = FeatureSlug.from_path(item, "sdk")
            if slug.is_valid:
                self._sdk_features.add(slug)
        
        return self._sdk_features
    
    def discover_cli_features(self) -> Set[FeatureSlug]:
        """Discover features from CLI feature files."""
        if self._cli_features is not None:
            return self._cli_features
        
        self._cli_features = set()
        
        if not self.config.cli_root or not self.config.cli_root.exists():
            return self._cli_features
        
        # Check features directory
        features_dir = self.config.cli_root / "features"
        if features_dir.exists():
            for item in features_dir.iterdir():
                if not item.is_file():
                    continue
                if item.suffix != ".py":
                    continue
                if item.name in self.SKIP_FILES:
                    continue
                
                slug = FeatureSlug.from_path(item, "cli")
                if slug.is_valid:
                    self._cli_features.add(slug)
        
        # Check commands directory
        commands_dir = self.config.cli_root / "commands"
        if commands_dir.exists():
            for item in commands_dir.iterdir():
                if not item.is_file():
                    continue
                if item.suffix != ".py":
                    continue
                if item.name in self.SKIP_FILES:
                    continue
                
                slug = FeatureSlug.from_path(item, "cli")
                if slug.is_valid:
                    self._cli_features.add(slug)
        
        return self._cli_features
    
    def discover_docs_features(self) -> Set[FeatureSlug]:
        """Discover features from docs pages."""
        if self._docs_features is not None:
            return self._docs_features
        
        self._docs_features = set()
        
        if not self.config.docs_root or not self.config.docs_root.exists():
            return self._docs_features
        
        # Scan key docs directories
        docs_dirs = ["concepts", "features", "cli", "sdk"]
        
        for dir_name in docs_dirs:
            dir_path = self.config.docs_root / dir_name
            if not dir_path.exists():
                continue
            
            self._scan_docs_directory(dir_path)
        
        return self._docs_features
    
    def _scan_docs_directory(self, directory: Path, depth: int = 0):
        """Recursively scan a docs directory for feature slugs."""
        if depth > 3:  # Limit recursion depth
            return
        
        for item in directory.iterdir():
            if item.name in self.SKIP_DIRS:
                continue
            if item.name.startswith("."):
                continue
            
            if item.is_file() and item.suffix == ".mdx":
                slug = FeatureSlug.from_path(item, "docs")
                if slug.is_valid:
                    self._docs_features.add(slug)
            elif item.is_dir():
                # Directory name itself might be a feature
                slug = FeatureSlug.from_path(item, "docs")
                if slug.is_valid:
                    self._docs_features.add(slug)
                # Recurse into subdirectory
                self._scan_docs_directory(item, depth + 1)
    
    def discover_example_features(self) -> Set[FeatureSlug]:
        """Discover features from examples."""
        if self._example_features is not None:
            return self._example_features
        
        self._example_features = set()
        
        if not self.config.examples_root or not self.config.examples_root.exists():
            return self._example_features
        
        # Each top-level directory in examples is a feature
        for item in self.config.examples_root.iterdir():
            if not item.is_dir():
                continue
            if item.name in self.SKIP_DIRS:
                continue
            if item.name.startswith("."):
                continue
            
            slug = FeatureSlug.from_path(item, "examples")
            if slug.is_valid:
                self._example_features.add(slug)
        
        return self._example_features
    
    def get_feature_sources(self, slug: FeatureSlug) -> Dict[str, bool]:
        """Get which sources contain a given feature."""
        return {
            "sdk": slug in self.discover_sdk_features(),
            "cli": slug in self.discover_cli_features(),
            "docs": slug in self.discover_docs_features(),
            "examples": slug in self.discover_example_features(),
        }
    
    def find_docs_pages(self, slug: FeatureSlug) -> List[Path]:
        """Find all docs pages for a given feature slug."""
        pages = []
        
        if not self.config.docs_root or not self.config.docs_root.exists():
            return pages
        
        # Search in key directories
        search_dirs = [
            self.config.docs_root / "concepts",
            self.config.docs_root / "features",
            self.config.docs_root / "cli",
        ]
        
        # Also search SDK docs
        sdk_docs = self.config.docs_root / "sdk" / "praisonaiagents"
        if sdk_docs.exists():
            search_dirs.append(sdk_docs)
        
        slug_str = slug.normalised
        slug_variants = {slug_str, slug_str.replace("-", "_")}
        
        # Add singular/plural variants
        from .models import SINGULAR_PLURAL_MAP
        for singular, plural in SINGULAR_PLURAL_MAP.items():
            if slug_str == plural:
                slug_variants.add(singular)
            elif slug_str == singular:
                slug_variants.add(plural)
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            self._find_pages_recursive(search_dir, slug_variants, pages)
        
        return pages
    
    def _find_pages_recursive(self, directory: Path, slug_variants: Set[str], 
                               pages: List[Path], depth: int = 0):
        """Recursively find pages matching slug variants."""
        if depth > 4:
            return
        
        for item in directory.iterdir():
            if item.name in self.SKIP_DIRS:
                continue
            
            if item.is_file() and item.suffix == ".mdx":
                stem = item.stem.lower().replace("_", "-")
                if stem in slug_variants:
                    pages.append(item)
            elif item.is_dir():
                dir_name = item.name.lower().replace("_", "-")
                if dir_name in slug_variants:
                    # Check for index or main file in this directory
                    for mdx_file in item.glob("*.mdx"):
                        pages.append(mdx_file)
                else:
                    self._find_pages_recursive(item, slug_variants, pages, depth + 1)
    
    def find_examples(self, slug: FeatureSlug) -> List[Path]:
        """Find all example files for a given feature slug."""
        examples = []
        
        if not self.config.examples_root or not self.config.examples_root.exists():
            return examples
        
        slug_str = slug.normalised
        slug_variants = {slug_str, slug_str.replace("-", "_")}
        
        # Check for feature directory
        for variant in slug_variants:
            feature_dir = self.config.examples_root / variant
            if feature_dir.exists() and feature_dir.is_dir():
                for py_file in feature_dir.glob("*.py"):
                    examples.append(py_file)
        
        return examples
    
    def get_sdk_module_path(self, slug: FeatureSlug) -> Optional[Path]:
        """Get the SDK module path for a feature."""
        if not self.config.sdk_root or not self.config.sdk_root.exists():
            return None
        
        slug_str = slug.normalised
        variants = [slug_str, slug_str.replace("-", "_")]
        
        for variant in variants:
            module_path = self.config.sdk_root / variant
            if module_path.exists() and module_path.is_dir():
                return module_path
        
        return None
    
    def get_cli_feature_path(self, slug: FeatureSlug) -> Optional[Path]:
        """Get the CLI feature file path for a feature."""
        if not self.config.cli_root or not self.config.cli_root.exists():
            return None
        
        slug_str = slug.normalised
        variants = [slug_str, slug_str.replace("-", "_")]
        
        # Check features directory
        features_dir = self.config.cli_root / "features"
        if features_dir.exists():
            for variant in variants:
                feature_path = features_dir / f"{variant}.py"
                if feature_path.exists():
                    return feature_path
        
        # Check commands directory
        commands_dir = self.config.cli_root / "commands"
        if commands_dir.exists():
            for variant in variants:
                command_path = commands_dir / f"{variant}.py"
                if command_path.exists():
                    return command_path
        
        return None
