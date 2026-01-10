"""
Drift detection for the FDEP standardisation system.

Detects drift between:
- SDK exports vs SDK docs
- CLI help/flags vs CLI docs
"""

import ast
import re
from pathlib import Path
from typing import List, Optional, Set

from .config import StandardiseConfig
from .discovery import FeatureDiscovery
from .models import DriftItem, DriftReport, FeatureSlug


class DriftDetector:
    """Detects drift between code and documentation."""
    
    def __init__(self, config: StandardiseConfig, discovery: FeatureDiscovery):
        self.config = config
        self.discovery = discovery
    
    def detect_all(self) -> List[DriftReport]:
        """Detect drift for all features."""
        reports = []
        
        all_features = self.discovery.get_all_features()
        
        for slug in all_features:
            report = self.detect_feature_drift(slug)
            if report.has_drift:
                reports.append(report)
        
        return reports
    
    def detect_feature_drift(self, slug: FeatureSlug) -> DriftReport:
        """Detect drift for a single feature."""
        sdk_drift = self._detect_sdk_drift(slug)
        cli_drift = self._detect_cli_drift(slug)
        
        return DriftReport(
            slug=slug,
            sdk_drift=sdk_drift,
            cli_drift=cli_drift,
        )
    
    def _detect_sdk_drift(self, slug: FeatureSlug) -> List[DriftItem]:
        """Detect drift between SDK module and SDK docs."""
        drift_items = []
        
        # Get SDK module path
        sdk_module = self.discovery.get_sdk_module_path(slug)
        if not sdk_module or not sdk_module.exists():
            return drift_items
        
        # Extract public exports from SDK module
        sdk_exports = self._extract_sdk_exports(sdk_module)
        
        # Extract documented items from SDK docs
        sdk_docs = self._get_sdk_docs_path(slug)
        if sdk_docs:
            documented_items = self._extract_documented_items(sdk_docs)
        else:
            documented_items = set()
        
        # Find items in SDK but not in docs
        for export in sdk_exports:
            if export not in documented_items:
                drift_items.append(DriftItem(
                    name=export,
                    source="sdk",
                    missing_in="docs",
                    item_type="class" if export[0].isupper() else "function",
                ))
        
        # Find items in docs but not in SDK
        for item in documented_items:
            if item not in sdk_exports:
                drift_items.append(DriftItem(
                    name=item,
                    source="docs",
                    missing_in="sdk",
                    item_type="class" if item[0].isupper() else "function",
                ))
        
        return drift_items
    
    def _detect_cli_drift(self, slug: FeatureSlug) -> List[DriftItem]:
        """Detect drift between CLI feature and CLI docs."""
        drift_items = []
        
        # Get CLI feature path
        cli_feature = self.discovery.get_cli_feature_path(slug)
        if not cli_feature or not cli_feature.exists():
            return drift_items
        
        # Extract CLI flags/commands from code
        cli_flags = self._extract_cli_flags(cli_feature)
        
        # Extract documented flags from CLI docs
        cli_docs = self._get_cli_docs_path(slug)
        if cli_docs:
            documented_flags = self._extract_documented_flags(cli_docs)
        else:
            documented_flags = set()
        
        # Find flags in code but not in docs
        for flag in cli_flags:
            if flag not in documented_flags:
                drift_items.append(DriftItem(
                    name=flag,
                    source="cli",
                    missing_in="docs",
                    item_type="flag",
                ))
        
        return drift_items
    
    def _extract_sdk_exports(self, module_path: Path) -> Set[str]:
        """Extract public exports from an SDK module."""
        exports = set()
        
        # Check __init__.py for __all__
        init_file = module_path / "__init__.py"
        if init_file.exists():
            try:
                content = init_file.read_text(encoding="utf-8")
                # Look for __all__ = [...]
                all_match = re.search(r"__all__\s*=\s*\[(.*?)\]", content, re.DOTALL)
                if all_match:
                    items = re.findall(r'["\'](\w+)["\']', all_match.group(1))
                    exports.update(items)
            except Exception:
                pass
        
        # Also scan for public classes and functions
        for py_file in module_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        if not node.name.startswith("_"):
                            exports.add(node.name)
                    elif isinstance(node, ast.FunctionDef):
                        if not node.name.startswith("_"):
                            exports.add(node.name)
            except Exception:
                pass
        
        return exports
    
    def _extract_cli_flags(self, cli_file: Path) -> Set[str]:
        """Extract CLI flags from a CLI feature file."""
        flags = set()
        
        try:
            content = cli_file.read_text(encoding="utf-8")
            
            # Look for click.option or argparse add_argument patterns
            # click: @click.option("--flag-name", ...)
            click_flags = re.findall(r'@click\.option\(["\'](-{1,2}[\w-]+)["\']', content)
            flags.update(click_flags)
            
            # argparse: parser.add_argument("--flag-name", ...)
            argparse_flags = re.findall(r'add_argument\(["\'](-{1,2}[\w-]+)["\']', content)
            flags.update(argparse_flags)
            
            # Also look for flag definitions in strings
            string_flags = re.findall(r'["\'](-{2}[\w-]+)["\']', content)
            flags.update(string_flags)
            
        except Exception:
            pass
        
        return flags
    
    def _extract_documented_items(self, docs_path: Path) -> Set[str]:
        """Extract documented class/function names from docs."""
        items = set()
        
        try:
            content = docs_path.read_text(encoding="utf-8")
            
            # Look for class/function references in code blocks
            # Pattern: `ClassName` or `function_name`
            backtick_items = re.findall(r'`(\w+)`', content)
            items.update(backtick_items)
            
            # Look for headings that might be class/function names
            heading_items = re.findall(r'^#{1,3}\s+`?(\w+)`?', content, re.MULTILINE)
            items.update(heading_items)
            
        except Exception:
            pass
        
        return items
    
    def _extract_documented_flags(self, docs_path: Path) -> Set[str]:
        """Extract documented CLI flags from docs."""
        flags = set()
        
        try:
            content = docs_path.read_text(encoding="utf-8")
            
            # Look for flags in code blocks and inline code
            flag_patterns = re.findall(r'`(-{1,2}[\w-]+)`', content)
            flags.update(flag_patterns)
            
            # Also look for flags in plain text
            text_flags = re.findall(r'\s(-{2}[\w-]+)\s', content)
            flags.update(text_flags)
            
        except Exception:
            pass
        
        return flags
    
    def _get_sdk_docs_path(self, slug: FeatureSlug) -> Optional[Path]:
        """Get the SDK docs path for a feature."""
        if not self.config.docs_root:
            return None
        
        sdk_docs = self.config.docs_root / "sdk" / "praisonaiagents"
        if not sdk_docs.exists():
            return None
        
        slug_str = slug.normalised
        variants = [slug_str, slug_str.replace("-", "_")]
        
        for variant in variants:
            module_dir = sdk_docs / variant
            if module_dir.exists():
                for mdx_file in module_dir.glob("*.mdx"):
                    return mdx_file
        
        return None
    
    def _get_cli_docs_path(self, slug: FeatureSlug) -> Optional[Path]:
        """Get the CLI docs path for a feature."""
        if not self.config.docs_root:
            return None
        
        cli_docs = self.config.docs_root / "cli"
        if not cli_docs.exists():
            return None
        
        slug_str = slug.normalised
        variants = [slug_str, slug_str.replace("-", "_")]
        
        for variant in variants:
            path = cli_docs / f"{variant}.mdx"
            if path.exists():
                return path
        
        return None
