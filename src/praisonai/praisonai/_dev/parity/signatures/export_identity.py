"""
Export identity: is the TypeScript symbol a surface validates the *same symbol*
``src/praisonai-ts/src/index.ts`` exports under the Python name?

The signature layer answers "do the parameters match?" for a symbol named by
``surface.yaml`` -- a file, an interface, a class. Nothing checked that the
class it names is the one an importer of the package actually receives. It is
not: ``surface.yaml`` maps ``Task.__init__`` to ``agent/types.ts`` and reports
60 of 60 parameters matched, while the barrel exports a *different* ``Task``
from ``./workflows``. ``import { Task } from 'praisonai'`` hands the caller a
class with ``{ name, execute, condition }``; the checker validates one with
``{ description, expectedOutput, agent }``. A green gate over a symbol users
cannot obtain.

This module resolves, for one exported name, the file and declaration the
barrel really leads to -- following ``export { X as Y } from``, ``export *
from``, local export lists and re-exported imports -- and compares that
*identity* (declaring file + declared name) with the identity the surface
validates.

IMPORTANT -- this measures symbol *identity*, not behaviour and not shape. It
says the checker is pointed at the class users get, nothing more.

Reuse: the barrel walk borrows ``typescript_extractor``'s regexes, comment and
string-literal scanner, and module resolver rather than adding a third parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..typescript_extractor import (
    _LOCAL_EXPORT_LIST,
    _NAMED_REEXPORT,
    _STAR_REEXPORT,
    _TYPE_REEXPORT,
    _code_matches,
    _literal_spans,
    _strip_comments,
    TypeScriptFeatureExtractor,
)

BARREL_FILE = 'index.ts'
MAX_DEPTH = 8

# Statuses, worst last: the report orders findings by these.
STATUS_MATCH = 'match'
STATUS_MISMATCH = 'mismatch'
STATUS_UNRESOLVED = 'unresolved'
STATUS_NOT_EXPORTED = 'not-exported'

_DECL_KEYWORDS = r'class|async\s+function|function|const|let|var|interface|type|enum|namespace'

# `import { A, B as C } from './x'` -- a local export list may re-export a name
# it imported rather than one it declares.
_NAMED_IMPORT = re.compile(
    r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]"
)


def _declaration_re(name: str) -> 're.Pattern':
    """Matches a declaration of ``name`` in a module, exported or not."""
    return re.compile(
        r'^[ \t]*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?'
        rf'({_DECL_KEYWORDS})\s+({re.escape(name)})\b',
        re.MULTILINE,
    )


@dataclass(frozen=True)
class Origin:
    """Where a name is really declared."""
    file: str          # repo-relative, posix separators
    name: str          # the name as declared in that file
    kind: str          # class | interface | function | const | ...

    line: int = 0

    @property
    def identity(self) -> Tuple[str, str]:
        """What makes two symbols the same symbol: declaring file + declared name."""
        return (self.file, self.name)

    def describe(self) -> str:
        where = f'{self.file}:{self.line}' if self.line else self.file
        return f'{self.kind} {self.name} at {where}'


class BarrelResolver:
    """Resolves a name exported by the package barrel to its declaration."""

    def __init__(self, repo_root: Path, typescript_root: str):
        self.repo_root = Path(repo_root).resolve()
        self.typescript_root = typescript_root
        self.barrel = self.repo_root / typescript_root / BARREL_FILE
        # Only for its verified module resolution and "what does this module
        # provide" walk; the identity walk below is this module's own.
        self._ts = TypeScriptFeatureExtractor(repo_root=self.repo_root)
        self._source_cache: Dict[Path, Tuple[str, List[Tuple[int, int]]]] = {}
        self._names: Optional[Set[str]] = None

    # -- public ----------------------------------------------------------

    def exported_names(self) -> Set[str]:
        """Every name the barrel makes available to an importer."""
        if self._names is None:
            self._names = set(self._ts._module_provides(self.barrel))
        return self._names

    def origin(self, name: str) -> Optional[Origin]:
        """The declaration the barrel's ``name`` leads to, or None if untraceable."""
        return self._lookup(self.barrel, name, set(), 0)

    # -- internals -------------------------------------------------------

    def _read(self, path: Path) -> Tuple[str, List[Tuple[int, int]]]:
        cached = self._source_cache.get(path)
        if cached is not None:
            return cached
        try:
            content = _strip_comments(path.read_text(encoding='utf-8'))
        except (IOError, UnicodeDecodeError):
            content = ''
        entry = (content, _literal_spans(content))
        self._source_cache[path] = entry
        return entry

    def _rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _local_declaration(self, path: Path, name: str) -> Optional[Origin]:
        content, spans = self._read(path)
        matches = _code_matches(_declaration_re(name), content, spans)
        if not matches:
            return None
        match = matches[0]
        return Origin(
            file=self._rel(path),
            name=name,
            kind=re.sub(r'\s+', ' ', match.group(1)),
            line=content.count('\n', 0, match.start()) + 1,
        )

    def _lookup(self, path: Path, name: str, visited: Set[Path], depth: int) -> Optional[Origin]:
        """Resolve ``name`` as seen by an importer of ``path``."""
        if depth > MAX_DEPTH or path in visited:
            return None
        visited = visited | {path}
        content, spans = self._read(path)
        base = path.parent

        # 1. Declared right here (`export class Task { ... }`).
        local = self._local_declaration(path, name)
        if local is not None:
            return local

        # 2. `export { Task } from './x'` / `export { A as Task } from './x'`.
        for pattern in (_NAMED_REEXPORT, _TYPE_REEXPORT):
            for match in _code_matches(pattern, content, spans):
                for source_name, local_name, _ in self._ts._parse_export_bindings(match.group(1)):
                    if local_name != name:
                        continue
                    target = self._ts._resolve_module(base, match.group(2))
                    if target is None:
                        continue
                    found = self._lookup(target, source_name, visited, depth + 1)
                    if found is not None:
                        return found

        # 3. `export { Task }` with no `from`: a locally declared or imported name.
        for match in _code_matches(_LOCAL_EXPORT_LIST, content, spans):
            for source_name, local_name, _ in self._ts._parse_export_bindings(match.group(2)):
                if local_name != name:
                    continue
                declared = self._local_declaration(path, source_name)
                if declared is not None:
                    return declared
                found = self._follow_import(path, source_name, visited, depth)
                if found is not None:
                    return found

        # 4. `export * from './x'`: the first module that provides the name wins,
        #    which is also what TypeScript does (a name provided by two stars is
        #    an error, not an ambiguity we have to model).
        for match in _code_matches(_STAR_REEXPORT, content, spans):
            target = self._ts._resolve_module(base, match.group(1))
            if target is None:
                continue
            if name not in self._ts._module_provides(target):
                continue
            found = self._lookup(target, name, visited, depth + 1)
            if found is not None:
                return found
        return None

    def _follow_import(self, path: Path, name: str, visited: Set[Path], depth: int) -> Optional[Origin]:
        content, spans = self._read(path)
        for match in _code_matches(_NAMED_IMPORT, content, spans):
            for source_name, local_name, _ in self._ts._parse_export_bindings(match.group(1)):
                if local_name != name:
                    continue
                target = self._ts._resolve_module(path.parent, match.group(2))
                if target is None:
                    continue
                found = self._lookup(target, source_name, visited, depth + 1)
                if found is not None:
                    return found
        return None


