"""
Python signature extractor for the signature parity checker.

Parses ``praisonaiagents`` sources with :mod:`ast` only -- it never imports the
package, so it needs no optional dependencies and cannot be skewed by runtime
monkey-patching. Output follows the shared schema in :mod:`.schema`.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schema import Param, SurfaceSignature, snake_to_camel, split_top_level

DEFAULT_PYTHON_ROOT = 'src/praisonai-agents/praisonaiagents'


class PythonSurfaceNotFound(Exception):
    """Raised when a surface listed in ``surface.yaml`` cannot be located."""


# --------------------------------------------------------------------------- types

_SIMPLE_TYPES = {
    'str': 'string', 'bytes': 'string',
    'int': 'number', 'float': 'number', 'complex': 'number',
    'bool': 'boolean',
    'dict': 'object', 'Dict': 'object', 'Mapping': 'object', 'MutableMapping': 'object',
    'TypedDict': 'object', 'Type': 'object',
    'list': 'array', 'List': 'array', 'Sequence': 'array', 'MutableSequence': 'array',
    'set': 'array', 'Set': 'array', 'frozenset': 'array', 'FrozenSet': 'array',
    'tuple': 'array', 'Tuple': 'array', 'Iterable': 'array', 'Iterator': 'array',
    'Callable': 'callable', 'Coroutine': 'callable', 'Awaitable': 'callable',
    'Any': 'unknown', 'object': 'unknown', 'None': 'unknown', 'NoneType': 'unknown',
}


def _union_members(text: str) -> List[str]:
    """Flatten ``Optional[X]``, ``Union[A, B]`` and ``A | B`` into member types."""
    t = text.strip()
    if t.startswith(('"', "'")) and t.endswith(('"', "'")) and len(t) >= 2:
        # Forward reference written as a string annotation.
        return _union_members(t[1:-1])
    head, _, _ = t.partition('[')
    head = head.rsplit('.', 1)[-1]
    if head == 'Optional' and t.endswith(']'):
        return _union_members(t[t.index('[') + 1:-1])
    if head == 'Union' and t.endswith(']'):
        inner = t[t.index('[') + 1:-1]
        return [m for part in split_top_level(inner, ',') for m in _union_members(part)]
    parts = split_top_level(t, '|')
    if len(parts) > 1:
        return [m for part in parts for m in _union_members(part)]
    return [t]


def _single_type_class(text: str) -> str:
    t = text.strip()
    if not t:
        return 'unknown'
    head, _, _ = t.partition('[')
    head = head.rsplit('.', 1)[-1].strip()
    if head == 'Literal' and t.endswith(']'):
        inner = split_top_level(t[t.index('[') + 1:-1], ',')
        first = inner[0].strip() if inner else ''
        if first.startswith(('"', "'")):
            return 'string'
        if first in ('True', 'False'):
            return 'boolean'
        if first[:1].isdigit() or first.startswith('-'):
            return 'number'
        return 'unknown'
    if head in _SIMPLE_TYPES:
        return _SIMPLE_TYPES[head]
    if head[:1].isupper():
        # A class reference (Agent, Memory, BaseModel, ...) is an object.
        return 'object'
    return 'unknown'


def python_type_class(annotation: str) -> str:
    """Map a Python annotation's source text onto the shared ``type_class`` set."""
    if not annotation or not annotation.strip():
        return 'unknown'
    members = [m for m in _union_members(annotation) if m.strip() not in ('None', 'NoneType')]
    if not members:
        return 'unknown'
    classes = {_single_type_class(m) for m in members}
    if len(classes) == 1:
        return classes.pop()
    return 'union'


# ------------------------------------------------------------------------ defaults

