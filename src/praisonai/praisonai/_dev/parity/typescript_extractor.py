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

# export default class Foo / export default function bar / export default x
_DEFAULT_EXPORT = re.compile(r"^[ \t]*export\s+default\b", re.MULTILINE)

_TYPE_KEYWORDS = {'interface', 'type'}
_MAX_STAR_DEPTH = 5


# A `/` starts a regular expression (rather than division) only after one of
# these. Anything else -- an identifier, a number, `)`, `]`, `.` -- means the
# preceding expression is complete, so the slash divides.
_REGEX_MAY_FOLLOW_CHARS = set('(,=:[!&|?{};+-*%^~<>')
_REGEX_MAY_FOLLOW_WORDS = {
    'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void',
    'throw', 'case', 'do', 'else', 'yield', 'await',
}


def _scan(source: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    r"""Split ``source`` into ``(comment_spans, literal_spans)``.

    A character-level scan rather than a regex, because the two cannot be told
    apart by alternation: the regular expression literal
    ``/([_*[\]()~`>#+\-=|{}.!\\])/g`` in ``src/bots/base.ts`` contains a
    backtick, and a regex-based splitter reads it as the start of a template
    literal that then swallows the next 6 lines -- including
    ``export function escapeMarkdownV2``.

    Literal spans cover string, template and regular-expression literals.
    """
    comments: List[Tuple[int, int]] = []
    literals: List[Tuple[int, int]] = []
    n = len(source)
    i = 0
    prev_char = ''   # last significant code character
    prev_word = ''   # last identifier in code, if it ended at prev_char

    while i < n:
        ch = source[i]
        pair = source[i:i + 2]

        if pair == '//':
            end = source.find('\n', i)
            end = n if end < 0 else end
            comments.append((i, end))
            i = end
            continue

        if pair == '/*':
            end = source.find('*/', i + 2)
            end = n if end < 0 else end + 2
            comments.append((i, end))
            i = end
            continue

        if ch in '"\'':
            j = i + 1
            while j < n and source[j] != ch and source[j] != '\n':
                j += 2 if source[j] == '\\' else 1
            end = min(j + 1, n) if j < n and source[j] == ch else j
            literals.append((i, end))
            prev_char, prev_word = ch, ''
            i = end
            continue

        if ch == '`':
            j = i + 1
            while j < n and source[j] != '`':
                j += 2 if source[j] == '\\' else 1
            end = min(j + 1, n)
            literals.append((i, end))
            prev_char, prev_word = '`', ''
            i = end
            continue

        if ch == '/' and (
            not prev_char
            or prev_char in _REGEX_MAY_FOLLOW_CHARS
            or prev_word in _REGEX_MAY_FOLLOW_WORDS
        ):
            j = i + 1
            in_class = False
            closed = False
            while j < n and source[j] != '\n':
                c = source[j]
                if c == '\\':
                    j += 2
                    continue
                if c == '[':
                    in_class = True
                elif c == ']':
                    in_class = False
                elif c == '/' and not in_class:
                    closed = True
                    break
                j += 1
            if closed:
                end = j + 1
                while end < n and source[end].isalpha():
                    end += 1   # flags
                literals.append((i, end))
                prev_char, prev_word = '/', ''
                i = end
                continue

        if ch.isalnum() or ch in '_$':
            j = i
            while j < n and (source[j].isalnum() or source[j] in '_$'):
                j += 1
            prev_word = source[i:j]
            prev_char = source[j - 1]
            i = j
            continue

        if not ch.isspace():
            prev_char, prev_word = ch, ''
        i += 1

    return comments, literals


def _strip_comments(source: str) -> str:
    """Blank out // and /* */ comments, leaving string literals intact.

    Comments become whitespace of the same length rather than being deleted, so
    character offsets survive and ``_literal_spans`` can be computed on the
    result.
    """
    comments, _ = _scan(source)
    if not comments:
        return source
    out = list(source)
    for start, end in comments:
        for k in range(start, end):
            if out[k] != '\n':
                out[k] = ' '
    return ''.join(out)


def _literal_spans(source: str) -> List[Tuple[int, int]]:
    """``(start, end)`` of every string/template/regex literal in ``source``."""
    return _scan(source)[1]


def _code_matches(pattern: 're.Pattern', source: str, spans: List[Tuple[int, int]]) -> list:
    """Matches of ``pattern`` that *begin* outside any string literal.

    The export regexes must read the module path out of a string literal, so
    literals cannot simply be deleted. Instead a statement only counts when its
    ``export`` keyword itself sits in code -- which is what keeps a doc snippet,
    a fixture or a codegen template from satisfying parity.
    """
    return [
        m for m in pattern.finditer(source)
        if not any(start <= m.start() < end for start, end in spans)
    ]


class TypeScriptFeatureExtractor:
    """
    Extracts features from praisonai-ts package using regex analysis.

    This extractor parses the index.ts file to find:
    - export { Name } from './path' statements
    - export type { Name } from './path' statements
    - export * from './path' statements

    Every re-export target is resolved to a real file (``./x.ts``, ``./x.tsx``,
    ``./x/index.ts`` or ``./x/index.tsx``); an unresolvable path contributes
    nothing. For ``export { .. } from`` the *source* name of each binding must
    also appear in what the target module provides -- its exported
    declarations, local export lists, nested re-exports and ``export default``
    (collected recursively, with a visited set and a depth limit). A statement
    naming a module that does not exist, or a symbol that module does not
    export, cannot compile, so it is not parity and is dropped.

    Export statements that begin inside a comment or a string literal are
    ignored: doc snippets, fixtures and codegen templates must not count.

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
        self._provides_cache: Dict[Path, Set[str]] = {}

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
        spans = _literal_spans(content)
        base_dir = index_file.parent

        # Parse regular exports: export { Name1, Name2 } from './path'
        for match in _code_matches(_NAMED_REEXPORT, content, spans):
            self._add_verified_reexport(
                features, base_dir, match.group(2), match.group(1), force_type=False)

        # Parse type exports: export type { Name1, Name2 } from './path'
        for match in _code_matches(_TYPE_REEXPORT, content, spans):
            self._add_verified_reexport(
                features, base_dir, match.group(2), match.group(1), force_type=True)

        # Parse namespace re-exports: export * as ns from './path'
        for match in _code_matches(_STAR_AS_REEXPORT, content, spans):
            if self._resolve_module(base_dir, match.group(2)) is None:
                continue
            self._add_export(features, match.group(1), match.group(2), False)

        # Parse star re-exports: export * from './path' — resolve the target
        # module and record everything it exports under the star path.
        for match in _code_matches(_STAR_REEXPORT, content, spans):
            source = match.group(1)
            resolved = self._resolve_module(base_dir, source)
            if resolved is None:
                continue
            for name, is_type in self._collect_star_exports(resolved, set(), 0):
                self._add_export(features, name, source, is_type)

        return features

    def _add_verified_reexport(
        self,
        features: TypeScriptFeatures,
        base_dir: Path,
        spec: str,
        names_str: str,
        force_type: bool,
    ) -> None:
        """Record ``export { .. } from spec`` only for bindings that really exist.

        An unresolvable ``spec`` contributes nothing, and a binding whose source
        name is absent from the target module is dropped: neither can compile,
        so neither is evidence of a TypeScript implementation.
        """
        resolved = self._resolve_module(base_dir, spec)
        if resolved is None:
            return
        provided = self._module_provides(resolved)
        for source_name, local_name, is_type in self._parse_export_bindings(names_str):
            if source_name not in provided:
                continue
            self._add_export(features, local_name, spec, force_type or is_type)

    def _module_provides(self, module_file: Path) -> Set[str]:
        """Names ``module_file`` makes available to an importer."""
        cached = self._provides_cache.get(module_file)
        if cached is not None:
            return cached

        names = {name for name, _ in self._collect_star_exports(module_file, set(), 0)}
        try:
            with open(module_file, 'r', encoding='utf-8') as f:
                content = _strip_comments(f.read())
        except (IOError, UnicodeDecodeError):
            content = ''
        if _code_matches(_DEFAULT_EXPORT, content, _literal_spans(content)):
            names.add('default')

        self._provides_cache[module_file] = names
        return names

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
        spans = _literal_spans(content)

        found: List[Tuple[str, bool]] = []
        seen: Set[Tuple[str, bool]] = set()

        def add(name: str, is_type: bool) -> None:
            key = (name, is_type)
            if key not in seen:
                seen.add(key)
                found.append(key)

        # Declarations: export class Foo / export function bar / export type T
        for match in _code_matches(_DECLARATION, content, spans):
            keyword = re.sub(r'\s+', ' ', match.group(1))
            add(match.group(2), keyword in _TYPE_KEYWORDS)

        # Named re-exports from other modules (names are known, no recursion)
        for match in _code_matches(_NAMED_REEXPORT, content, spans):
            for name, is_type in self._parse_export_entries(match.group(1)):
                add(name, is_type)
        for match in _code_matches(_TYPE_REEXPORT, content, spans):
            for name, _ in self._parse_export_entries(match.group(1)):
                add(name, True)
        for match in _code_matches(_STAR_AS_REEXPORT, content, spans):
            add(match.group(1), False)

        # Local export lists: export { a, b as c }
        for match in _code_matches(_LOCAL_EXPORT_LIST, content, spans):
            list_is_type = bool(match.group(1))
            for name, is_type in self._parse_export_entries(match.group(2)):
                add(name, is_type or list_is_type)

        # Nested star re-exports: recurse
        for match in _code_matches(_STAR_REEXPORT, content, spans):
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

    def _parse_export_bindings(self, names_str: str) -> List[Tuple[str, str, bool]]:
        """Parse an export list into ``(source_name, local_name, is_type)`` triples.

        ``source_name`` is what the target module must provide; ``local_name``
        is what an importer of *this* module sees, and is what parity matches
        against Python. For ``{ A }`` the two are equal; for ``{ A as B }`` they
        are ``A`` and ``B``; for ``{ default as B }`` they are ``default`` and
        ``B``.
        """
        bindings: List[Tuple[str, str, bool]] = []
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
            is_type = False
            if part.startswith('type '):
                is_type = True
                part = part[5:].strip()
            # Handle 'Name as Alias' syntax - the ALIAS (right side) is the name
            # importers see, so that is what parity matches against Python.
            if ' as ' in part:
                source, local = part.split(' as ', 1)
                source, local = source.strip(), local.strip()
            else:
                source = local = part
            if not source or not local or local == 'default':
                continue
            bindings.append((source, local, is_type))
        return bindings

    def _parse_export_entries(self, names_str: str) -> List[Tuple[str, bool]]:
        """Parse an export list into (name, is_type) pairs."""
        return [(local, is_type)
                for _, local, is_type in self._parse_export_bindings(names_str)]

    def _parse_export_names(self, names_str: str) -> List[str]:
        """Parse export names from a comma-separated string."""
        return [local for _, local, _ in self._parse_export_bindings(names_str)]

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
