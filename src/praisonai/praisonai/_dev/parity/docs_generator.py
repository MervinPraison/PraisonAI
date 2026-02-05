"""
Documentation Parity Generator for PraisonAI SDKs.

Compares each SDK's implemented features against its documentation.
- Rust: praisonai-rust features vs docs/rust/
- TypeScript: praisonai-ts features vs docs/js/
- Python: praisonaiagents features vs docs/concepts, docs/features, etc.

This is NOT a cross-SDK comparison. Each SDK is compared against its own docs.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

from .docs_extractor import DocsFeatures, DocsTopic, BaseDocsExtractor
from .ts_docs_extractor import TypeScriptDocsExtractor
from .rust_docs_extractor import RustDocsExtractor
from .topic_normalizer import normalize_topic

# Import feature extractors for SDK features
from .rust_extractor import RustFeatureExtractor
from .typescript_extractor import TypeScriptFeatureExtractor


@dataclass
class DocsParitySummary:
    """Summary statistics for documentation parity."""
    implemented_features: int = 0
    documented_features: int = 0
    documented_count: int = 0
    undocumented_count: int = 0
    parity_percent: float = 0.0


class DocsParityGenerator:
    """
    Generates documentation parity tracker files.
    
    Compares each SDK's implemented features against its own documentation
    to identify undocumented features.
    """
    
    def __init__(
        self,
        docs_root: Optional[Path] = None,
        repo_root: Optional[Path] = None
    ):
        """
        Initialize generator with documentation and repository root paths.
        
        Args:
            docs_root: Path to PraisonAIDocs/docs directory
            repo_root: Path to praisonai-package repository
        """
        if docs_root is None:
            docs_root = Path("/Users/praison/PraisonAIDocs/docs")
        if repo_root is None:
            repo_root = self._find_repo_root()
        
        self.docs_root = Path(docs_root).resolve()
        self.repo_root = Path(repo_root).resolve()
        
        # Documentation extractors
        self.ts_docs_extractor = TypeScriptDocsExtractor(self.docs_root)
        self.rust_docs_extractor = RustDocsExtractor(self.docs_root)
        
        # Feature extractors (from existing parity module)
        self.ts_feature_extractor = TypeScriptFeatureExtractor(self.repo_root)
        self.rust_feature_extractor = RustFeatureExtractor(self.repo_root)
        
        # Output paths
        self.ts_md_output = self.repo_root / "src" / "praisonai-ts" / "DOCS_PARITY.md"
        self.rust_md_output = self.repo_root / "src" / "praisonai-rust" / "DOCS_PARITY.md"
    
    def _find_repo_root(self) -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path("/Users/praison/praisonai-package")
    
    def _normalize_feature_name(self, name: str) -> str:
        """Normalize a feature name for comparison with docs."""
        # Convert class names like AgentTeam to agent-team
        normalized = normalize_topic(name)
        return normalized
    
    def _get_feature_names(self, features: List[str]) -> Set[str]:
        """Get normalized feature names."""
        return {self._normalize_feature_name(f) for f in features}
    
    def _get_doc_topic_names(self, docs: DocsFeatures) -> Set[str]:
        """Get normalized doc topic names."""
        return {normalize_topic(t.name) for t in docs.topics}
    
    def _calculate_parity(
        self,
        feature_names: Set[str],
        doc_names: Set[str]
    ) -> DocsParitySummary:
        """
        Calculate parity between features and documentation.
        
        Args:
            feature_names: Set of implemented feature names
            doc_names: Set of documented topic names
            
        Returns:
            DocsParitySummary with statistics
        """
        documented = feature_names & doc_names
        undocumented = feature_names - doc_names
        
        feature_count = len(feature_names)
        documented_count = len(documented)
        undocumented_count = len(undocumented)
        parity = round((documented_count / feature_count * 100) if feature_count > 0 else 0, 1)
        
        return DocsParitySummary(
            implemented_features=feature_count,
            documented_features=len(doc_names),
            documented_count=documented_count,
            undocumented_count=undocumented_count,
            parity_percent=parity,
        )
    
    def generate_typescript_parity(self) -> Dict:
        """
        Generate TypeScript documentation parity data.
        
        Compares TypeScript SDK features against docs/js/ documentation.
        
        Returns:
            Dictionary with parity data
        """
        # Get TypeScript features
        ts_features = self.ts_feature_extractor.extract()
        feature_names = set()
        
        # Collect all feature names from exports
        for export in ts_features.exports:
            feature_names.add(self._normalize_feature_name(export.name))
        
        # Get TypeScript documentation
        docs = self.ts_docs_extractor.extract()
        doc_names = self._get_doc_topic_names(docs)
        
        summary = self._calculate_parity(feature_names, doc_names)
        
        # Build documented and undocumented lists
        documented = sorted(feature_names & doc_names)
        undocumented = sorted(feature_names - doc_names)
        extra_docs = sorted(doc_names - feature_names)  # Docs without features
        
        return {
            'lastUpdated': date.today().isoformat(),
            'sdk': 'TypeScript/JavaScript',
            'summary': {
                'implementedFeatures': summary.implemented_features,
                'documentedTopics': summary.documented_features,
                'featuresWithDocs': summary.documented_count,
                'featuresWithoutDocs': summary.undocumented_count,
                'parityPercent': summary.parity_percent,
            },
            'documented': documented,
            'undocumented': undocumented,
            'extraDocs': extra_docs,
        }
    
    def generate_rust_parity(self) -> Dict:
        """
        Generate Rust documentation parity data.
        
        Compares Rust SDK features against docs/rust/ documentation.
        
        Returns:
            Dictionary with parity data
        """
        # Get Rust features
        rust_features = self.rust_feature_extractor.extract()
        feature_names = set()
        
        # Collect all feature names from exports
        for export in rust_features.exports:
            feature_names.add(self._normalize_feature_name(export.name))
        
        # Get Rust documentation
        docs = self.rust_docs_extractor.extract()
        doc_names = self._get_doc_topic_names(docs)
        
        summary = self._calculate_parity(feature_names, doc_names)
        
        # Build documented and undocumented lists
        documented = sorted(feature_names & doc_names)
        undocumented = sorted(feature_names - doc_names)
        extra_docs = sorted(doc_names - feature_names)  # Docs without features
        
        return {
            'lastUpdated': date.today().isoformat(),
            'sdk': 'Rust',
            'summary': {
                'implementedFeatures': summary.implemented_features,
                'documentedTopics': summary.documented_features,
                'featuresWithDocs': summary.documented_count,
                'featuresWithoutDocs': summary.undocumented_count,
                'parityPercent': summary.parity_percent,
            },
            'documented': documented,
            'undocumented': undocumented,
            'extraDocs': extra_docs,
        }
    
    def write_typescript_markdown(self, check: bool = False) -> int:
        """
        Write TypeScript documentation parity Markdown.
        
        Args:
            check: If True, only check if file is up to date
            
        Returns:
            0 for success, 1 for check failure
        """
        data = self.generate_typescript_parity()
        summary = data['summary']
        
        lines = []
        lines.append("# Documentation Parity Tracker (TypeScript/JavaScript)")
        lines.append("")
        lines.append(f"> **Features:** {summary['implementedFeatures']} | **Documented:** {summary['featuresWithDocs']} | **Parity:** {summary['parityPercent']}%")
        lines.append("")
        lines.append("This report compares **TypeScript SDK features** against **TypeScript documentation** (docs/js/).")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Implemented Features | {summary['implementedFeatures']} |")
        lines.append(f"| Documentation Topics | {summary['documentedTopics']} |")
        lines.append(f"| **Features with Docs** | **{summary['featuresWithDocs']}** |")
        lines.append(f"| **Features without Docs** | **{summary['featuresWithoutDocs']}** |")
        lines.append(f"| **Parity** | **{summary['parityPercent']}%** |")
        lines.append("")
        
        # Documented features
        if data['documented']:
            lines.append("## Documented Features")
            lines.append("")
            for feature in data['documented']:
                lines.append(f"- ✅ `{feature}`")
            lines.append("")
        
        # Undocumented features
        if data['undocumented']:
            lines.append("## Undocumented Features (Need Documentation)")
            lines.append("")
            for feature in data['undocumented']:
                lines.append(f"- ❌ `{feature}`")
            lines.append("")
        
        # Extra docs (docs without corresponding features)
        if data['extraDocs']:
            lines.append("## Documentation Without Corresponding Features")
            lines.append("")
            lines.append("These documentation pages don't match any exported feature:")
            lines.append("")
            for doc in data['extraDocs']:
                lines.append(f"- ℹ️ `{doc}`")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append("*Generated by `praisonai._dev.parity.docs_generator`*")
        lines.append("")
        
        content = '\n'.join(lines)
        
        if check:
            if self.ts_md_output.exists():
                existing = self.ts_md_output.read_text()
                existing_lines = [l for l in existing.split('\n') if not l.startswith('>')]
                content_lines = [l for l in content.split('\n') if not l.startswith('>')]
                if existing_lines == content_lines:
                    print(f"✓ {self.ts_md_output} is up to date")
                    return 0
                print(f"✗ {self.ts_md_output} is out of date")
                return 1
            print(f"✗ {self.ts_md_output} does not exist")
            return 1
        
        self.ts_md_output.parent.mkdir(parents=True, exist_ok=True)
        self.ts_md_output.write_text(content)
        print(f"✓ Generated {self.ts_md_output}")
        return 0
    
    def write_rust_markdown(self, check: bool = False) -> int:
        """
        Write Rust documentation parity Markdown.
        
        Args:
            check: If True, only check if file is up to date
            
        Returns:
            0 for success, 1 for check failure
        """
        data = self.generate_rust_parity()
        summary = data['summary']
        
        lines = []
        lines.append("# Documentation Parity Tracker (Rust)")
        lines.append("")
        lines.append(f"> **Features:** {summary['implementedFeatures']} | **Documented:** {summary['featuresWithDocs']} | **Parity:** {summary['parityPercent']}%")
        lines.append("")
        lines.append("This report compares **Rust SDK features** against **Rust documentation** (docs/rust/).")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Implemented Features | {summary['implementedFeatures']} |")
        lines.append(f"| Documentation Topics | {summary['documentedTopics']} |")
        lines.append(f"| **Features with Docs** | **{summary['featuresWithDocs']}** |")
        lines.append(f"| **Features without Docs** | **{summary['featuresWithoutDocs']}** |")
        lines.append(f"| **Parity** | **{summary['parityPercent']}%** |")
        lines.append("")
        
        # Documented features
        if data['documented']:
            lines.append("## Documented Features")
            lines.append("")
            for feature in data['documented']:
                lines.append(f"- ✅ `{feature}`")
            lines.append("")
        
        # Undocumented features
        if data['undocumented']:
            lines.append("## Undocumented Features (Need Documentation)")
            lines.append("")
            for feature in data['undocumented']:
                lines.append(f"- ❌ `{feature}`")
            lines.append("")
        
        # Extra docs (docs without corresponding features)
        if data['extraDocs']:
            lines.append("## Documentation Without Corresponding Features")
            lines.append("")
            lines.append("These documentation pages don't match any exported feature:")
            lines.append("")
            for doc in data['extraDocs']:
                lines.append(f"- ℹ️ `{doc}`")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append("*Generated by `praisonai._dev.parity.docs_generator`*")
        lines.append("")
        
        content = '\n'.join(lines)
        
        if check:
            if self.rust_md_output.exists():
                existing = self.rust_md_output.read_text()
                existing_lines = [l for l in existing.split('\n') if not l.startswith('>')]
                content_lines = [l for l in content.split('\n') if not l.startswith('>')]
                if existing_lines == content_lines:
                    print(f"✓ {self.rust_md_output} is up to date")
                    return 0
                print(f"✗ {self.rust_md_output} is out of date")
                return 1
            print(f"✗ {self.rust_md_output} does not exist")
            return 1
        
        self.rust_md_output.parent.mkdir(parents=True, exist_ok=True)
        self.rust_md_output.write_text(content)
        print(f"✓ Generated {self.rust_md_output}")
        return 0
    
    def write_typescript_json(self, check: bool = False) -> int:
        """Write TypeScript documentation parity JSON (optional)."""
        data = self.generate_typescript_parity()
        json_output = self.ts_md_output.with_suffix('.json')
        content = json.dumps(data, indent=2, sort_keys=True)
        
        if check:
            if json_output.exists():
                existing = json_output.read_text()
                existing_data = json.loads(existing)
                existing_data.pop('lastUpdated', None)
                data.pop('lastUpdated', None)
                if json.dumps(existing_data, sort_keys=True) == json.dumps(data, sort_keys=True):
                    print(f"✓ {json_output} is up to date")
                    return 0
                print(f"✗ {json_output} is out of date")
                return 1
            print(f"✗ {json_output} does not exist")
            return 1
        
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(content)
        print(f"✓ Generated {json_output}")
        return 0
    
    def write_rust_json(self, check: bool = False) -> int:
        """Write Rust documentation parity JSON (optional)."""
        data = self.generate_rust_parity()
        json_output = self.rust_md_output.with_suffix('.json')
        content = json.dumps(data, indent=2, sort_keys=True)
        
        if check:
            if json_output.exists():
                existing = json_output.read_text()
                existing_data = json.loads(existing)
                existing_data.pop('lastUpdated', None)
                data.pop('lastUpdated', None)
                if json.dumps(existing_data, sort_keys=True) == json.dumps(data, sort_keys=True):
                    print(f"✓ {json_output} is up to date")
                    return 0
                print(f"✗ {json_output} is out of date")
                return 1
            print(f"✗ {json_output} does not exist")
            return 1
        
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(content)
        print(f"✓ Generated {json_output}")
        return 0


def generate_docs_parity(
    docs_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    target: str = 'all',
    check: bool = False,
    include_json: bool = False,
) -> int:
    """
    Generate documentation parity tracker files.
    
    Args:
        docs_root: Path to documentation root
        repo_root: Path to repository root
        target: 'typescript', 'ts', 'rust', 'rs', or 'all'
        check: If True, check if files are up to date
        include_json: If True, also generate JSON files (default: MD only)
        
    Returns:
        Exit code (0 for success, 1 for check failure)
    """
    generator = DocsParityGenerator(docs_root=docs_root, repo_root=repo_root)
    exit_code = 0
    
    if target in ('typescript', 'ts', 'all'):
        result = generator.write_typescript_markdown(check=check)
        if result != 0:
            exit_code = result
        if include_json:
            result = generator.write_typescript_json(check=check)
            if result != 0:
                exit_code = result
    
    if target in ('rust', 'rs', 'all'):
        result = generator.write_rust_markdown(check=check)
        if result != 0:
            exit_code = result
        if include_json:
            result = generator.write_rust_json(check=check)
            if result != 0:
                exit_code = result
    
    return exit_code


def main():
    """CLI entry point for the docs parity generator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate documentation parity tracker files"
    )
    parser.add_argument(
        "-t", "--target",
        choices=["typescript", "ts", "rust", "rs", "all"],
        default="all",
        help="Target SDK to generate parity for (default: all)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files are up to date (exit 1 if not)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also generate JSON files (default: Markdown only)"
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        help="Path to documentation root directory"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Path to repository root directory"
    )
    
    args = parser.parse_args()
    
    exit_code = generate_docs_parity(
        docs_root=args.docs_root,
        repo_root=args.repo_root,
        target=args.target,
        check=args.check,
        include_json=args.json,
    )
    
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
