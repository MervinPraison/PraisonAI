"""
TypeScript Feature Extractor for PraisonAI SDK.

Extracts features from praisonai-ts package using regex-based analysis.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ._paths import find_repo_root


@dataclass
class TypeScriptExport:
    """Information about a TypeScript export."""
    name: str
    source_file: str
    is_type: bool = False
    kind: str = 'export'  # 'class', 'function', 'type', 'const'


@dataclass
class TypeScriptModule:
    """Information about a TypeScript module."""
    name: str
    exports: List[str] = field(default_factory=list)


@dataclass
class TypeScriptFeatures:
    """Extracted features from TypeScript SDK."""
    exports: List[TypeScriptExport] = field(default_factory=list)
    modules: Dict[str, TypeScriptModule] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'exports': [e.name for e in self.exports if not e.is_type],
            'modules': {
                name: mod.exports
                for name, mod in self.modules.items()
            },
        }

    def get_export_names(self) -> Set[str]:
        """Get set of all export names."""
        return {e.name for e in self.exports}

    def get_exports_by_name(self) -> Dict[str, List[TypeScriptExport]]:
        """Group exports by name so every provider of a name can be inspected."""
        grouped: Dict[str, List[TypeScriptExport]] = {}
        for export in self.exports:
            grouped.setdefault(export.name, []).append(export)
        return grouped


# --- Regexes -----------------------------------------------------------------

# Strings are captured in group 1 so comments inside string literals survive.
_STRING_OR_COMMENT = re.compile(
    r"""('(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`)"""
    r"""|//[^\n]*|/\*.*?\*/""",
    re.DOTALL,
)