# ------------------------------------------------------------------- findings

@dataclass
class ExportIdentityFinding:
    """One surface's answer to "is this the symbol users get?"."""
    surface: str
    status: str
    python_name: str
    validated: Origin                      # what surface.yaml points the checker at
    exported: Optional[Origin] = None      # what the barrel really leads to
    candidates: List[str] = field(default_factory=list)
    note: Optional[str] = None             # the surface's recorded "why not"

    @property
    def ok(self) -> bool:
        return self.status == STATUS_MATCH or self.note is not None

    def detail(self) -> str:
        if self.status == STATUS_MATCH:
            return (f'validates {self.validated.describe()}, which is what '
                    f'`import {{ {self.python_name} }}` yields')
        if self.status == STATUS_NOT_EXPORTED:
            tried = ' / '.join(self.candidates)
            return (f'the barrel {self.barrel_label()} exports no {tried}, so no importer can '
                    f'reach the {self.validated.describe()} this surface validates')
        if self.status == STATUS_UNRESOLVED:
            return (f'the barrel exports `{self.python_name}` but its declaration could not be '
                    f'traced, so the {self.validated.describe()} this surface validates is unproven')
        return (f'`import {{ {self.python_name} }}` yields {self.exported.describe()}, '
                f'but this surface validates {self.validated.describe()} -- {self._consequence()}')

    def _consequence(self) -> str:
        """Why this particular mismatch matters; the three kinds differ."""
        if self.exported.kind in ('interface', 'type'):
            return ('the importable name is a type, so the class this surface validates is not '
                    'constructible under it')
        if self.exported.file != self.validated.file:
            return 'a green gate over a symbol users cannot obtain'
        return ('same file, different declaration: the checker validates one symbol and callers '
                'receive another')

    def barrel_label(self) -> str:
        return f'{BARREL_FILE}'