def _json_safe(value: Any) -> Tuple[bool, Any]:
    """Return (ok, value) where value is JSON-serialisable (tuples/sets -> lists)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True, value
    if isinstance(value, (list, tuple, set, frozenset)):
        items = []
        for item in value:
            ok, converted = _json_safe(item)
            if not ok:
                return False, None
            items.append(converted)
        return True, items
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return False, None
            ok, converted = _json_safe(item)
            if not ok:
                return False, None
            out[key] = converted
        return True, out
    return False, None


def normalise_default(node: Optional[ast.AST]) -> Tuple[Any, Optional[str]]:
    """
    Turn a default-value AST node into ``(value, kind)``.

    Literals become JSON values with kind ``"literal"``; anything else keeps its
    source text with kind ``"expr"``. ``None`` node -> ``(None, None)``.
    """
    if node is None:
        return None, None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return ast.unparse(node), 'expr'
    ok, converted = _json_safe(value)
    if ok:
        return converted, 'literal'
    return ast.unparse(node), 'expr'


# ----------------------------------------------------------------------- extraction

def _params_of(fn: ast.AST, in_class: bool) -> List[Param]:
    args = fn.args
    positional = list(args.posonlyargs) + list(args.args)
    pos_defaults: List[Optional[ast.AST]] = (
        [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    )
    out: List[Param] = []
    for index, (arg, default) in enumerate(zip(positional, pos_defaults)):
        if index == 0 and in_class and arg.arg in ('self', 'cls'):
            continue
        out.append(_make_param(arg, default, 'positional'))
    if args.vararg is not None:
        out.append(_make_param(args.vararg, None, 'var_positional'))
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        out.append(_make_param(arg, default, 'keyword'))
    if args.kwarg is not None:
        out.append(_make_param(args.kwarg, None, 'var_keyword'))
    return out


def _make_param(arg: ast.arg, default: Optional[ast.AST], kind: str) -> Param:
    type_text = ast.unparse(arg.annotation) if arg.annotation is not None else ''
    value, default_kind = normalise_default(default)
    required = default is None and kind in ('positional', 'keyword')
    return Param(
        name=arg.arg,
        canonical=snake_to_camel(arg.arg),
        kind=kind,
        required=required,
        default=value,
        default_kind=default_kind,
        type_text=type_text,
        type_class=python_type_class(type_text),
    )


def discover_class(tree: ast.Module, init_first_param: str) -> Optional[str]:
    """Return the name of the class whose ``__init__`` takes ``init_first_param`` first after self."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == '__init__'
                and len(item.args.args) > 1
                and item.args.args[1].arg == init_first_param
            ):
                return node.name
    return None


def _find_function(
    tree: ast.Module, class_name: Optional[str], function: str,
) -> Tuple[Optional[ast.AST], Optional[str]]:
    """
    Locate ``function``. With ``class_name`` look only inside that class; without
    it, take the first module-level function or method (source order) with that
    name. Closures nested inside function bodies are never considered.
    """
    if class_name is not None:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function:
                        return item, class_name
        return None, None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return node, None
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function:
                    return item, node.name
    return None, None


def extract_python_surface(
    repo_root: Path,
    key: str,
    spec: Dict[str, Any],
    python_root: str = DEFAULT_PYTHON_ROOT,
) -> SurfaceSignature:
    """
    Extract one Python surface.

    ``spec`` keys (from ``surface.yaml``):

    - ``file``: path relative to ``python_root``
    - ``function``: function/method name
    - ``class`` (optional): enclosing class name
    - ``discover`` (optional): ``{"init_first_param": "agents"}`` -- resolve the
      class as the one whose ``__init__`` takes that parameter first
    """
    rel_file = spec['file']
    path = Path(repo_root) / python_root / rel_file
    if not path.is_file():
        raise PythonSurfaceNotFound(f'{key}: python file not found: {path}')
    tree = ast.parse(path.read_text(encoding='utf-8'))

    class_name: Optional[str] = spec.get('class')
    discover = spec.get('discover') or {}
    if class_name is None and discover.get('init_first_param'):
        class_name = discover_class(tree, discover['init_first_param'])
        if class_name is None:
            raise PythonSurfaceNotFound(
                f'{key}: no class in {rel_file} has __init__(self, {discover["init_first_param"]}, ...)'
            )

    fn, enclosing = _find_function(tree, class_name, spec['function'])
    if fn is None:
        where = f'{class_name}.' if class_name else ''
        raise PythonSurfaceNotFound(f'{key}: {where}{spec["function"]} not found in {rel_file}')

    location = f'{python_root}/{rel_file}:{fn.lineno}'
    extra: Dict[str, Any] = {}
    if enclosing:
        extra['resolved_class'] = enclosing
    if spec.get('aliases'):
        extra['aliases'] = list(spec['aliases'])
    return SurfaceSignature(
        surface=key,
        language='python',
        location=location,
        params=_params_of(fn, in_class=enclosing is not None),
        extra=extra,
    )


def extract_python_source(source: str, function: str, class_name: Optional[str] = None,
                          surface: str = 'fixture', location: str = '<string>') -> SurfaceSignature:
    """Extract from an in-memory source string (used by tests)."""
    tree = ast.parse(source)
    fn, enclosing = _find_function(tree, class_name, function)
    if fn is None:
        raise PythonSurfaceNotFound(f'{surface}: {function} not found')
    return SurfaceSignature(
        surface=surface,
        language='python',
        location=f'{location}:{fn.lineno}',
        params=_params_of(fn, in_class=enclosing is not None),
        extra={'resolved_class': enclosing} if enclosing else {},
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Debug helper: dump the Python side of every surface in surface.yaml as JSON."""
    import argparse
    import sys

    from .compare import find_repo_root, load_surfaces

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = find_repo_root(args.repo_root)
    catalogue = load_surfaces()
    out = [
        extract_python_surface(repo_root, s.key, s.python, catalogue.python_root).to_dict()
        for s in catalogue.surfaces
    ]
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
