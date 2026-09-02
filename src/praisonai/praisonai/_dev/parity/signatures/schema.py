"""
Shared schema for the signature-level parity checker.

Both extractors (``py_extract.py`` for Python, ``ts_extract.mjs`` for
TypeScript) emit the same JSON shape, and the comparator consumes it. Keeping
the shape in one place means a pre-extracted JSON fixture can be fed straight
into the comparator without either toolchain being present.

Schema (one object per surface)::

    {
      "surface":  "<key from surface.yaml>",
      "language": "python" | "typescript",
      "location": "src/.../file.py:LINE",        # repo-relative
      "params": [
        {
          "name":        "expected_output",        # as written in source
          "canonical":   "expectedOutput",         # camelCased (python) / as written (ts)
          "kind":        "positional" | "keyword" | "property"
                         | "var_positional" | "var_keyword",
          "required":    true | false,
          "default":     <JSON literal> | "<source text>" | null,
          "default_kind": "literal" | "expr" | null,
          "type_text":   "Optional[str]",
          "type_class":  "string" | "number" | "boolean" | "object" | "array"
                         | "callable" | "union" | "unknown"
        }
      ],
      "extra": { ... }                              # e.g. ctor_location, resolved_class
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

TYPE_CLASSES = (
    'string', 'number', 'boolean', 'object', 'array', 'callable', 'union', 'unknown',
)

PARAM_KINDS = ('positional', 'keyword', 'property', 'var_positional', 'var_keyword')

# Kinds that can never be matched by name against the other language.
VARIADIC_KINDS = ('var_positional', 'var_keyword')


@dataclass
class Param:
    """One parameter (Python) or one interface member / method parameter (TS)."""
    name: str
    canonical: str
    kind: str
    required: bool
    default: Any = None
    default_kind: Optional[str] = None  # 'literal' | 'expr' | None (no default)
    type_text: str = ''
    type_class: str = 'unknown'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'canonical': self.canonical,
            'kind': self.kind,
            'required': self.required,
            'default': self.default,
            'default_kind': self.default_kind,
            'type_text': self.type_text,
            'type_class': self.type_class,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Param':
        return cls(
            name=data['name'],
            canonical=data.get('canonical') or data['name'],
            kind=data.get('kind', 'positional'),
            required=bool(data.get('required', False)),
            default=data.get('default'),
            default_kind=data.get('default_kind'),
            type_text=data.get('type_text', '') or '',
            type_class=data.get('type_class', 'unknown') or 'unknown',
        )

    @property
    def variadic(self) -> bool:
        return self.kind in VARIADIC_KINDS


@dataclass
class SurfaceSignature:
    """The extracted signature of one surface in one language."""
    surface: str
    language: str
    location: str
    params: List[Param] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'surface': self.surface,
            'language': self.language,
            'location': self.location,
            'params': [p.to_dict() for p in self.params],
            'extra': dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SurfaceSignature':
        return cls(
            surface=data['surface'],
            language=data['language'],
            location=data.get('location', ''),
            params=[Param.from_dict(p) for p in data.get('params', [])],
            extra=dict(data.get('extra') or {}),
        )


def snake_to_camel(name: str) -> str:
    """``expected_output`` -> ``expectedOutput``. Leading underscores are kept."""
    stripped = name.lstrip('_')
    prefix = name[: len(name) - len(stripped)]
    parts = [p for p in stripped.split('_')]
    if not parts:
        return name
    head, *rest = parts
    return prefix + head + ''.join(p[:1].upper() + p[1:] for p in rest)


def split_top_level(text: str, sep: str) -> List[str]:
    """
    Split ``text`` on ``sep`` only at bracket depth 0 and outside quotes.

    Handles ``()``, ``[]``, ``{}`` and ``<>`` so that
    ``Dict[str, Any] | List[int]`` splits on ``|`` but not on the inner comma.
    """
    parts: List[str] = []
    depth = 0
    quote: Optional[str] = None
    current: List[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            current.append(ch)
            if ch == '\\' and i + 1 < len(text):
                current.append(text[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch in ('"', "'", '`'):
            quote = ch
            current.append(ch)
        elif ch in '([{<':
            depth += 1
            current.append(ch)
        elif ch in ')]}>':
            depth = max(0, depth - 1)
            current.append(ch)
        elif depth == 0 and text.startswith(sep, i):
            parts.append(''.join(current))
            current = []
            i += len(sep)
            continue
        else:
            current.append(ch)
        i += 1
    parts.append(''.join(current))
    return parts