# export { A, B as C } from './path'  (group 1 = names, group 2 = path)
_NAMED_REEXPORT = re.compile(
    r"export\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]"
)
# export type { A, B } from './path'
_TYPE_REEXPORT = re.compile(
    r"export\s+type\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]"
)
# export * from './path'
_STAR_REEXPORT = re.compile(
    r"export\s*\*\s*from\s*['\"]([^'\"]+)['\"]"
)
# export * as ns from './path'
_STAR_AS_REEXPORT = re.compile(
    r"export\s*\*\s*as\s+([A-Za-z_$][\w$]*)\s*from\s*['\"]([^'\"]+)['\"]"
)
# Local export list with no `from`: export { a, b as c }
_LOCAL_EXPORT_LIST = re.compile(
    r"export\s*(type\s*)?\{([^}]*)\}\s*(?!\s*from\b)"
)
# Declarations: export [declare] [abstract] class|function|const|... NAME
_DECLARATION = re.compile(
    r"^[ \t]*export\s+(?:declare\s+)?(?:abstract\s+)?"
    r"(class|async\s+function|function|const|let|var|interface|type|enum|namespace)"
    r"\s*\*?\s*([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)

_TYPE_KEYWORDS = {'interface', 'type'}
_MAX_STAR_DEPTH = 5


def _strip_comments(source: str) -> str:
    """Remove // and /* */ comments while leaving string literals intact."""
    return _STRING_OR_COMMENT.sub(lambda m: m.group(1) or '', source)


class TypeScriptFeatureExtractor:
    """
    Extracts features from praisonai-ts package using regex analysis.

    This extractor parses the index.ts file to find:
    - export { Name } from './path' statements
    - export type { Name } from './path' statements
    - export * from './path' statements — resolved by reading the target
      module (``./x.ts``, ``./x.tsx``, ``./x/index.ts`` or ``./x/index.tsx``)
      and collecting its exported declarations, local export lists and nested
      re-exports (recursively, with a visited set and a depth limit).

    It categorizes exports into modules based on their source paths.

    IMPORTANT — this measures symbol *names*, not behaviour. Presence of an
    exported name here does NOT mean the capability is reachable, wired up, or
    behaviourally equivalent to its Python counterpart. A name that is exported
    but never called (e.g. an approval manager that no code path invokes) still
    shows up. Downstream reports must label these as "exported", not "done".
    """

    # Module category mapping based on source paths
    MODULE_MAPPING = {
        'agent': ['./agent'],
        'auto': ['./auto'],
        'task': ['./task'],
        'tools': ['./tools'],
        'llm': ['./llm'],
        'memory': ['./memory'],
        'knowledge': ['./knowledge'],
        'db': ['./db'],
        'session': ['./session'],
        'workflows': ['./workflows'],
        'guardrails': ['./guardrails'],
        'eval': ['./eval'],
        'skills': ['./skills'],
        'telemetry': ['./telemetry'],
        'context': ['./context'],
        'observability': ['./observability'],
        'planning': ['./planning'],
        'cache': ['./cache'],
        'events': ['./events'],
        'hooks': ['./hooks'],
        'mcp': ['./mcp'],
        'integrations': ['./integrations'],
        'ai': ['./ai'],
        'os': ['./os'],
        'process': ['./process'],
        'cli': ['./cli'],
        'utils': ['./utils'],
        'parity': ['./parity'],  # Parity module for Python SDK feature parity
        'protocols': ['./protocols'],  # Protocol definitions
    }

    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize extractor with repository root path."""
        if repo_root is None:
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()
        self.ts_pkg = self.repo_root / "src" / "praisonai-ts"

    def _find_repo_root(self) -> Path:
        """Find the monorepo root (see ``_paths.find_repo_root``)."""
        return find_repo_root()

    def extract(self) -> TypeScriptFeatures:
        """Extract all features from TypeScript SDK."""
        features = TypeScriptFeatures()

        index_file = self.ts_pkg / "src" / "index.ts"
        if not index_file.exists():
            return features

        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return features

        content = _strip_comments(content)

        # Parse regular exports: export { Name1, Name2 } from './path'
        for match in _NAMED_REEXPORT.finditer(content):
            source = match.group(2)
            for name, is_type in self._parse_export_entries(match.group(1)):
                self._add_export(features, name, source, is_type)

        # Parse type exports: export type { Name1, Name2 } from './path'
        for match in _TYPE_REEXPORT.finditer(content):
            source = match.group(2)
            for name, _ in self._parse_export_entries(match.group(1)):
                self._add_export(features, name, source, True)

        # Parse namespace re-exports: export * as ns from './path'
        for match in _STAR_AS_REEXPORT.finditer(content):
            self._add_export(features, match.group(1), match.group(2), False)

        # Parse star re-exports: export * from './path' — resolve the target
        # module and record everything it exports under the star path.
        for match in _STAR_REEXPORT.finditer(content):
            source = match.group(1)
            resolved = self._resolve_module(index_file.parent, source)
            if resolved is None:
                continue
            for name, is_type in self._collect_star_exports(resolved, set(), 0):
                self._add_export(features, name, source, is_type)

        return features

    # --- export * resolution -------------------------------------------------

    def _resolve_module(self, base_dir: Path, spec: str) -> Optional[Path]:
        """Resolve a relative import specifier to a .ts/.tsx file."""
        if not spec.startswith('.'):
            return None  # bare package specifier — not part of this SDK
        target = (base_dir / spec)
        candidates = [
            target.with_suffix('.ts') if target.suffix != '.ts' else target,
            target.with_suffix('.tsx') if target.suffix != '.tsx' else target,
            target / 'index.ts',
            target / 'index.tsx',
        ]
        # Also accept an explicit './x.js' (TS ESM style) → './x.ts'
        if target.suffix == '.js':
            candidates.insert(0, target.with_suffix('.ts'))
            candidates.insert(1, target.with_suffix('.tsx'))
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _collect_star_exports(
        self, module_file: Path, visited: Set[Path], depth: int
    ) -> List[Tuple[str, bool]]:
        """
        Collect (name, is_type) pairs exported by ``module_file``.

        Follows nested ``export { .. } from`` / ``export * from`` statements up
        to ``_MAX_STAR_DEPTH`` levels, never visiting the same file twice.
        """
        if depth > _MAX_STAR_DEPTH or module_file in visited:
            return []
        visited.add(module_file)

        try:
            with open(module_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return []
        content = _strip_comments(content)

        found: List[Tuple[str, bool]] = []
        seen: Set[Tuple[str, bool]] = set()

        def add(name: str, is_type: bool) -> None:
            key = (name, is_type)
            if key not in seen:
                seen.add(key)
                found.append(key)

        # Declarations: export class Foo / export function bar / export type T
        for match in _DECLARATION.finditer(content):
            keyword = re.sub(r'\s+', ' ', match.group(1))
            add(match.group(2), keyword in _TYPE_KEYWORDS)

        # Named re-exports from other modules (names are known, no recursion)
        for match in _NAMED_REEXPORT.finditer(content):
            for name, is_type in self._parse_export_entries(match.group(1)):
                add(name, is_type)
        for match in _TYPE_REEXPORT.finditer(content):
            for name, _ in self._parse_export_entries(match.group(1)):
                add(name, True)
        for match in _STAR_AS_REEXPORT.finditer(content):
            add(match.group(1), False)

        # Local export lists: export { a, b as c }
        for match in _LOCAL_EXPORT_LIST.finditer(content):
            list_is_type = bool(match.group(1))
            for name, is_type in self._parse_export_entries(match.group(2)):
                add(name, is_type or list_is_type)

        # Nested star re-exports: recurse
        for match in _STAR_REEXPORT.finditer(content):
            nested = self._resolve_module(module_file.parent, match.group(1))
            if nested is None:
                continue
            for name, is_type in self._collect_star_exports(nested, visited, depth + 1):
                add(name, is_type)

        return found

    # --- helpers -------------------------------------------------------------

    def _add_export(
        self, features: TypeScriptFeatures, name: str, source: str, is_type: bool
    ) -> None:
        """Append an export record and register it under its module."""
        features.exports.append(TypeScriptExport(
            name=name,
            source_file=source,
            is_type=is_type,
            kind='type' if is_type else self._infer_kind(name),
        ))
        module_name = self._categorize(source)
        module = features.modules.setdefault(module_name, TypeScriptModule(name=module_name))
        if name not in module.exports:
            module.exports.append(name)

    def _parse_export_entries(self, names_str: str) -> List[Tuple[str, bool]]:
        """Parse an export list into (name, is_type) pairs."""
        entries: List[Tuple[str, bool]] = []
        for raw in self._parse_export_names(names_str):
            if raw.startswith('type '):
                entries.append((raw[5:].strip(), True))
            else:
                entries.append((raw, False))
        return entries

    def _parse_export_names(self, names_str: str) -> List[str]:
        """Parse export names from a comma-separated string."""
        names = []
        # Remove comments from the string first
        # Handle both // and /* */ style comments
        names_str = re.sub(r'//[^\n]*', '', names_str)
        names_str = re.sub(r'/\*.*?\*/', '', names_str, flags=re.DOTALL)

        for part in names_str.split(','):
            part = part.strip()
            if not part:
                continue
            # Skip if it looks like a comment remnant
            if part.startswith('//') or part.startswith('/*'):
                continue
            # Handle 'Name as Alias' syntax - take the ALIAS (right side)
            # This is correct because we want to match what Python exports
            if ' as ' in part:
                left, alias = part.split(' as ', 1)
                alias = alias.strip()
                # Preserve an inline `type` prefix from the left side
                if left.strip().startswith('type ') and not alias.startswith('type '):
                    alias = 'type ' + alias
                part = alias
            if part == 'default':
                continue
            names.append(part)
        return names

    def _categorize(self, source_path: str) -> str:
        """Categorize an export based on its source path."""
        for module_name, patterns in self.MODULE_MAPPING.items():
            for pattern in patterns:
                if source_path.startswith(pattern):
                    return module_name
        return 'other'

    def _infer_kind(self, name: str) -> str:
        """Infer the kind of export based on naming conventions."""
        if name[0].isupper():
            if name.endswith('Config') or name.endswith('Result') or name.endswith('Error'):
                return 'type'
            if name.endswith('Provider') or name.endswith('Adapter'):
                return 'class'
            return 'class'
        elif name.startswith('create') or name.startswith('get') or name.startswith('use'):
            return 'function'
        else:
            return 'function'
