"""
Feature Parity Tracker Generator for PraisonAI SDKs.

Generates JSON files tracking feature parity between Python SDK (source of truth)
and other implementations (TypeScript, Rust).
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ._paths import find_repo_root
from .python_extractor import PythonFeatureExtractor, PythonFeatures
from .rust_extractor import (
    RustFeatureExtractor,
    RustFeatures,
    RUST_LANGUAGE_EXCLUDED,
    RUST_ALIAS_MAPPING,
)
from .typescript_extractor import TypeScriptFeatureExtractor, TypeScriptFeatures


# Python name -> TypeScript name for exports whose TS spelling cannot be derived
# mechanically (snake_case -> camelCase is tried automatically; list only the
# exceptions here).
TS_ALIAS_MAPPING: Dict[str, str] = {}

# Source-path prefix of the TypeScript "parity shim" module. Names whose only
# TypeScript provider lives here are reported as STUB rather than DONE, because
# that module exists to satisfy this tracker's name matching, not to implement
# behaviour.
TS_STUB_SOURCE_PREFIX = './parity'

# Status ordering used when rendering markdown (missing first, stubs next).
_STATUS_ORDER = {'TODO': 0, 'STUB': 1, 'DONE': 2}


def _escape_md(text: str) -> str:
    """Escape markdown special characters."""
    return text.replace('|', '\\|').replace('_', '\\_')


def _snake_to_camel(name: str) -> Optional[str]:
    """
    Convert a snake_case identifier to camelCase.

    Returns None when no meaningful conversion exists: names without an
    underscore, dunder/private names (``__version__``, ``_x``, ``if_``) and
    SCREAMING_CASE constants are left alone.
    """
    if '_' not in name or name.startswith('_') or name.endswith('_'):
        return None
    if name.isupper():
        return None
    parts = [p for p in name.split('_') if p]
    if len(parts) < 2:
        return None
    return parts[0] + ''.join(p[:1].upper() + p[1:] for p in parts[1:])


def _tracker_equal_ignoring_date(a: dict, b: dict) -> bool:
    """Compare two tracker documents ignoring their ``lastUpdated`` field."""
    a_copy = dict(a)
    b_copy = dict(b)
    a_copy.pop('lastUpdated', None)
    b_copy.pop('lastUpdated', None)
    return a_copy == b_copy


def _is_date_line(line: str) -> bool:
    """True for markdown lines that carry only the generation date."""
    return line.startswith('> **Version:**') or '**Last Updated:**' in line


@dataclass
class FeatureGap:
    """Represents a feature gap between implementations."""
    feature: str
    python: bool
    typescript: bool
    rust: bool = False
    priority: str = 'P3'  # P0=critical, P1=high, P2=medium, P3=low
    effort: str = 'medium'  # low, medium, high
    status: str = 'TODO'  # TODO, IN_PROGRESS, DONE, STUB
    category: str = 'other'


@dataclass
class ParitySummary:
    """Summary statistics for parity tracking."""
    python_core_features: int = 0
    python_wrapper_features: int = 0
    typescript_features: int = 0
    rust_features: int = 0
    gap_count: int = 0
    stub_count: int = 0
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

    # Priority to gap-matrix key mapping
    PRIORITY_TO_KEY = {
        'P0': 'P0_CoreParity',
        'P1': 'P1_Persistence',
        'P2': 'P2_CLI',
        'P3': 'P3_Advanced',
    }

    # Explicit Python -> TypeScript name exceptions (see module docstring).
    TS_ALIAS_MAPPING = TS_ALIAS_MAPPING

    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize generator with repository root path."""
        if repo_root is None:
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()

        self.python_extractor = PythonFeatureExtractor(self.repo_root)
        self.ts_extractor = TypeScriptFeatureExtractor(self.repo_root)
        self.rust_extractor = RustFeatureExtractor(self.repo_root)

        # Output paths
        self.ts_output = self.repo_root / "src" / "praisonai-ts" / "FEATURE_PARITY_TRACKER.json"
        self.ts_md_output = self.repo_root / "src" / "praisonai-ts" / "PARITY.md"
        self.rust_output = self.repo_root / "src" / "praisonai-rust" / "FEATURE_PARITY_TRACKER.json"
        self.rust_md_output = self.repo_root / "src" / "praisonai-rust" / "PARITY.md"

    def _find_repo_root(self) -> Path:
        """Find the monorepo root (see ``_paths.find_repo_root``)."""
        return find_repo_root()

    def _rel(self, path: Path) -> str:
        """Render a path relative to the repo root, posix style."""
        try:
            return path.resolve().relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _refuse_empty(self, features, language: str, source: str) -> None:
        """An extractor that found nothing has FAILED; it has not found parity.

        Both extractors swallow their errors and return an empty result, and
        every downstream number is a set difference -- so a missing or
        unparseable source file produces a plausible tracker rather than an
        error. Measured against a scratch tree with an unparseable
        `__init__.py`: `{'pythonCoreFeatures': 0, 'gapCount': 0}`, exit 0, and
        CI would have committed it as "no gaps".

        Zero exports is never a real answer for either SDK, so it is refused
        here rather than published.
        """
        count = len(getattr(features, "exports", ()) or ())
        if count == 0:
            raise RuntimeError(
                f"{language} extractor found 0 exports in {source}. That is a "
                f"read or parse failure, not parity -- refusing to write a "
                f"tracker that would report zero gaps."
            )

    # ------------------------------------------------------------------
    # TypeScript tracker
    # ------------------------------------------------------------------

    def generate(self) -> dict:
        """Generate the parity tracker data structure."""
        # Extract features from both SDKs
        python_features = self.python_extractor.extract()
        ts_features = self.ts_extractor.extract()
        self._refuse_empty(python_features, "Python", "praisonaiagents/__init__.py")
        self._refuse_empty(ts_features, "TypeScript", "praisonai-ts/src/index.ts")

        # Get version from existing tracker or default
        version = self._get_current_version()

        # One row per Python export; summary and gap matrix both derive from it
        rows = self._build_ts_rows(python_features, ts_features)

        # Build the tracker structure
        tracker = {
            'version': version,
            'lastUpdated': date.today().isoformat(),
            'generatedBy': 'praisonai._dev.parity.generator',
            'sourceOfTruth': 'Python SDK (praisonaiagents)',
            'summary': self._build_summary(python_features, ts_features, rows),
            'pythonCoreSDK': self._build_python_section(python_features),
            'pythonWrapper': self._build_wrapper_section(python_features),
            'typescriptSDK': self._build_typescript_section(ts_features),
            'gapMatrix': self._group_rows_by_priority(rows),
        }

        self._preserve_last_updated(tracker, self.ts_output)
        return tracker

    def _preserve_last_updated(self, tracker: dict, existing_path: Path) -> None:
        """
        Keep the previously committed ``lastUpdated`` when nothing else changed.

        Without this every run rewrites the date, producing commits whose only
        diff is the timestamp.
        """
        if not existing_path.exists():
            return
        try:
            with open(existing_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            return
        if not isinstance(existing, dict) or 'lastUpdated' not in existing:
            return
        if _tracker_equal_ignoring_date(existing, tracker):
            tracker['lastUpdated'] = existing['lastUpdated']

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

    def _match_ts_name(self, name: str, ts_by_name: Dict[str, list]) -> Optional[str]:
        """
        Find the TypeScript export name that corresponds to a Python name.

        Order: exact match, explicit ``TS_ALIAS_MAPPING`` entry, then the
        mechanical snake_case -> camelCase conversion. Returns None if the
        name is absent from the TypeScript surface.
        """
        if name in ts_by_name:
            return name
        alias = self.TS_ALIAS_MAPPING.get(name)
        if alias and alias in ts_by_name:
            return alias
        camel = _snake_to_camel(name)
        if camel and camel in ts_by_name:
            return camel
        return None

    def _build_ts_rows(self, python: PythonFeatures, ts: TypeScriptFeatures) -> List[dict]:
        """
        Build one gap-matrix row per Python export.

        This is the single place that decides whether a Python name counts as
        present in TypeScript; the summary and the gap matrix both consume the
        result so they can never disagree.
        """
        ts_by_name = ts.get_exports_by_name()
        rows: List[dict] = []

        for export in sorted(python.exports, key=lambda e: e.name):
            name = export.name
            priority = self.PRIORITY_MAPPING.get(export.category, 'P3')
            effort = self.EFFORT_MAPPING.get(export.kind, 'medium')
            ts_name = self._match_ts_name(name, ts_by_name)

            row = {
                'feature': name,
                'python': True,
                'typescript': ts_name is not None,
                'priority': priority,
                'effort': effort,
                'status': 'TODO',
                'category': export.category,
            }

            if ts_name is not None:
                providers = ts_by_name[ts_name]
                only_stub = all(
                    p.source_file.startswith(TS_STUB_SOURCE_PREFIX) for p in providers
                )
                row['status'] = 'STUB' if only_stub else 'DONE'
                if ts_name != name:
                    row['tsName'] = ts_name
                if only_stub:
                    row['tsSource'] = TS_STUB_SOURCE_PREFIX

            rows.append(row)

        return rows

    def _group_rows_by_priority(self, rows: List[dict]) -> Dict[str, List[dict]]:
        """Group gap-matrix rows under their priority bucket."""
        grouped: Dict[str, List[dict]] = {key: [] for key in self.PRIORITY_TO_KEY.values()}
        for row in rows:
            key = self.PRIORITY_TO_KEY.get(row['priority'], 'P3_Advanced')
            grouped[key].append(row)
        return grouped

    def _build_summary(
        self, python: PythonFeatures, ts: TypeScriptFeatures, rows: Optional[List[dict]] = None
    ) -> dict:
        """Build summary statistics from the gap-matrix rows."""
        if rows is None:
            rows = self._build_ts_rows(python, ts)

        priority_counts = {'P0': 0, 'P1': 0, 'P2': 0, 'P3': 0}
        gap_count = 0
        stub_count = 0
        for row in rows:
            if row['status'] == 'TODO':
                gap_count += 1
                priority_counts[row['priority']] += 1
            elif row['status'] == 'STUB':
                stub_count += 1

        return {
            'pythonCoreFeatures': len(python.exports),
            'pythonWrapperFeatures': len(python.cli_features),
            'typescriptFeatures': len(ts.exports),
            'gapCount': gap_count,
            'stubCount': stub_count,
            'priorityP0': priority_counts['P0'],
            'priorityP1': priority_counts['P1'],
            'priorityP2': priority_counts['P2'],
            'priorityP3': priority_counts['P3'],
        }

    def _build_python_section(self, features: PythonFeatures) -> dict:
        """Build Python SDK section."""
        return {
            'path': self._rel(self.repo_root / "src" / "praisonai-agents" / "praisonaiagents"),
            'exports': sorted([e.name for e in features.exports]),
            'modules': {
                name: sorted(mod.exports)
                for name, mod in sorted(features.modules.items())
            },
        }

    def _build_wrapper_section(self, features: PythonFeatures) -> dict:
        """Build Python wrapper section."""
        return {
            'path': self._rel(self.repo_root / "src" / "praisonai" / "praisonai"),
            'cliFeatures': sorted(features.cli_features),
        }

    def _build_typescript_section(self, features: TypeScriptFeatures) -> dict:
        """Build TypeScript SDK section."""
        return {
            'path': self._rel(self.repo_root / "src" / "praisonai-ts" / "src"),
            'exports': sorted({e.name for e in features.exports if not e.is_type}),
            'modules': {
                name: sorted(mod.exports)
                for name, mod in sorted(features.modules.items())
            },
        }

    def _build_gap_matrix(self, python: PythonFeatures, ts: TypeScriptFeatures) -> dict:
        """Build the gap matrix showing feature-by-feature comparison."""
        return self._group_rows_by_priority(self._build_ts_rows(python, ts))

    def _check_json(self, path: Path, content: str) -> int:
        """Compare a freshly generated JSON document against the file on disk."""
        if not path.exists():
            print(f"✗ {path} does not exist")
            return 1
        try:
            with open(path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"✗ {path} is not valid JSON")
            return 1
        if _tracker_equal_ignoring_date(existing_data, json.loads(content)):
            print(f"✓ {path} is up to date")
            return 0
        print(f"✗ {path} is out of date")
        return 1

    def _check_markdown(self, path: Path, content: str) -> int:
        """Compare generated markdown against disk, ignoring the date line."""
        if not path.exists():
            print(f"✗ {path} does not exist")
            return 1
        with open(path, 'r', encoding='utf-8') as f:
            existing = f.read()
        existing_lines = [l for l in existing.split('\n') if not _is_date_line(l)]
        content_lines = [l for l in content.split('\n') if not _is_date_line(l)]
        if existing_lines == content_lines:
            print(f"✓ {path} is up to date")
            return 0
        print(f"✗ {path} is out of date")
        return 1

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
            return self._check_json(self.ts_output, content)

        # Ensure directory exists
        self.ts_output.parent.mkdir(parents=True, exist_ok=True)

        with open(self.ts_output, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✓ Generated {self.ts_output}")
        return 0

    # ------------------------------------------------------------------
    # Rust tracker
    # ------------------------------------------------------------------

    def generate_rust(self) -> dict:
        """Generate the Rust parity tracker data structure."""
        python_features = self.python_extractor.extract()
        rust_features = self.rust_extractor.extract()

        python_exports = {e.name for e in python_features.exports}
        rust_exports = rust_features.get_export_names()
        python_count = len(python_exports)
        rust_count = len(rust_exports)

        # Status and percentage derive from the gap matrix so the two can
        # never contradict each other (raw export counts can exceed 100%).
        gap_matrix = self._build_rust_gap_matrix(python_features, rust_features)
        rows = [row for rows in gap_matrix.values() for row in rows]
        gap_count = sum(1 for row in rows if row['status'] == 'TODO')
        matched = len(rows) - gap_count
        parity_pct = round(min(100.0, matched / python_count * 100), 1) if python_count else 0.0

        if rust_count == 0 or matched == 0:
            status = 'NOT_STARTED'
        elif gap_count == 0:
            status = 'PARITY_ACHIEVED'
        elif parity_pct < 25:
            status = 'EARLY_DEVELOPMENT'
        elif parity_pct < 75:
            status = 'IN_PROGRESS'
        else:
            status = 'NEAR_PARITY'

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
                # IMPLEMENTED over expected, not total-exports over expected. Dividing
                # the whole Rust surface by Python's produced 162.3% alongside a
                # gapCount of 129 -- a number that cannot fall below 100% however
                # much is missing, and that contradicted the PARITY.md written by
                # the same run. Volume is not parity; parity_pct is matched/expected.
                'parityPercentage': parity_pct,
            },
            'pythonCoreSDK': {
                'exports': sorted([e.name for e in python_features.exports]),
            },
            'rustSDK': {
                'path': self._rel(self.repo_root / "src" / "praisonai-rust"),
                'exports': sorted(list(rust_exports)),
                'modules': {
                    name: sorted(mod.exports)
                    for name, mod in sorted(rust_features.modules.items())
                },
                'cargoFeatures': rust_features.cargo_features,
            },
            'gapMatrix': gap_matrix,
        }

        self._preserve_last_updated(tracker, self.rust_output)
        return tracker

    def write_rust(self, check: bool = False) -> int:
        """
        Write Rust parity tracker.

        Args:
            check: If True, only check if file is up to date

        Returns:
            0 for success, 1 for check failure
        """
        tracker = self.generate_rust()
        content = json.dumps(tracker, indent=2, ensure_ascii=False) + '\n'

        if check:
            return self._check_json(self.rust_output, content)

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

        gaps_by_priority: Dict[str, List[dict]] = {
            key: [] for key in self.PRIORITY_TO_KEY.values()
        }

        for name, export in sorted(python_exports.items()):
            rust_name: Optional[str] = None
            if name in rust_export_names:
                rust_name = name
            else:
                alias = RUST_ALIAS_MAPPING.get(name)
                if alias and alias in rust_export_names:
                    rust_name = alias
            in_rust = rust_name is not None
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
            if rust_name is not None and rust_name != name:
                gap_entry['rustName'] = rust_name

            key = self.PRIORITY_TO_KEY.get(priority, 'P3_Advanced')
            gaps_by_priority[key].append(gap_entry)

        return gaps_by_priority

    # ------------------------------------------------------------------
    # Markdown reports
    # ------------------------------------------------------------------

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
        lines.append("> [!IMPORTANT]")
        lines.append("> **What this measures:** whether a matching *exported symbol name* exists in")
        lines.append("> the TypeScript SDK's public surface (parsed from `src/index.ts`, following")
        lines.append("> `export * from` re-exports). It does **not** verify that the capability is")
        lines.append("> reachable, wired up, or behaves like its Python counterpart. A `✅ exported`")
        lines.append("> cell means the name is exported — not that it works. A `⚠️ stub exported`")
        lines.append("> cell means the *only* provider of the name is the `src/parity` shim module,")
        lines.append("> which exists to satisfy this tracker's name matching rather than to implement")
        lines.append("> the feature. Snake_case Python names are also matched against their camelCase")
        lines.append("> spelling (shown as `→ tsName`).")
        lines.append("> Counts include barrel re-exports, so `TypeScript Features` reflects module")
        lines.append("> structure, not distinct capabilities, and is not directly comparable to the")
        lines.append("> Python count. For a capability with a testable contract, rely on its conformance")
        lines.append("> suite rather than this table.")
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
        lines.append(f"| Stub Exported (parity shim only) | {summary['stubCount']} |")
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

            done_count = sum(1 for g in gaps if g['status'] == 'DONE')
            stub_count = sum(1 for g in gaps if g['status'] == 'STUB')
            todo_count = len(gaps) - done_count - stub_count

            lines.append(
                f"### {priority_key} ({done_count} exported, {stub_count} stub, {todo_count} missing)"
            )
            lines.append("")
            lines.append("| Feature | Python | TypeScript | Effort | Status |")
            lines.append("|---------|--------|------------|--------|--------|")

            for gap in sorted(gaps, key=lambda x: (_STATUS_ORDER.get(x['status'], 9), x['feature'])):
                py = "✅" if gap['python'] else "❌"
                ts = "✅" if gap['typescript'] else "❌"
                if gap['status'] == 'DONE':
                    status = "✅ exported"
                elif gap['status'] == 'STUB':
                    status = "⚠️ stub exported"
                else:
                    status = "⏳ missing"
                feature = f"`{_escape_md(gap['feature'])}`"
                if gap.get('tsName'):
                    feature += f" → `{_escape_md(gap['tsName'])}`"
                lines.append(f"| {feature} | {py} | {ts} | {gap['effort']} | {status} |")

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
            return self._check_markdown(self.ts_md_output, content)

        self.ts_md_output.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ts_md_output, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✓ Generated {self.ts_md_output}")
        return 0

    def generate_rust_markdown(self) -> str:
        """Generate the Rust markdown parity report."""
        python_features = self.python_extractor.extract()
        rust_features = self.rust_extractor.extract()

        python_exports = {e.name for e in python_features.exports}
        rust_exports = rust_features.get_export_names()

        # Check for Rust aliases - consider Python features implemented if their alias exists
        effective_rust_exports = set(rust_exports)
        for py_name, rust_alias in RUST_ALIAS_MAPPING.items():
            if rust_alias in rust_exports:
                effective_rust_exports.add(py_name)

        # Separate missing features into language-excluded and actual gaps
        missing_all = python_exports - effective_rust_exports
        language_excluded = missing_all & RUST_LANGUAGE_EXCLUDED
        actual_gaps = missing_all - RUST_LANGUAGE_EXCLUDED

        rust_count = len(rust_exports)
        python_count = len(python_exports)
        # Gap count excludes language limitations
        gap_count = len(actual_gaps)
        # Parity counts language-excluded as implemented (they have aliases)
        implemented_count = python_count - gap_count
        parity_pct = round(min(100.0, implemented_count / python_count * 100), 1) if python_count else 0.0

        lines = []
        lines.append("# Rust Feature Parity Tracker")
        lines.append("")
        lines.append(f"> **Python Features:** {python_count} | **Rust Features:** {rust_count} | **Parity:** {parity_pct}%")
        lines.append("")
        lines.append("> [!IMPORTANT]")
        lines.append("> **What this measures:** whether a matching *exported symbol name* exists in the")
        lines.append("> Rust crate's public surface. It does **not** verify that the capability is")
        lines.append("> reachable or behaves like its Python counterpart — an exported item whose body")
        lines.append("> returns `Err(\"not yet implemented\")` still counts here. Treat `✅` as \"a symbol")
        lines.append("> of this name is exported\", not \"this works\". For a capability with a testable")
        lines.append("> contract, rely on its conformance suite rather than this table.")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Python Core Features | {python_count} |")
        lines.append(f"| Rust Features | {rust_count} |")
        lines.append(f"| **Actual Gap Count** | **{gap_count}** |")
        lines.append(f"| Language Limitations (N/A) | {len(language_excluded)} |")
        lines.append(f"| **Parity** | **{parity_pct}%** |")
        lines.append("")
        lines.append("## Implemented Features")
        lines.append("")
        for name in sorted(rust_exports):
            lines.append(f"- ✅ `{name}`")
        lines.append("")

        # Language limitations section
        if language_excluded:
            lines.append("## N/A (Rust Language Limitations)")
            lines.append("")
            lines.append("These Python features cannot be directly implemented in Rust due to reserved keywords or module naming conflicts. Equivalent functionality exists under different names.")
            lines.append("")
            for name in sorted(language_excluded):
                alias = RUST_ALIAS_MAPPING.get(name)
                if alias:
                    lines.append(f"- ⚠️ `{name}` → Use `{alias}` instead")
                else:
                    lines.append(f"- ⚠️ `{name}` (Rust reserved/module conflict)")
            lines.append("")

        # Actual missing features
        if actual_gaps:
            lines.append("## Missing Features")
            lines.append("")
            for name in sorted(actual_gaps):
                lines.append(f"- ❌ `{name}`")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("*Generated by `praisonai._dev.parity.generator`*")
        lines.append("")

        return '\n'.join(lines)

    def write_rust_markdown(self, check: bool = False) -> int:
        """
        Write Rust markdown parity report.

        Args:
            check: If True, only check if file is up to date

        Returns:
            0 for success, 1 for check failure
        """
        content = self.generate_rust_markdown()

        if check:
            return self._check_markdown(self.rust_md_output, content)

        self.rust_md_output.parent.mkdir(parents=True, exist_ok=True)
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

    if check and exit_code != 0:
        print(
            "Parity tracker files are out of date. Run "
            "`python3 src/praisonai/scripts/generate_parity_tracker.py` "
            "and commit the updated tracker files."
        )

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
