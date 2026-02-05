"""
Feature Parity Tracker Generator for PraisonAI SDKs.

Generates JSON files tracking feature parity between Python SDK (source of truth)
and other implementations (TypeScript, Rust).
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from .python_extractor import PythonFeatureExtractor, PythonFeatures
from .rust_extractor import RustFeatureExtractor, RustFeatures
from .typescript_extractor import TypeScriptFeatureExtractor, TypeScriptFeatures


def _escape_md(text: str) -> str:
    """Escape markdown special characters."""
    return text.replace('|', '\\|').replace('_', '\\_')


@dataclass
class FeatureGap:
    """Represents a feature gap between implementations."""
    feature: str
    python: bool
    typescript: bool
    rust: bool = False
    priority: str = 'P3'  # P0=critical, P1=high, P2=medium, P3=low
    effort: str = 'medium'  # low, medium, high
    status: str = 'TODO'  # TODO, IN_PROGRESS, DONE
    category: str = 'other'


@dataclass
class ParitySummary:
    """Summary statistics for parity tracking."""
    python_core_features: int = 0
    python_wrapper_features: int = 0
    typescript_features: int = 0
    rust_features: int = 0
    gap_count: int = 0
    priority_p0: int = 0
    priority_p1: int = 0
    priority_p2: int = 0
    priority_p3: int = 0


class ParityTrackerGenerator:
    """
    Generates feature parity tracker JSON files.
    
    Compares Python SDK (source of truth) against TypeScript and Rust
    implementations to identify gaps and track progress.
    """
    
    # Priority mapping based on feature categories
    PRIORITY_MAPPING = {
        'agent': 'P0',
        'tools': 'P0',
        'workflows': 'P1',
        'memory': 'P1',
        'knowledge': 'P1',
        'session': 'P1',
        'db': 'P1',
        'guardrails': 'P2',
        'eval': 'P2',
        'skills': 'P2',
        'telemetry': 'P2',
        'mcp': 'P2',
        'context': 'P2',
        'planning': 'P2',
        'rag': 'P2',
        'ui': 'P3',
        'config': 'P3',
        'plugins': 'P3',
        'trace': 'P3',
        'other': 'P3',
    }
    
    # Effort mapping based on feature type
    EFFORT_MAPPING = {
        'class': 'high',
        'function': 'low',
        'type': 'low',
        'constant': 'low',
        'protocol': 'medium',
    }
    
    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize generator with repository root path."""
        if repo_root is None:
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()
        
        self.python_extractor = PythonFeatureExtractor(repo_root)
        self.ts_extractor = TypeScriptFeatureExtractor(repo_root)
        self.rust_extractor = RustFeatureExtractor(repo_root)
        
        # Output paths
        self.ts_output = self.repo_root / "src" / "praisonai-ts" / "FEATURE_PARITY_TRACKER.json"
        self.ts_md_output = self.repo_root / "src" / "praisonai-ts" / "PARITY.md"
        self.rust_output = self.repo_root / "src" / "praisonai-rust" / "FEATURE_PARITY_TRACKER.json"
        self.rust_md_output = self.repo_root / "src" / "praisonai-rust" / "PARITY.md"
    
    def _find_repo_root(self) -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path("/Users/praison/praisonai-package")
    
    def generate(self) -> dict:
        """Generate the parity tracker data structure."""
        # Extract features from both SDKs
        python_features = self.python_extractor.extract()
        ts_features = self.ts_extractor.extract()
        
        # Get version from existing tracker or default
        version = self._get_current_version()
        
        # Build the tracker structure
        tracker = {
            'version': version,
            'lastUpdated': date.today().isoformat(),
            'generatedBy': 'praisonai._dev.parity.generator',
            'sourceOfTruth': 'Python SDK (praisonaiagents)',
            'summary': self._build_summary(python_features, ts_features),
            'pythonCoreSDK': self._build_python_section(python_features),
            'pythonWrapper': self._build_wrapper_section(python_features),
            'typescriptSDK': self._build_typescript_section(ts_features),
            'gapMatrix': self._build_gap_matrix(python_features, ts_features),
        }
        
        return tracker
    
    def _get_current_version(self) -> str:
        """Get version from existing tracker or pyproject.toml."""
        # Try to read from existing tracker
        if self.ts_output.exists():
            try:
                with open(self.ts_output, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    return existing.get('version', '1.0.0')
            except (json.JSONDecodeError, IOError):
                pass
        
        # Try to read from pyproject.toml
        pyproject = self.repo_root / "src" / "praisonai-agents" / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, 'r', encoding='utf-8') as f:
                    content = f.read()
                    import re
                    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                    if match:
                        return match.group(1)
            except IOError:
                pass
        
        return '1.0.0'
    
    def _build_summary(self, python: PythonFeatures, ts: TypeScriptFeatures) -> dict:
        """Build summary statistics."""
        python_exports = {e.name for e in python.exports}
        ts_exports = ts.get_export_names()
        
        # Count gaps (Python features not in TypeScript)
        gaps = python_exports - ts_exports
        
        # Count by priority
        priority_counts = {'P0': 0, 'P1': 0, 'P2': 0, 'P3': 0}
        for export in python.exports:
            if export.name in gaps:
                priority = self.PRIORITY_MAPPING.get(export.category, 'P3')
                priority_counts[priority] += 1
        
        return {
            'pythonCoreFeatures': len(python.exports),
            'pythonWrapperFeatures': len(python.cli_features),
            'typescriptFeatures': len(ts.exports),
            'gapCount': len(gaps),
            'priorityP0': priority_counts['P0'],
            'priorityP1': priority_counts['P1'],
            'priorityP2': priority_counts['P2'],
            'priorityP3': priority_counts['P3'],
        }
    
    def _build_python_section(self, features: PythonFeatures) -> dict:
        """Build Python SDK section."""
        return {
            'path': str(self.repo_root / "src" / "praisonai-agents" / "praisonaiagents"),
            'exports': sorted([e.name for e in features.exports]),
            'modules': {
                name: sorted(mod.exports)
                for name, mod in sorted(features.modules.items())
            },
        }
    
    def _build_wrapper_section(self, features: PythonFeatures) -> dict:
        """Build Python wrapper section."""
        return {
            'path': str(self.repo_root / "src" / "praisonai" / "praisonai"),
            'cliFeatures': sorted(features.cli_features),
        }
    
    def _build_typescript_section(self, features: TypeScriptFeatures) -> dict:
        """Build TypeScript SDK section."""
        return {
            'path': str(self.repo_root / "src" / "praisonai-ts" / "src"),
            'exports': sorted([e.name for e in features.exports if not e.is_type]),
            'modules': {
                name: sorted(mod.exports)
                for name, mod in sorted(features.modules.items())
            },
        }
    
    def _build_gap_matrix(self, python: PythonFeatures, ts: TypeScriptFeatures) -> dict:
        """Build the gap matrix showing feature-by-feature comparison."""
        python_exports = {e.name: e for e in python.exports}
        ts_export_names = ts.get_export_names()
        
        # Group by priority
        gaps_by_priority: Dict[str, List[dict]] = {
            'P0_CoreParity': [],
            'P1_Persistence': [],
            'P2_CLI': [],
            'P3_Advanced': [],
        }
        
        # Priority to key mapping
        priority_to_key = {
            'P0': 'P0_CoreParity',
            'P1': 'P1_Persistence',
            'P2': 'P2_CLI',
            'P3': 'P3_Advanced',
        }
        
        for name, export in sorted(python_exports.items()):
            in_ts = name in ts_export_names
            priority = self.PRIORITY_MAPPING.get(export.category, 'P3')
            effort = self.EFFORT_MAPPING.get(export.kind, 'medium')
            status = 'DONE' if in_ts else 'TODO'
            
            gap_entry = {
                'feature': name,
                'python': True,
                'typescript': in_ts,
                'priority': priority,
                'effort': effort,
                'status': status,
                'category': export.category,
            }
            
            key = priority_to_key.get(priority, 'P3_Advanced')
            gaps_by_priority[key].append(gap_entry)
        
        return gaps_by_priority
    
    def write_typescript(self, check: bool = False) -> int:
        """
        Write TypeScript parity tracker.
        
        Args:
            check: If True, only check if file is up to date
            
        Returns:
            0 for success, 1 for check failure
        """
        tracker = self.generate()
        content = json.dumps(tracker, indent=2, ensure_ascii=False) + '\n'
        
        if check:
            if self.ts_output.exists():
                with open(self.ts_output, 'r', encoding='utf-8') as f:
                    existing = f.read()
                # Compare ignoring lastUpdated field
                existing_data = json.loads(existing)
                tracker_copy = json.loads(content)
                existing_data.pop('lastUpdated', None)
                tracker_copy.pop('lastUpdated', None)
                if existing_data == tracker_copy:
                    print(f"✓ {self.ts_output} is up to date")
                    return 0
                else:
                    print(f"✗ {self.ts_output} is out of date")
                    return 1
            else:
                print(f"✗ {self.ts_output} does not exist")
                return 1
        
        # Ensure directory exists
        self.ts_output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.ts_output, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ Generated {self.ts_output}")
        return 0
    
    def write_rust(self, check: bool = False) -> int:
        """
        Write Rust parity tracker.
        
        Args:
            check: If True, only check if file is up to date
            
        Returns:
            0 for success, 1 for check failure
        """
        python_features = self.python_extractor.extract()
        rust_features = self.rust_extractor.extract()
        
        # Calculate gap (Python features not in Rust)
        python_exports = {e.name for e in python_features.exports}
        rust_exports = rust_features.get_export_names()
        gap_count = len(python_exports - rust_exports)
        
        # Determine status based on implementation progress
        rust_count = len(rust_exports)
        python_count = len(python_exports)
        if rust_count == 0:
            status = 'NOT_STARTED'
        elif rust_count < python_count * 0.25:
            status = 'EARLY_DEVELOPMENT'
        elif rust_count < python_count * 0.75:
            status = 'IN_PROGRESS'
        elif rust_count < python_count:
            status = 'NEAR_PARITY'
        else:
            status = 'PARITY_ACHIEVED'
        
        tracker = {
            'version': self._get_current_version(),
            'lastUpdated': date.today().isoformat(),
            'generatedBy': 'praisonai._dev.parity.generator',
            'sourceOfTruth': 'Python SDK (praisonaiagents)',
            'status': status,
            'summary': {
                'pythonCoreFeatures': python_count,
                'rustFeatures': rust_count,
                'gapCount': gap_count,
                'parityPercentage': round((rust_count / python_count * 100) if python_count > 0 else 0, 1),
            },
            'pythonCoreSDK': {
                'exports': sorted([e.name for e in python_features.exports]),
            },
            'rustSDK': {
                'path': str(self.repo_root / "src" / "praisonai-rust"),
                'exports': sorted(list(rust_exports)),
                'modules': {
                    name: sorted(mod.exports)
                    for name, mod in sorted(rust_features.modules.items())
                },
                'cargoFeatures': rust_features.cargo_features,
            },
            'gapMatrix': self._build_rust_gap_matrix(python_features, rust_features),
        }
        
        content = json.dumps(tracker, indent=2, ensure_ascii=False) + '\n'
        
        if check:
            if self.rust_output.exists():
                with open(self.rust_output, 'r', encoding='utf-8') as f:
                    existing = f.read()
                existing_data = json.loads(existing)
                tracker_copy = json.loads(content)
                existing_data.pop('lastUpdated', None)
                tracker_copy.pop('lastUpdated', None)
                if existing_data == tracker_copy:
                    print(f"✓ {self.rust_output} is up to date")
                    return 0
                else:
                    print(f"✗ {self.rust_output} is out of date")
                    return 1
            else:
                print(f"✗ {self.rust_output} does not exist")
                return 1
        
        # Ensure directory exists
        self.rust_output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.rust_output, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ Generated {self.rust_output}")
        return 0
    
    def _build_rust_gap_matrix(self, python: PythonFeatures, rust: RustFeatures) -> dict:
        """Build the gap matrix for Rust showing feature-by-feature comparison."""
        python_exports = {e.name: e for e in python.exports}
        rust_export_names = rust.get_export_names()
        
        # Group by priority
        gaps_by_priority: Dict[str, List[dict]] = {
            'P0_CoreParity': [],
            'P1_Persistence': [],
            'P2_CLI': [],
            'P3_Advanced': [],
        }
        
        # Priority to key mapping
        priority_to_key = {
            'P0': 'P0_CoreParity',
            'P1': 'P1_Persistence',
            'P2': 'P2_CLI',
            'P3': 'P3_Advanced',
        }
        
        for name, export in sorted(python_exports.items()):
            in_rust = name in rust_export_names
            priority = self.PRIORITY_MAPPING.get(export.category, 'P3')
            effort = self.EFFORT_MAPPING.get(export.kind, 'medium')
            status = 'DONE' if in_rust else 'TODO'
            
            gap_entry = {
                'feature': name,
                'python': True,
                'rust': in_rust,
                'priority': priority,
                'effort': effort,
                'status': status,
                'category': export.category,
            }
            
            key = priority_to_key.get(priority, 'P3_Advanced')
            gaps_by_priority[key].append(gap_entry)
        
        return gaps_by_priority
    
    def generate_markdown(self) -> str:
        """
        Generate human-readable markdown table output.
        
        Returns:
            Markdown string with parity tables
        """
        tracker = self.generate()
        lines = []
        
        # Header
        lines.append("# Feature Parity Tracker")
        lines.append("")
        lines.append(f"> **Version:** {tracker['version']} | **Last Updated:** {tracker['lastUpdated']}")
        lines.append(f"> **Source of Truth:** {tracker['sourceOfTruth']}")
        lines.append("")
        
        # Summary
        summary = tracker['summary']
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Python Core Features | {summary['pythonCoreFeatures']} |")
        lines.append(f"| Python Wrapper Features | {summary['pythonWrapperFeatures']} |")
        lines.append(f"| TypeScript Features | {summary['typescriptFeatures']} |")
        lines.append(f"| **Gap Count** | **{summary['gapCount']}** |")
        lines.append(f"| P0 (Critical) | {summary['priorityP0']} |")
        lines.append(f"| P1 (High) | {summary['priorityP1']} |")
        lines.append(f"| P2 (Medium) | {summary['priorityP2']} |")
        lines.append(f"| P3 (Low) | {summary['priorityP3']} |")
        lines.append("")
        
        # Gap Matrix by Priority
        lines.append("## Gap Matrix")
        lines.append("")
        
        for priority_key, gaps in tracker['gapMatrix'].items():
            if not gaps:
                continue
            
            # Count done vs todo
            done_count = sum(1 for g in gaps if g['status'] == 'DONE')
            todo_count = len(gaps) - done_count
            
            lines.append(f"### {priority_key} ({done_count} done, {todo_count} todo)")
            lines.append("")
            lines.append("| Feature | Python | TypeScript | Effort | Status |")
            lines.append("|---------|--------|------------|--------|--------|")
            
            for gap in sorted(gaps, key=lambda x: (x['status'] != 'TODO', x['feature'])):
                py = "✅" if gap['python'] else "❌"
                ts = "✅" if gap['typescript'] else "❌"
                status = "✅ DONE" if gap['status'] == 'DONE' else "⏳ TODO"
                feature = _escape_md(gap['feature'])
                lines.append(f"| `{feature}` | {py} | {ts} | {gap['effort']} | {status} |")
            
            lines.append("")
        
        # Python Core SDK Exports
        lines.append("## Python Core SDK Exports")
        lines.append("")
        lines.append(f"**Path:** `{tracker['pythonCoreSDK']['path']}`")
        lines.append("")
        
        # Group exports by module
        if tracker['pythonCoreSDK'].get('modules'):
            for module, exports in sorted(tracker['pythonCoreSDK']['modules'].items()):
                lines.append("<details>")
                lines.append(f"<summary><strong>{module}</strong> ({len(exports)} exports)</summary>")
                lines.append("")
                lines.append("```python")
                lines.append(f"from praisonaiagents import {', '.join(exports[:10])}{'...' if len(exports) > 10 else ''}")
                lines.append("```")
                lines.append("")
                lines.append("</details>")
                lines.append("")
        
        # TypeScript SDK Exports
        lines.append("## TypeScript SDK Exports")
        lines.append("")
        lines.append(f"**Path:** `{tracker['typescriptSDK']['path']}`")
        lines.append("")
        
        if tracker['typescriptSDK'].get('modules'):
            for module, exports in sorted(tracker['typescriptSDK']['modules'].items()):
                lines.append("<details>")
                lines.append(f"<summary><strong>{module}</strong> ({len(exports)} exports)</summary>")
                lines.append("")
                lines.append("```typescript")
                lines.append(f"import {{ {', '.join(exports[:10])}{'...' if len(exports) > 10 else ''} }} from 'praisonai';")
                lines.append("```")
                lines.append("")
                lines.append("</details>")
                lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*Generated by `praisonai._dev.parity.generator`*")
        lines.append("")
        
        return '\n'.join(lines)
    
    def write_typescript_markdown(self, check: bool = False) -> int:
        """
        Write TypeScript markdown parity report.
        
        Args:
            check: If True, only check if file is up to date
            
        Returns:
            0 for success, 1 for check failure
        """
        content = self.generate_markdown()
        
        if check:
            if self.ts_md_output.exists():
                with open(self.ts_md_output, 'r', encoding='utf-8') as f:
                    existing = f.read()
                # Compare ignoring date line
                existing_lines = [line for line in existing.split('\n') if not line.startswith('> **Version:**')]
                content_lines = [line for line in content.split('\n') if not line.startswith('> **Version:**')]
                if existing_lines == content_lines:
                    print(f"✓ {self.ts_md_output} is up to date")
                    return 0
                else:
                    print(f"✗ {self.ts_md_output} is out of date")
                    return 1
            else:
                print(f"✗ {self.ts_md_output} does not exist")
                return 1
        
        with open(self.ts_md_output, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ Generated {self.ts_md_output}")
        return 0
    
    def write_rust_markdown(self, check: bool = False) -> int:
        """
        Write Rust markdown parity report.
        
        Args:
            check: If True, only check if file is up to date
            
        Returns:
            0 for success, 1 for check failure
        """
        # Generate Rust-specific markdown
        python_features = self.python_extractor.extract()
        rust_features = self.rust_extractor.extract()
        
        python_exports = {e.name for e in python_features.exports}
        rust_exports = rust_features.get_export_names()
        rust_count = len(rust_exports)
        python_count = len(python_exports)
        gap_count = len(python_exports - rust_exports)
        parity_pct = round((rust_count / python_count * 100) if python_count > 0 else 0, 1)
        
        lines = []
        lines.append("# Rust Feature Parity Tracker")
        lines.append("")
        lines.append(f"> **Python Features:** {python_count} | **Rust Features:** {rust_count} | **Parity:** {parity_pct}%")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Python Core Features | {python_count} |")
        lines.append(f"| Rust Features | {rust_count} |")
        lines.append(f"| **Gap Count** | **{gap_count}** |")
        lines.append(f"| **Parity** | **{parity_pct}%** |")
        lines.append("")
        lines.append("## Implemented Features")
        lines.append("")
        for name in sorted(rust_exports):
            lines.append(f"- ✅ `{name}`")
        lines.append("")
        lines.append("## Missing Features (Top Priority)")
        lines.append("")
        missing = sorted(python_exports - rust_exports)[:50]
        for name in missing:
            lines.append(f"- ❌ `{name}`")
        if len(python_exports - rust_exports) > 50:
            lines.append(f"- ... and {len(python_exports - rust_exports) - 50} more")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Generated by `praisonai._dev.parity.generator`*")
        lines.append("")
        
        content = '\n'.join(lines)
        
        if check:
            if self.rust_md_output.exists():
                with open(self.rust_md_output, 'r', encoding='utf-8') as f:
                    existing = f.read()
                existing_lines = [line for line in existing.split('\n') if not line.startswith('>')]
                content_lines = [line for line in content.split('\n') if not line.startswith('>')]
                if existing_lines == content_lines:
                    print(f"✓ {self.rust_md_output} is up to date")
                    return 0
                else:
                    print(f"✗ {self.rust_md_output} is out of date")
                    return 1
            else:
                print(f"✗ {self.rust_md_output} does not exist")
                return 1
        
        with open(self.rust_md_output, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ Generated {self.rust_md_output}")
        return 0


def generate_parity_tracker(
    repo_root: Optional[Path] = None,
    target: str = 'all',
    check: bool = False,
    stdout: bool = False,
    output_format: str = 'json'
) -> int:
    """
    Generate feature parity tracker files.
    
    Args:
        repo_root: Repository root path (auto-detected if None)
        target: 'typescript', 'rust', or 'all'
        check: If True, check if files are up to date (exit 1 if not)
        stdout: If True, print to stdout instead of writing files
        output_format: Output format for --stdout ('json' or 'md')
    
    Returns:
        Exit code (0 for success, 1 for check failure)
    """
    generator = ParityTrackerGenerator(repo_root)
    
    if stdout:
        if output_format == 'md':
            print(generator.generate_markdown())
        else:
            tracker = generator.generate()
            print(json.dumps(tracker, indent=2, ensure_ascii=False))
        return 0
    
    exit_code = 0
    
    if target in ('typescript', 'ts', 'all'):
        result = generator.write_typescript(check=check)
        if result != 0:
            exit_code = result
        result = generator.write_typescript_markdown(check=check)
        if result != 0:
            exit_code = result
    
    if target in ('rust', 'rs', 'all'):
        result = generator.write_rust(check=check)
        if result != 0:
            exit_code = result
        result = generator.write_rust_markdown(check=check)
        if result != 0:
            exit_code = result
    
    return exit_code


def main():
    """CLI entry point for the generator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate feature parity tracker for PraisonAI SDKs"
    )
    parser.add_argument(
        '--target', '-t',
        choices=['typescript', 'ts', 'rust', 'rs', 'md', 'markdown', 'all'],
        default='all',
        help='Target SDK to generate tracker for (default: all)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['json', 'md'],
        default='json',
        help='Output format for --stdout (default: json)'
    )
    parser.add_argument(
        '--check', action='store_true',
        help='Check if tracker is up to date (exit 1 if not)'
    )
    parser.add_argument(
        '--stdout', action='store_true',
        help='Print to stdout instead of writing files'
    )
    parser.add_argument(
        '--repo-root', type=Path,
        help='Repository root path (auto-detected if not specified)'
    )
    
    args = parser.parse_args()
    
    import sys
    exit_code = generate_parity_tracker(
        repo_root=args.repo_root,
        target=args.target,
        check=args.check,
        stdout=args.stdout,
        output_format=args.format
    )
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
