"""
Public method inventory: does the TypeScript class offer the methods the Python
class offers?

The signature layer compares one function per surface, and for thirteen of the
seventeen curated surfaces that function is ``__init__``. Everything else the
class does is outside its field of view, which is how these survived a green
gate:

* ``Agent.execute`` -- Python ``execute(task, context=None)`` runs the task it
  is given; TypeScript ``execute(previousResult?)`` runs the agent's own
  instructions. ``agent.execute(taskText)`` silently does the wrong thing.
* ``Session`` -- Python has ``save_state``, ``restore_state``,
  ``get_state(key, default)``, ``add_memory``, ``search_memory``, ``chat`` and
  more; the TypeScript class has none of them.
* ``FunctionTool`` -- Python has ``run(**kwargs)``; TypeScript has neither that
  nor a callable form.

WHAT THIS CHECK COMPARES, precisely -- the same caveat ``PARITY.md`` prints
about names, for the same reason:

    NAME PRESENCE, NOT SIGNATURE AND NOT BEHAVIOUR. A method listed as present
    means only that ``x.foo(...)`` resolves on both sides. ``Agent.execute`` is
    "present" by this measure and still does something else. Signature parity is
    the layer above; behaviour parity is the layer above that.

Also stated rather than assumed:

* Python bases are followed through the package (``Agent`` gets its methods from
  twelve mixins). A base that cannot be located is named in the report, never
  passed over.
* TypeScript ``extends`` in another file is NOT followed, so every base is
  reported alongside its class. ``implements`` carries no members and so
  carries no caveat.
* ``save_state`` matches ``saveState``: exact or camelCase, nothing looser.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .schema import snake_to_camel

TS_MEMBERS_SCRIPT = Path(__file__).resolve().parent / 'ts_members.mjs'

# Decorators that make a `def` something other than a callable method.
_PROPERTY_DECORATORS = {'property', 'cached_property', 'setter', 'deleter', 'getter'}

# Bases that are not part of the SDK, so their methods are not parity surface.
_EXTERNAL_BASES = {
    'object', 'Exception', 'BaseException', 'ValueError', 'TypeError', 'RuntimeError',
    'ABC', 'BaseModel', 'Enum', 'IntEnum', 'StrEnum', 'Protocol', 'TypedDict',
    'NamedTuple', 'Generic', 'dict', 'list', 'str', 'int',
}


# ------------------------------------------------------------------ python side

@dataclass(frozen=True)
class PyMethod:
    name: str
    location: str        # repo-relative file:line
    owner: str           # the class that declares it (may be a mixin)
    is_async: bool = False


@dataclass
class PyClass:
    name: str
    location: str
    methods: List[PyMethod] = field(default_factory=list)
    unresolved_bases: List[str] = field(default_factory=list)


def _decorator_names(node: ast.AST) -> Set[str]:
    names = set()
    for dec in getattr(node, 'decorator_list', []):
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _base_names(node: ast.ClassDef) -> List[str]:
    names = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


class PythonClassIndex:
    """``class Name`` -> the files under ``python_root`` that declare it."""

    def __init__(self, repo_root: Path, python_root: str):
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / python_root
        self._index: Optional[Dict[str, List[Path]]] = None
        self._trees: Dict[Path, ast.Module] = {}

    def _build(self) -> Dict[str, List[Path]]:
        if self._index is not None:
            return self._index
        index: Dict[str, List[Path]] = {}
        for path in sorted(self.root.rglob('*.py')):
            try:
                tree = self._tree(path)
            except (SyntaxError, OSError):
                continue
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    index.setdefault(node.name, []).append(path)
        self._index = index
        return index

    def _tree(self, path: Path) -> ast.Module:
        cached = self._trees.get(path)
        if cached is None:
            cached = ast.parse(path.read_text(encoding='utf-8'))
            self._trees[path] = cached
        return cached

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()

    def files_declaring(self, name: str) -> List[Path]:
        return list(self._build().get(name, []))

    def find(self, name: str, prefer: Optional[Path] = None) -> Optional[Tuple[Path, ast.ClassDef]]:
        """Locate ``class name``. ``prefer`` wins when several files declare it."""
        files = self.files_declaring(name)
        if not files:
            return None
        chosen = prefer if prefer in files else files[0]
        for node in self._tree(chosen).body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return chosen, node
        return None

    def public_methods(self, name: str, prefer: Optional[Path] = None) -> Optional[PyClass]:
        """Public methods of ``name``, including those inherited from SDK bases."""
        found = self.find(name, prefer)
        if found is None:
            return None
        path, node = found
        result = PyClass(name=name, location=f'{self.rel(path)}:{node.lineno}')
        seen: Set[str] = set()
        self._collect(name, path, node, result, seen, set(), 0)
        result.methods.sort(key=lambda m: m.name)
        return result

    def _collect(self, cls_name: str, path: Path, node: ast.ClassDef,
                 out: PyClass, seen: Set[str], visited: Set[Tuple[str, str]], depth: int) -> None:
        key = (cls_name, str(path))
        if depth > 6 or key in visited:
            return
        visited.add(key)
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name.startswith('_'):
                continue
            if _decorator_names(child) & _PROPERTY_DECORATORS:
                continue
            if child.name in seen:
                continue
            seen.add(child.name)
            out.methods.append(PyMethod(
                name=child.name,
                location=f'{self.rel(path)}:{child.lineno}',
                owner=cls_name,
                is_async=isinstance(child, ast.AsyncFunctionDef),
            ))
        for base in _base_names(node):
            if base in _EXTERNAL_BASES:
                continue
            resolved = self.find(base, prefer=path)
            if resolved is None:
                if base not in out.unresolved_bases:
                    out.unresolved_bases.append(base)
                continue
            base_path, base_node = resolved
            self._collect(base, base_path, base_node, out, seen, visited, depth + 1)


# -------------------------------------------------------------- typescript side

class MemberToolingError(Exception):
    """node/typescript is missing or the member lister broke: not a parity result."""


@dataclass
class TsClass:
    name: str
    file: str
    location: str
    found: bool
    members: List[Dict[str, Any]] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)        # `extends` only
    implements: List[str] = field(default_factory=list)   # contributes no members
    absent: Optional[str] = None

    def member_names(self) -> Set[str]:
        return {m['name'] for m in self.members}


def run_ts_members(repo_root: Path, targets: List[Dict[str, str]],
                   ts_root: str = 'src/praisonai-ts/src') -> Dict[str, TsClass]:
    """Run ``ts_members.mjs``; keyed by ``"<file>::<cls>"``."""
    if not targets:
        return {}
    node = shutil.which('node')
    if node is None:
        raise MemberToolingError('node is not on PATH; the TypeScript member lister needs Node.js')
    proc = subprocess.run(
        [node, str(TS_MEMBERS_SCRIPT), '--repo-root', str(repo_root), '--ts-root', ts_root],
        input=json.dumps(targets), capture_output=True, text=True, env=os.environ.copy(),
    )
    if proc.returncode != 0:
        raise MemberToolingError(
            f'ts_members.mjs exited {proc.returncode}:\n{proc.stderr.strip() or proc.stdout.strip()}')
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MemberToolingError(f'ts_members.mjs printed invalid JSON: {exc}\n{proc.stdout[:500]}')
    out: Dict[str, TsClass] = {}
    for item in data:
        entry = TsClass(
            name=item['cls'], file=item['file'], location=item.get('location', ''),
            found=bool(item.get('found')), members=list(item.get('members') or []),
            bases=list(item.get('bases') or []),
            implements=list(item.get('implements') or []),
            absent=item.get('absent'),
        )
        out[f'{entry.file}::{entry.name}'] = entry
    return out


# ------------------------------------------------------------------ comparison

@dataclass
class MissingMethod:
    name: str
    expected_ts: str          # the name TypeScript would spell it
    location: str             # where Python declares it
    owner: str                # the Python class or mixin that declares it
    waiver: Optional[Dict[str, Any]] = None


@dataclass
class ClassInventory:
    """One Python class held against the TypeScript class a surface names."""
    key: str                       # the surface-facing class name
    surfaces: List[str] = field(default_factory=list)
    python: Optional[PyClass] = None
    typescript: Optional[TsClass] = None
    missing: List[MissingMethod] = field(default_factory=list)
    present: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    skipped: Optional[str] = None

    @property
    def unwaived(self) -> List[MissingMethod]:
        return [m for m in self.missing if m.waiver is None]

    @property
    def ok(self) -> bool:
        return self.skipped is not None or not self.unwaived


def _ts_candidates(name: str) -> Set[str]:
    """The TypeScript spellings accepted for a Python method name."""
    return {name, snake_to_camel(name)}


def compare_class(inventory: ClassInventory, waivers: Dict[str, Dict[str, Any]]) -> ClassInventory:
    """Fill in ``missing``/``present`` from the two sides already attached."""
    py, ts = inventory.python, inventory.typescript
    if py is None or ts is None:
        return inventory
    if py.unresolved_bases:
        inventory.notes.append(
            'Python base(s) not found in the package, so their methods are not compared: '
            + ', '.join(sorted(py.unresolved_bases))
        )
    if ts.found and ts.bases:
        inventory.notes.append(
            'TypeScript class extends ' + ', '.join(ts.bases)
            + '; inherited members are not listed, so a method it inherits may be reported missing'
        )
    if not py.methods:
        inventory.notes.append(
            f'{py.name} declares no public methods in Python ({py.location}), '
            'so this class passes vacuously'
        )
    available = ts.member_names()
    for method in py.methods:
        if _ts_candidates(method.name) & available:
            inventory.present.append(method.name)
            continue
        inventory.missing.append(MissingMethod(
            name=method.name,
            expected_ts=snake_to_camel(method.name),
            location=method.location,
            owner=method.owner,
            waiver=waivers.get(method.name),
        ))
    return inventory


def _python_class_candidates(surface) -> List[str]:
    """Names to try for the Python class behind a surface, best first."""
    ts = surface.typescript
    head = surface.key.split('.', 1)[0].split('(', 1)[0].strip()
    ordered = [
        surface.python.get('class'),
        head,
        *(surface.python.get('aliases') or []),
        ts.get('ctorClass'),
        ts.get('cls'),
    ]
    out: List[str] = []
    for name in ordered:
        if name and name not in out:
            out.append(name)
    return out


def _ts_class_of(surface) -> Optional[str]:
    return surface.typescript.get('ctorClass') or surface.typescript.get('cls')


def check_method_inventory(repo_root: Path, catalogue) -> List[ClassInventory]:
    """
    Public-method inventory for every class named by ``surface.yaml``.

    Raises ``MemberToolingError`` when node or the TypeScript member lister
    cannot run: an inventory that lists nothing must not read as parity.
    """
    index = PythonClassIndex(repo_root, catalogue.python_root)
    by_ts_key: Dict[str, ClassInventory] = {}
    targets: List[Dict[str, str]] = []
    waivers_for: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for surface in catalogue.surfaces:
        ts_class = _ts_class_of(surface)
        if not ts_class:
            continue
        ts_file = surface.typescript['file']
        key = f'{ts_file}::{ts_class}'
        inventory = by_ts_key.get(key)
        if inventory is None:
            inventory = by_ts_key[key] = ClassInventory(key=ts_class)
            targets.append({'cls': ts_class, 'file': ts_file})
        inventory.surfaces.append(surface.key)
        merged = waivers_for.setdefault(key, {})
        merged.update(surface.method_waivers or {})

    ts_classes = run_ts_members(repo_root, targets, catalogue.typescript_root)

    results: List[ClassInventory] = []
    for key, inventory in by_ts_key.items():
        ts_file, _, ts_class = key.partition('::')
        inventory.typescript = ts_classes.get(key)
        py_class = None
        tried = _python_class_candidates(_first_surface(catalogue, inventory.surfaces[0]))
        for candidate in tried:
            py_class = index.public_methods(candidate)
            if py_class is not None:
                break
        if py_class is None:
            inventory.skipped = (
                f'no Python class found for {", ".join(tried)} under {catalogue.python_root} '
                f'-- the surface names a function, not a class'
            )
            results.append(inventory)
            continue
        inventory.python = py_class
        if inventory.typescript is None or not inventory.typescript.found:
            absent = inventory.typescript.absent if inventory.typescript else 'not extracted'
            inventory.notes.append(f'TypeScript class {ts_class} is absent: {absent}')
        compare_class(inventory, waivers_for.get(key, {}))
        results.append(inventory)
    return results


def _first_surface(catalogue, key: str):
    for surface in catalogue.surfaces:
        if surface.key == key:
            return surface
    raise KeyError(key)