def python_export_candidates(surface) -> List[str]:
    """
    The name(s) an importer would use for this surface's Python symbol.

    The surface key names it (``Task.__init__`` -> ``Task``, ``tool()`` ->
    ``tool``); an explicit ``python.class`` and any ``python.aliases`` are
    accepted too, because Python exports the team class under three names and
    TypeScript mirrors all three.
    """
    key = surface.key
    head = key.split('.', 1)[0].split('(', 1)[0].strip()
    candidates = [head]
    for extra in [surface.python.get('class')] + list(surface.python.get('aliases') or []):
        if extra and extra not in candidates:
            candidates.append(extra)
    return candidates


def validated_symbol(surface) -> Tuple[str, str]:
    """The ``(name, kind)`` of the TypeScript symbol this surface validates."""
    ts = surface.typescript
    if ts.get('ctorClass'):
        return ts['ctorClass'], 'class'
    if ts.get('cls'):
        return ts['cls'], 'class'
    return ts.get('name', ''), ts.get('kind', 'unknown')


def check_surface(surface, resolver: BarrelResolver, typescript_root: str) -> ExportIdentityFinding:
    """Compare the symbol a surface validates with the one the barrel exports."""
    name, kind = validated_symbol(surface)
    validated = Origin(
        file=f'{typescript_root}/{surface.typescript["file"]}',
        name=name,
        kind=kind,
    )
    candidates = python_export_candidates(surface)
    note = (surface.export_identity or {}).get('reason')

    exported_names = resolver.exported_names()
    reachable = [c for c in candidates if c in exported_names]
    if not reachable:
        return ExportIdentityFinding(
            surface=surface.key, status=STATUS_NOT_EXPORTED, python_name=candidates[0],
            validated=validated, candidates=[f'`{c}`' for c in candidates], note=note,
        )

    unresolved: List[str] = []
    first: Optional[Tuple[str, Origin]] = None
    for candidate in reachable:
        origin = resolver.origin(candidate)
        if origin is None:
            unresolved.append(candidate)
            continue
        if first is None:
            first = (candidate, origin)
        if origin.identity == validated.identity:
            return ExportIdentityFinding(
                surface=surface.key, status=STATUS_MATCH, python_name=candidate,
                validated=validated, exported=origin, candidates=candidates, note=note,
            )
    if first is None:
        return ExportIdentityFinding(
            surface=surface.key, status=STATUS_UNRESOLVED, python_name=unresolved[0],
            validated=validated, candidates=candidates, note=note,
        )
    return ExportIdentityFinding(
        surface=surface.key, status=STATUS_MISMATCH, python_name=first[0],
        validated=validated, exported=first[1], candidates=candidates, note=note,
    )


def check_export_identity(repo_root: Path, catalogue) -> List[ExportIdentityFinding]:
    """One finding per surface, in ``surface.yaml`` order.

    Raises ``FileNotFoundError`` if the barrel cannot be read -- the caller
    turns that into a tooling error, because an unreadable barrel means nothing
    was checked rather than that everything passed.
    """
    resolver = BarrelResolver(repo_root, catalogue.typescript_root)
    if not resolver.barrel.is_file():
        raise FileNotFoundError(
            f'the package barrel {catalogue.typescript_root}/{BARREL_FILE} does not exist under '
            f'{repo_root}; export identity cannot be checked'
        )
    if not resolver.exported_names():
        raise FileNotFoundError(
            f'{catalogue.typescript_root}/{BARREL_FILE} exports nothing -- it is empty or unreadable; '
            f'export identity cannot be checked'
        )
    return [check_surface(s, resolver, catalogue.typescript_root) for s in catalogue.surfaces]
