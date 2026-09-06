"""
Comparator and CLI for the signature parity checker.

Pure functions (``compare_all``, ``evaluate``, ``render_markdown``,
``render_json``) work on pre-extracted :class:`SurfaceSignature` objects, so
they can be tested from JSON fixtures without Node or the TypeScript compiler.
``extract_all`` and :func:`main` wire in the real extractors.

Exit codes: 0 ok, 1 parity failure (gap, drift, waiver problem, nothing
checked), 2 tooling failure (node/typescript missing, surface not found).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from .py_extract import (
    DEFAULT_PYTHON_ROOT,
    PythonSurfaceNotFound,
    extract_python_surface,
    normalise_default,
)
from .schema import Param, SurfaceSignature, snake_to_camel

HERE = Path(__file__).resolve().parent
DEFAULT_SURFACE_FILE = HERE / 'surface.yaml'
DEFAULT_RULES_FILE = HERE / 'rules.yaml'
DEFAULT_WAIVERS_FILE = HERE / 'waivers.yaml'
TS_EXTRACTOR = HERE / 'ts_extract.mjs'
DEFAULT_TS_ROOT = 'src/praisonai-ts/src'

MD_OUTPUT = Path('src/praisonai-ts/SIGNATURE_PARITY.md')
JSON_OUTPUT = Path('src/praisonai-ts/signature-parity.json')
GENERATED_BY = 'praisonai._dev.parity.signatures'

BASELINE_REASON = 'baseline 2026-09-02: not yet ported to TypeScript'
BASELINE_OWNER = 'praisonai-ts'

# Resolution order, strictest rule first. `flattened` precedes `alias` because a
# flattening is the stricter statement of the two: `caching -> [cache, cacheTTL]`
# checks both TS fields, while the `caching -> cache` alias checked only one. With
# `alias` first the flattening never fired at all.
MATCH_ORDER = ('exact', 'camelCase', 'flattened', 'alias', 'missing')

EXIT_OK = 0
EXIT_PARITY = 1
EXIT_TOOLING = 2


class ToolingError(Exception):
    """Something outside the code under test is broken (node, typescript, config)."""


# ------------------------------------------------------------------ configuration

@dataclass
class Surface:
    """One entry of ``surface.yaml``."""
    key: str
    python: Dict[str, Any]
    typescript: Dict[str, Any]

    def ts_target(self) -> Dict[str, Any]:
        target = {'surface': self.key}
        target.update(self.typescript)
        return target


@dataclass
class SurfaceCatalogue:
    surfaces: List[Surface]
    python_root: str = DEFAULT_PYTHON_ROOT
    typescript_root: str = DEFAULT_TS_ROOT

    def get(self, key: str) -> Optional[Surface]:
        for s in self.surfaces:
            if s.key == key:
                return s
        return None


@dataclass
class Flattening:
    """
    One ``rules.yaml`` ``flattened`` entry: a nested Python config parameter that
    TypeScript spells out as several top-level fields.

    ``python_config`` (``"<file under python_root>:<ClassName>"``) and
    ``field_map`` (TS field -> field of that class) say which Python default each
    TS field must agree with. Without them only required-ness is checked, because
    the Python parameter's own default (usually ``None``) says nothing about what
    the individual fields resolve to.
    """
    fields: List[str] = field(default_factory=list)
    python_config: Optional[str] = None
    field_map: Dict[str, Optional[str]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, value: Any) -> 'Flattening':
        if isinstance(value, list):
            return cls(fields=[str(f) for f in value])
        if not isinstance(value, dict):
            raise ToolingError(f'rules.yaml: a flattened entry must be a list or a mapping, got {value!r}')
        mapping = value.get('fields') or {}
        if isinstance(mapping, list):
            return cls(fields=[str(f) for f in mapping], python_config=value.get('python_config'))
        return cls(
            fields=[str(f) for f in mapping],
            python_config=value.get('python_config'),
            field_map={str(k): (str(v) if v is not None else None) for k, v in mapping.items()},
        )


@dataclass
class Rules:
    """Contents of ``rules.yaml``."""
    case: str = 'snake_to_camel'
    aliases: Dict[str, Dict[str, str]] = field(default_factory=dict)
    flattened: Dict[str, Dict[str, Flattening]] = field(default_factory=dict)
    #: ``"<file>:<Class>"`` -> ``{field name: Param}``, resolved from the Python
    #: source by :func:`load_nested_config_defaults`. Empty when the comparator
    #: runs on pre-extracted fixtures with no repository to read.
    nested_defaults: Dict[str, Dict[str, Param]] = field(default_factory=dict)
    default_equivalences: List[Tuple[Any, Any]] = field(default_factory=list)
    #: ``(python expression text, typescript token)`` pairs. Separate from
    #: ``default_equivalences`` because a Python *expression* default (a module
    #: sentinel such as ``_UNSET``) is not a literal and must not be compared
    #: against literals of the same spelling.
    default_expr_equivalences: List[Tuple[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Rules':
        data = data or {}
        equivalences = []
        expr_equivalences = []
        for item in data.get('default_equivalences') or []:
            if 'python_expr' in item:
                expr_equivalences.append((item['python_expr'], item.get('typescript')))
            else:
                equivalences.append((item.get('python'), item.get('typescript')))
        return cls(
            default_expr_equivalences=expr_equivalences,
            case=data.get('case', 'snake_to_camel'),
            aliases={k: dict(v or {}) for k, v in (data.get('aliases') or {}).items()},
            flattened={k: {p: Flattening.from_yaml(f) for p, f in (v or {}).items()}
                       for k, v in (data.get('flattened') or {}).items()},
            default_equivalences=equivalences,
        )

    def canonical(self, python_name: str) -> str:
        if self.case == 'snake_to_camel':
            return snake_to_camel(python_name)
        return python_name


@dataclass
class Waiver:
    """One entry of ``waivers.yaml``: ``"<surface>.<python param>"``."""
    key: str
    reason: str
    owner: str
    issue: Optional[str] = None
    expires: Optional[date] = None
    kinds: Optional[List[str]] = None

    #: A waiver is keyed by parameter, so without this it silences every KIND of
    #: gap on that parameter. Waiving a default difference would then also hide a
    #: parameter becoming REQUIRED in TypeScript -- a change that breaks every
    #: caller. Found by making verbose/markdown/stream required behind the
    #: `Agent.__init__.output` waiver and watching the gate stay green.
    #: So required-ness is never covered implicitly: a waiver must name it.
    EXPLICIT_ONLY = ('required',)

    def covers(self, gap_kind: str) -> bool:
        """Whether this waiver suppresses a gap of ``gap_kind``."""
        if self.kinds is not None:
            return gap_kind in self.kinds
        return gap_kind not in self.EXPLICIT_ONLY

    @classmethod
    def from_dict(cls, key: str, data: Dict[str, Any]) -> 'Waiver':
        data = data or {}
        for required in ('reason', 'owner'):
            if not data.get(required):
                raise ToolingError(f'waiver "{key}" is missing required field "{required}"')
        expires = data.get('expires')
        if isinstance(expires, str):
            expires = date.fromisoformat(expires)
        kinds = data.get('kinds')
        if kinds is not None:
            if not isinstance(kinds, list) or not all(isinstance(k, str) for k in kinds):
                raise ToolingError(f'waiver "{key}": "kinds" must be a list of gap kinds')
            kinds = [str(k) for k in kinds]
        return cls(
            key=key,
            reason=str(data['reason']),
            owner=str(data['owner']),
            issue=str(data['issue']) if data.get('issue') else None,
            expires=expires,
            kinds=kinds,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {'reason': self.reason, 'owner': self.owner}
        if self.issue:
            out['issue'] = self.issue
        if self.expires:
            out['expires'] = self.expires
        if self.kinds is not None:
            out['kinds'] = list(self.kinds)
        return out

    def expired(self, today: date) -> bool:
        return self.expires is not None and today > self.expires


def load_surfaces(path: Optional[Path] = None) -> SurfaceCatalogue:
    path = path or DEFAULT_SURFACE_FILE
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    surfaces = []
    for item in data.get('surfaces') or []:
        if not item.get('key') or not item.get('python') or not item.get('typescript'):
            raise ToolingError(f'surface.yaml entry is missing key/python/typescript: {item}')
        surfaces.append(Surface(key=item['key'], python=dict(item['python']),
                                typescript=dict(item['typescript'])))
    return SurfaceCatalogue(
        surfaces=surfaces,
        python_root=data.get('python_root', DEFAULT_PYTHON_ROOT),
        typescript_root=data.get('typescript_root', DEFAULT_TS_ROOT),
    )


def load_rules(path: Optional[Path] = None) -> Rules:
    path = path or DEFAULT_RULES_FILE
    return Rules.from_dict(yaml.safe_load(path.read_text(encoding='utf-8')) or {})


def read_config_class_defaults(repo_root: Path, python_root: str, spec: str) -> Dict[str, Param]:
    """
    Field defaults of a Python config dataclass named ``"<file>:<ClassName>"``.

    ``Agent(output=None)`` resolves to ``OutputConfig()``, so ``OutputConfig``'s
    field defaults -- not the ``output`` parameter's ``None`` -- are what the
    flattened TypeScript fields must agree with.
    """
    rel, _, class_name = spec.partition(':')
    if not rel or not class_name:
        raise ToolingError(f'rules.yaml: python_config must be "<file>:<ClassName>", got "{spec}"')
    path = Path(repo_root) / python_root / rel
    if not path.is_file():
        raise ToolingError(f'rules.yaml: python_config file not found: {path}')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    decl = next((n for n in ast.walk(tree)
                 if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    if decl is None:
        raise ToolingError(f'rules.yaml: python_config class {class_name} not found in {path}')
    out: Dict[str, Param] = {}
    for stmt in decl.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        name = stmt.target.id
        default, kind = normalise_default(stmt.value)
        out[name] = Param(
            name=name, canonical=snake_to_camel(name), kind='keyword',
            required=stmt.value is None, default=default, default_kind=kind,
            type_text=ast.unparse(stmt.annotation) if stmt.annotation is not None else '',
        )
    return out


def load_nested_config_defaults(rules: Rules, repo_root: Path, python_root: str) -> None:
    """Fill ``rules.nested_defaults`` for every ``python_config`` named in the rules."""
    for surface in rules.flattened.values():
        for flat in surface.values():
            if flat.python_config and flat.python_config not in rules.nested_defaults:
                rules.nested_defaults[flat.python_config] = read_config_class_defaults(
                    repo_root, python_root, flat.python_config)


def load_waivers(path: Optional[Path] = None) -> List[Waiver]:
    path = path or DEFAULT_WAIVERS_FILE
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    entries = data.get('waivers') or {}
    if not isinstance(entries, dict):
        raise ToolingError('waivers.yaml: "waivers" must be a mapping keyed "<surface>.<param>"')
    return [Waiver.from_dict(str(k), v) for k, v in sorted(entries.items())]


def write_waivers(path: Path, waivers: Iterable[Waiver]) -> None:
    header = (
        '# Signature parity waivers.\n'
        '#\n'
        '# Key: "<surface key>.<python parameter>". Required: reason, owner.\n'
        '# Optional: issue, expires (ISO date; an expired waiver FAILS the check).\n'
        '# A waiver whose gap no longer exists is stale and FAILS the check: delete it.\n'
        '# Regenerate missing entries with: python -m praisonai._dev.parity.signatures --baseline\n'
        '\n'
    )
    body = {'waivers': {w.key: w.to_dict() for w in sorted(waivers, key=lambda w: w.key)}}
    text = yaml.safe_dump(body, sort_keys=True, allow_unicode=True, default_flow_style=False, width=120)
    path.write_text(header + text, encoding='utf-8')


# ------------------------------------------------------------------- comparison

@dataclass
class Gap:
    kind: str      # 'missing' | 'required' | 'default'
    detail: str


@dataclass
class ParamRow:
    python: Param
    match: str                       # one of MATCH_ORDER
    ts: Optional[Param] = None       # matched TS member (None for flattened/missing)
    ts_names: List[str] = field(default_factory=list)
    #: The TS members a `flattened` match resolved to. Populated so gap detection
    #: can run on them: `ts` stays None for a flattening, and gating gap
    #: detection on `ts is not None` is what let a flattened field become
    #: REQUIRED (`new Agent({ name })` stops compiling) with a green gate.
    ts_members: List[Param] = field(default_factory=list)
    gap: Optional[Gap] = None
    warnings: List[str] = field(default_factory=list)
    waived: Optional[Waiver] = None

    @property
    def ts_name(self) -> str:
        if self.ts is not None:
            return self.ts.name
        return ', '.join(self.ts_names) if self.ts_names else ''


@dataclass
class SurfaceComparison:
    key: str
    python: SurfaceSignature
    typescript: SurfaceSignature
    rows: List[ParamRow] = field(default_factory=list)
    ts_only: List[Param] = field(default_factory=list)

    def ts_only_required(self) -> List[Param]:
        """
        TS-only members the caller MUST pass. An optional one is informational.

        The constructor's own options parameter (`constructor(config:
        SimpleAgentConfig)`) is excluded: it is required, but a required options
        OBJECT is not a parity gap -- its members are the compared surface, and
        Python spells them out as keyword arguments.
        """
        carriers = set(self.typescript.extra.get('options_parameters') or [])
        return [p for p in self.ts_only if p.required and p.name not in carriers]

    def counts(self) -> Dict[str, int]:
        counts = {m: 0 for m in MATCH_ORDER}
        gaps = 0
        waived = 0
        for row in self.rows:
            counts[row.match] += 1
            if row.gap is not None and row.gap.kind != 'missing':
                gaps += 1
            if row.waived is not None:
                waived += 1
        return {
            'params': len(self.rows),
            'exact': counts['exact'],
            'camelCase': counts['camelCase'],
            'alias': counts['alias'],
            'flattened': counts['flattened'],
            'missing': counts['missing'],
            'mismatches': gaps,
            'waived': waived,
            'ts_only': len(self.ts_only),
            'ts_total': len(self.typescript.params),
        }


#: The TypeScript extractor emits this when the constructor decides a member's
#: fallback in a form it cannot evaluate. It is NOT the same as "no default", and
#: must never compare equal to anything: reading it as `undefined` is how an
#: invented default (`reasoningEffort: 'high'`, approval forced on) slipped past.
UNKNOWN_DEFAULT_KIND = 'unknown'


def _ts_default_token(param: Param) -> Any:
    """The comparable form of a TS default: JSON literal, expr text, or 'undefined'."""
    if param.default_kind is None:
        return 'undefined'
    return param.default


def defaults_equivalent(py: Param, ts: Param, rules: Rules) -> bool:
    """True when the Python default and the TS effective default mean the same thing."""
    if ts.default_kind == UNKNOWN_DEFAULT_KIND:
        return False
    ts_token = _ts_default_token(ts)
    py_value = py.default
    if py.default_kind == 'literal' and ts.default_kind == 'literal':
        if py_value == ts_token and type(py_value) is type(ts_token):
            return True
    elif py.default_kind == 'expr' and ts.default_kind == 'expr':
        if py_value == ts_token:
            return True
    for py_eq, ts_eq in rules.default_equivalences:
        if py.default_kind == 'literal' and py_value == py_eq and type(py_value) is type(py_eq):
            if ts_token == ts_eq and type(ts_token) is type(ts_eq):
                return True
    # A Python module-level sentinel (``_UNSET``) and TypeScript's `undefined`
    # are the same "the caller passed nothing" marker; only the spelling of the
    # sentinel differs, so the two sides resolve identically.
    for py_expr, ts_eq in rules.default_expr_equivalences:
        if py.default_kind == 'expr' and py_value == py_expr:
            if ts_token == ts_eq and type(ts_token) is type(ts_eq):
                return True
    return False


def _fmt_default(param: Optional[Param]) -> str:
    if param is None:
        return ''
    if param.required:
        return '*required*'
    if param.default_kind == UNKNOWN_DEFAULT_KIND:
        return 'unknown'
    if param.default_kind is None:
        return 'undefined'
    if param.default_kind == 'literal':
        return json.dumps(param.default)
    return f'`{param.default}`'


def _fmt_row_ts_default(row: ParamRow) -> str:
    """
    The TS-default cell for one row.

    A flattened row has no single TS member, so it lists each field's default.
    Leaving the cell blank (which it was) meant a flattened field's default
    could change without the report changing -- and report freshness is a gate.
    """
    if row.ts is not None:
        return _fmt_default(row.ts)
    if not row.ts_members:
        return ''
    return ', '.join(f'{m.name}={_fmt_default(m)}' for m in row.ts_members)


def compare_surface(py: SurfaceSignature, ts: SurfaceSignature, rules: Rules) -> SurfaceComparison:
    """Classify every Python parameter against the TS members and detect gaps."""
    ts_by_name: Dict[str, Param] = {p.name: p for p in ts.params if not p.variadic}
    aliases = rules.aliases.get(py.surface, {})
    flattened = rules.flattened.get(py.surface, {})
    matched_ts: set = set()
    rows: List[ParamRow] = []

    for param in py.params:
        if param.variadic:
            continue
        row = ParamRow(python=param, match='missing')
        canonical = rules.canonical(param.name)
        flat = flattened.get(param.name)
        # Resolution order: MATCH_ORDER. `flattened` beats `alias` -- see the
        # comment on that constant.
        if param.name in ts_by_name:
            row.match, row.ts = 'exact', ts_by_name[param.name]
        elif canonical in ts_by_name:
            row.match, row.ts = 'camelCase', ts_by_name[canonical]
        elif flat is not None and all(f in ts_by_name for f in flat.fields):
            row.match = 'flattened'
            row.ts_names = list(flat.fields)
            row.ts_members = [ts_by_name[f] for f in flat.fields]
        elif aliases.get(param.name) in ts_by_name:
            row.match, row.ts = 'alias', ts_by_name[aliases[param.name]]

        if row.ts is not None:
            matched_ts.add(row.ts.name)
            _detect_gaps(row, rules)
        elif row.match == 'flattened':
            matched_ts.update(row.ts_names)
            _detect_flattened_gaps(row, rules, flat)
        else:
            row.gap = Gap('missing', f'is missing from TypeScript (looked for `{canonical}`)')
        rows.append(row)

    ts_only = [p for p in ts.params if not p.variadic and p.name not in matched_ts]
    return SurfaceComparison(key=py.surface, python=py, typescript=ts, rows=rows, ts_only=ts_only)


def _detect_gaps(row: ParamRow, rules: Rules) -> None:
    py, ts = row.python, row.ts
    assert ts is not None
    if py.required != ts.required:
        side = 'required in Python but optional in TypeScript' if py.required \
            else 'optional in Python but required in TypeScript'
        row.gap = Gap('required', f'is {side} (TS `{ts.name}`)')
    elif not py.required and not defaults_equivalent(py, ts, rules):
        row.gap = Gap(
            'default',
            f'default differs: python={_fmt_default(py)} typescript={_fmt_default(ts)} (TS `{ts.name}`)',
        )
    if py.type_class != 'unknown' and ts.type_class != 'unknown' and py.type_class != ts.type_class:
        row.warnings.append(f'type differs: python {py.type_class} ({py.type_text}) vs typescript {ts.type_class} ({ts.type_text})')


def _detect_flattened_gaps(row: ParamRow, rules: Rules, flat: Flattening) -> None:
    """
    Check every TS member a flattening resolved to.

    Before this existed a `flattened` row set `ts_names` and left `ts` None, and
    `compare_surface` only ran gap detection `if row.ts is not None` -- so the
    required-ness and defaults of those fields were never compared at all.
    Making `verbose`, `markdown` and `stream` REQUIRED in `SimpleAgentConfig`
    (which stops `new Agent({ name })` compiling for every user) left the report
    byte-identical and every gate green.
    """
    py = row.python
    nested = rules.nested_defaults.get(flat.python_config or '', {})
    required_problems: List[str] = []
    default_problems: List[str] = []
    for member in row.ts_members:
        # The Python side of this field: the nested config's field when the rule
        # names one, else the flattened parameter itself.
        py_field_name = flat.field_map.get(member.name, member.name) if flat.field_map else None
        py_side = nested.get(py_field_name) if py_field_name else None
        expected_required = py_side.required if py_side is not None else py.required
        if expected_required != member.required:
            side = 'required in Python but optional in TypeScript' if expected_required \
                else 'optional in Python but required in TypeScript'
            required_problems.append(f'`{member.name}` is {side}')
            continue
        if member.required:
            continue
        if py_side is None:
            # A TS field with no Python counterpart (`cacheTTL`). Nothing to
            # compare its default against; required-ness above is the whole check.
            continue
        if not defaults_equivalent(py_side, member, rules):
            default_problems.append(
                f'`{member.name}` default differs: python {py_field_name}='
                f'{_fmt_default(py_side)} typescript={_fmt_default(member)}'
            )
    problems = required_problems + default_problems
    if not problems:
        return
    where = f'flattened to TS [{", ".join(row.ts_names)}]'
    row.gap = Gap(
        'required' if required_problems else 'default',
        f'is {where} and {"; ".join(problems)}',
    )


def signatures_from_json(items: Iterable[Dict[str, Any]]) -> Dict[str, SurfaceSignature]:
    """Index a list of schema dicts by surface key."""
    return {s['surface']: SurfaceSignature.from_dict(s) for s in items}


def compare_all(
    python: Dict[str, SurfaceSignature],
    typescript: Dict[str, SurfaceSignature],
    rules: Rules,
    keys: Optional[Sequence[str]] = None,
) -> List[SurfaceComparison]:
    """Compare every surface present on both sides (in ``keys`` order if given)."""
    order = list(keys) if keys is not None else [k for k in python if k in typescript]
    comparisons = []
    for key in order:
        if key not in python:
            raise ToolingError(f'surface {key}: no Python extraction')
        if key not in typescript:
            raise ToolingError(f'surface {key}: no TypeScript extraction')
        comparisons.append(compare_surface(python[key], typescript[key], rules))
    return comparisons


# ------------------------------------------------------------------- evaluation

@dataclass
class Evaluation:
    failures: List[str] = field(default_factory=list)
    active_waivers: List[Waiver] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def evaluate(
    comparisons: List[SurfaceComparison],
    waivers: List[Waiver],
    today: Optional[date] = None,
) -> Evaluation:
    """
    Apply the gate rules. Mutates ``row.waived`` on covered rows.

    a) every active waiver is reported; b) expired waiver fails; c) stale
    waiver fails; d) un-waived missing/required/default gap fails; e) zero
    surfaces or zero params on either side fails ("nothing was checked").
    """
    today = today or date.today()
    result = Evaluation()

    if not comparisons:
        result.failures.append('nothing was checked: zero surfaces were compared')
        return result
    py_total = sum(len(c.python.params) for c in comparisons)
    ts_total = sum(len(c.typescript.params) for c in comparisons)
    if py_total == 0:
        result.failures.append('nothing was checked: the Python extractor produced zero parameters')
    if ts_total == 0:
        result.failures.append('nothing was checked: the TypeScript extractor produced zero parameters')

    by_key = {w.key: w for w in waivers}
    used: set = set()
    for comparison in comparisons:
        # A TS-only member that is REQUIRED is a parity failure: TypeScript
        # callers must pass something Python has no way to express, so no
        # program can be written against both SDKs. `ts_only` used to be
        # computed and rendered and never looked at, so adding a required
        # `tenantId` to SimpleAgentConfig failed only on report freshness --
        # and running `--write`, exactly what the CI error tells you to do,
        # made it green. An OPTIONAL TS-only member stays informational.
        for member in comparison.ts_only_required():
            key = f'{comparison.key}.{member.name}'
            waiver = by_key.get(key)
            detail = (f'TypeScript-only member `{member.name}` is required, so a TypeScript '
                      f'caller must pass a value Python cannot express')
            if waiver is None:
                result.failures.append(
                    f'{comparison.key}: {detail} -- make it optional, port it to Python, '
                    f'or add a waiver "{key}"'
                )
                continue
            used.add(key)
            if waiver.expired(today):
                result.failures.append(
                    f'{comparison.key}: waiver for `{member.name}` expired on '
                    f'{waiver.expires.isoformat()} but the gap remains ({detail}) '
                    f'-- port it or extend the waiver'
                )
        for row in comparison.rows:
            for warning in row.warnings:
                result.warnings.append(f'{comparison.key}: `{row.python.name}` {warning}')
            if row.gap is None:
                continue
            key = f'{comparison.key}.{row.python.name}'
            waiver = by_key.get(key)
            if waiver is not None and not waiver.covers(row.gap.kind):
                # The waiver exists but does not name this kind of gap. Required-ness
                # is never covered implicitly, so a parameter turning required in
                # TypeScript still fails even where its default is waived.
                used.add(key)
                result.failures.append(
                    f'{comparison.key}: parameter `{row.python.name}` {row.gap.detail} '
                    f'-- the waiver "{key}" does not cover a {row.gap.kind} gap; '
                    f'port it, or add {row.gap.kind!r} to that waiver\'s "kinds" and say why'
                )
                continue
            if waiver is None:
                result.failures.append(
                    f'{comparison.key}: parameter `{row.python.name}` {row.gap.detail} '
                    f'-- port it or add a waiver "{key}"'
                )
                continue
            used.add(key)
            row.waived = waiver
            if waiver.expired(today):
                result.failures.append(
                    f'{comparison.key}: waiver for parameter `{row.python.name}` expired on '
                    f'{waiver.expires.isoformat()} but the gap remains ({row.gap.detail}) '
                    f'-- port it or extend the waiver'
                )
    for waiver in waivers:
        if waiver.key not in used:
            result.failures.append(
                f'stale waiver "{waiver.key}": the gap it covers no longer exists -- delete it from waivers.yaml'
            )
    result.active_waivers = [w for w in waivers if w.key in used and not w.expired(today)]
    return result


# -------------------------------------------------------------------- rendering

def _md_escape(text: str) -> str:
    return text.replace('|', '\\|')


def _status(row: ParamRow) -> str:
    if row.gap is None:
        return 'ok' if not row.warnings else 'ok (type differs)'
    label = {'missing': 'MISSING', 'required': 'required mismatch', 'default': 'default mismatch'}[row.gap.kind]
    return f'{label} (waived)' if row.waived else label


def render_surface_markdown(comparison: SurfaceComparison) -> str:
    """Side-by-side table for one surface."""
    py, ts = comparison.python, comparison.typescript
    lines = [f'### `{comparison.key}`', '']
    ts_loc = f'`{ts.location}`'
    if ts.extra.get('ctor_location'):
        ts_loc += f' (ctor `{ts.extra["ctor_location"]}`)'
    lines.append(f'- Python: `{py.location}`')
    lines.append(f'- TypeScript: {ts_loc}')
    if py.extra.get('aliases'):
        lines.append(f'- Python aliases: {", ".join(py.extra["aliases"])}')
    c = comparison.counts()
    lines.append(
        f'- Counts: {c["params"]} python params: {c["exact"]} exact, {c["camelCase"]} camelCase, '
        f'{c["alias"]} alias, {c["flattened"]} flattened, {c["missing"]} missing; '
        f'{c["mismatches"]} mismatches; {c["waived"]} waived; {c["ts_only"]} TS-only of {c["ts_total"]}'
    )
    lines.append('')
    lines.append('| Python param | Kind | Py default | Py type | Match | TS name | TS default | TS type | Status |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for row in comparison.rows:
        p = row.python
        lines.append('| ' + ' | '.join(_md_escape(x) for x in (
            f'`{p.name}`', p.kind, _fmt_default(p), f'`{p.type_text}`' if p.type_text else '',
            row.match, f'`{row.ts_name}`' if row.ts_name else '', _fmt_row_ts_default(row),
            f'`{row.ts.type_text}`' if row.ts is not None and row.ts.type_text else '',
            _status(row),
        )) + ' |')
    lines.append('')
    if comparison.ts_only:
        lines.append('TS-only members: ' + ', '.join(
            f'`{p.name}`' + ('' if p.required else '?') for p in comparison.ts_only))
        if comparison.ts_only_required():
            lines.append('')
            lines.append('TS-only members that are REQUIRED (a TypeScript caller must pass them): '
                         + ', '.join(f'`{p.name}`' for p in comparison.ts_only_required()))
    else:
        lines.append('TS-only members: none')
    lines.append('')
    return '\n'.join(lines)


def totals(comparisons: List[SurfaceComparison]) -> Dict[str, int]:
    keys = ['params', 'exact', 'camelCase', 'alias', 'flattened', 'missing', 'mismatches', 'waived', 'ts_only', 'ts_total']
    out = {k: 0 for k in keys}
    for c in comparisons:
        for k, v in c.counts().items():
            out[k] += v
    out['surfaces'] = len(comparisons)
    return out


def render_markdown(comparisons: List[SurfaceComparison], waivers: List[Waiver]) -> str:
    """Whole SIGNATURE_PARITY.md. Deterministic: no dates, relative paths only."""
    lines = [
        '# Signature Parity: praisonaiagents (Python) vs praisonai-ts (TypeScript)',
        '',
        f'<!-- Generated by `python -m {GENERATED_BY} --write`. Do not edit by hand. -->',
        '',
        '## What this measures',
        '',
        'For each curated surface in `surface.yaml`, every Python parameter (positional and',
        'keyword-only; `*args`/`**kwargs` excluded) is looked up on the TypeScript side',
        'as an interface member or method parameter. Matching order: **exact** name,',
        '**camelCase** (`snake_to_camel`), **flattened** (a nested Python config exposed as',
        'several TS fields), **alias** (`rules.yaml`), else **missing**. For matched pairs the',
        'checker compares required-ness and the effective default (TS constructor',
        'fallbacks such as `config.x ?? v` count as defaults); a flattened parameter is',
        'checked against every TS field it names, and against the Python nested-config',
        "field defaults when `rules.yaml` names them. A TS default the extractor cannot",
        'evaluate reads as `unknown` and needs a waiver rather than passing as `undefined`.',
        'A **required** TS-only member fails the check; an optional one is informational.',
        'Type classes are compared as a warning only. Every gap must be waived in',
        '`waivers.yaml` or the check fails.',
        'This complements `PARITY.md`, which only tracks whether an export exists.',
        '',
        '## Summary',
        '',
        '| Surface | Params | Exact | camelCase | Alias | Flattened | Missing | Mismatches | Waived | TS-only / TS total |',
        '|---|---|---|---|---|---|---|---|---|---|',
    ]
    for c in comparisons:
        n = c.counts()
        lines.append(
            f'| `{c.key}` | {n["params"]} | {n["exact"]} | {n["camelCase"]} | {n["alias"]} | {n["flattened"]} '
            f'| {n["missing"]} | {n["mismatches"]} | {n["waived"]} | {n["ts_only"]} / {n["ts_total"]} |'
        )
    t = totals(comparisons)
    lines.append(
        f'| **Total ({t["surfaces"]} surfaces)** | {t["params"]} | {t["exact"]} | {t["camelCase"]} | {t["alias"]} '
        f'| {t["flattened"]} | {t["missing"]} | {t["mismatches"]} | {t["waived"]} | {t["ts_only"]} / {t["ts_total"]} |'
    )
    lines += ['', '## Surfaces', '']
    for c in comparisons:
        lines.append(render_surface_markdown(c))
    lines += ['## Active waivers', '']
    if waivers:
        lines.append('| Key | Reason | Owner | Issue | Expires |')
        lines.append('|---|---|---|---|---|')
        for w in sorted(waivers, key=lambda w: w.key):
            lines.append('| ' + ' | '.join(_md_escape(x) for x in (
                f'`{w.key}`', w.reason, w.owner, w.issue or '', w.expires.isoformat() if w.expires else '',
            )) + ' |')
    else:
        lines.append('None.')
    lines.append('')
    return '\n'.join(lines)


def render_json(comparisons: List[SurfaceComparison], waivers: List[Waiver]) -> str:
    """Machine-readable output. Deterministic: sorted keys, no dates."""
    surfaces: Dict[str, Any] = {}
    for c in comparisons:
        params = []
        for row in c.rows:
            entry = row.python.to_dict()
            entry.update({
                'match': row.match,
                'ts_name': row.ts_name or None,
                'ts': row.ts.to_dict() if row.ts is not None else None,
                'ts_members': [m.to_dict() for m in row.ts_members] or None,
                'gap': {'kind': row.gap.kind, 'detail': row.gap.detail} if row.gap else None,
                'waived': row.waived.key if row.waived else None,
                'warnings': list(row.warnings),
            })
            params.append(entry)
        surfaces[c.key] = {
            'python': {'location': c.python.location, **c.python.extra},
            'typescript': {'location': c.typescript.location, **c.typescript.extra},
            'counts': c.counts(),
            'params': params,
            'ts_only': [p.to_dict() for p in c.ts_only],
            'ts_only_required': [p.name for p in c.ts_only_required()],
        }
    doc = {
        'generatedBy': GENERATED_BY,
        'surfaces': surfaces,
        'totals': totals(comparisons),
        'waivers': [
            {'key': w.key, 'reason': w.reason, 'owner': w.owner, 'issue': w.issue,
             'expires': w.expires.isoformat() if w.expires else None}
            for w in sorted(waivers, key=lambda w: w.key)
        ],
    }
    return json.dumps(doc, indent=2, sort_keys=True) + '\n'


# ------------------------------------------------------------ rules self-test

def validate_rules(
    rules: Rules,
    python: Dict[str, SurfaceSignature],
    typescript: Dict[str, SurfaceSignature],
) -> List[str]:
    """
    Problems with ``rules.yaml`` itself, checked against a real extraction.

    Every entry in this file exists to make a match happen. An entry that can
    never fire is dead weight that reads as coverage: eight of them had
    accumulated -- aliases for Python parameters that no longer exist, aliases
    shadowed by the exact/camelCase tiers that run first, a pure case change
    (which the file's own header says an alias must not be), a flattening
    shadowed by an alias, and two ``default_equivalences`` the literal branch of
    :func:`defaults_equivalent` returns True for before the loop is reached.
    ``test_config_files_load`` did not catch any of them because it only asserted
    that the YAML says what the YAML says.

    Returns a list of human-readable problems; empty means the rules are clean.
    """
    problems: List[str] = []

    for py_value, ts_value in rules.default_equivalences:
        if py_value == ts_value and type(py_value) is type(ts_value):
            problems.append(
                f'default_equivalences: {{python: {py_value!r}, typescript: {ts_value!r}}} is '
                f'unreachable -- identical literals already compare equal before the loop'
            )

    def tiers_before(surface: str, py_name: str, ts_names: set) -> Optional[str]:
        """The earlier MATCH_ORDER tier that already resolves ``py_name``, if any."""
        if py_name in ts_names:
            return f'the exact-name tier already matches TS `{py_name}`'
        canonical = rules.canonical(py_name)
        if canonical in ts_names:
            return f'the camelCase tier already matches TS `{canonical}`'
        return None

    for surface, aliases in sorted(rules.aliases.items()):
        if surface not in python or surface not in typescript:
            continue
        py_names = {p.name for p in python[surface].params}
        ts_names = {p.name for p in typescript[surface].params if not p.variadic}
        flattened = rules.flattened.get(surface, {})
        for py_name, ts_name in sorted(aliases.items()):
            where = f'aliases.{surface}.{py_name} -> {ts_name}'
            if py_name not in py_names:
                problems.append(f'{where}: no Python parameter named `{py_name}` on this surface')
                continue
            if rules.canonical(py_name) == ts_name:
                problems.append(
                    f'{where}: is a pure case change, which the camelCase tier already does '
                    f'-- delete it (rules.yaml says an alias must NOT be a pure case change)'
                )
                continue
            shadow = tiers_before(surface, py_name, ts_names)
            if shadow:
                problems.append(f'{where}: never fires -- {shadow}')
                continue
            if py_name in flattened and all(f in ts_names for f in flattened[py_name].fields):
                problems.append(
                    f'{where}: never fires -- the flattened rule for `{py_name}` resolves first'
                )
                continue
            if ts_name not in ts_names:
                problems.append(f'{where}: no TypeScript member named `{ts_name}` on this surface')

    for surface, entries in sorted(rules.flattened.items()):
        if surface not in python or surface not in typescript:
            continue
        py_names = {p.name for p in python[surface].params}
        ts_names = {p.name for p in typescript[surface].params if not p.variadic}
        for py_name, flat in sorted(entries.items()):
            where = f'flattened.{surface}.{py_name}'
            if py_name not in py_names:
                problems.append(f'{where}: no Python parameter named `{py_name}` on this surface')
                continue
            shadow = tiers_before(surface, py_name, ts_names)
            if shadow:
                problems.append(f'{where}: never fires -- {shadow}')
                continue
            missing = [f for f in flat.fields if f not in ts_names]
            if missing:
                problems.append(
                    f'{where}: TypeScript member(s) {", ".join("`" + m + "`" for m in missing)} '
                    f'do not exist, so the rule never fires'
                )
                continue
            if not flat.fields:
                problems.append(f'{where}: lists no TypeScript fields')
                continue
            nested = rules.nested_defaults.get(flat.python_config or '')
            for ts_field, py_field in sorted(flat.field_map.items()):
                if py_field is None:
                    continue
                if nested is None:
                    problems.append(
                        f'{where}.{ts_field}: maps to Python `{py_field}` but no python_config '
                        f'was resolved to look it up in'
                    )
                elif py_field not in nested:
                    problems.append(
                        f'{where}.{ts_field}: `{flat.python_config}` has no field `{py_field}`'
                    )
    return problems


# ------------------------------------------------------------------- extraction

def find_repo_root(explicit: Optional[Path] = None) -> Path:
    """``--repo-root`` > nearest ``.git`` above cwd > nearest ``.git`` above this file."""
    if explicit is not None:
        root = Path(explicit).resolve()
        if not (root / 'src').is_dir():
            raise ToolingError(f'--repo-root {root} does not look like the monorepo (no src/)')
        return root
    for start in (Path.cwd(), HERE):
        current = start.resolve()
        while True:
            if (current / '.git').exists() and (current / 'src').is_dir():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise ToolingError('cannot find the repository root; pass --repo-root')


def run_ts_extractor(repo_root: Path, targets: List[Dict[str, Any]],
                     ts_root: str = DEFAULT_TS_ROOT) -> List[Dict[str, Any]]:
    """Run ``ts_extract.mjs`` and return the parsed JSON list. Raises ToolingError."""
    node = shutil.which('node')
    if node is None:
        raise ToolingError('node is not on PATH; the TypeScript extractor needs Node.js')
    cmd = [node, str(TS_EXTRACTOR), '--repo-root', str(repo_root), '--ts-root', ts_root]
    proc = subprocess.run(
        cmd, input=json.dumps(targets), capture_output=True, text=True, env=os.environ.copy(),
    )
    if proc.returncode != 0:
        raise ToolingError(
            f'ts_extract.mjs exited {proc.returncode}:\n{proc.stderr.strip() or proc.stdout.strip()}'
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ToolingError(f'ts_extract.mjs printed invalid JSON: {exc}\n{proc.stdout[:500]}')
    if not isinstance(data, list):
        raise ToolingError('ts_extract.mjs output is not a JSON array')
    return data


def extract_all(
    repo_root: Path,
    catalogue: SurfaceCatalogue,
    keys: Optional[Sequence[str]] = None,
) -> Tuple[Dict[str, SurfaceSignature], Dict[str, SurfaceSignature]]:
    """Extract both sides for every (or the selected) surface."""
    surfaces = catalogue.surfaces if keys is None else [s for s in catalogue.surfaces if s.key in keys]
    if keys is not None:
        unknown = set(keys) - {s.key for s in surfaces}
        if unknown:
            raise ToolingError(f'unknown surface key(s): {", ".join(sorted(unknown))}')
    python: Dict[str, SurfaceSignature] = {}
    for s in surfaces:
        try:
            python[s.key] = extract_python_surface(repo_root, s.key, s.python, catalogue.python_root)
        except (PythonSurfaceNotFound, SyntaxError, OSError) as exc:
            raise ToolingError(str(exc))
    ts_items = run_ts_extractor(repo_root, [s.ts_target() for s in surfaces], catalogue.typescript_root)
    typescript = signatures_from_json(ts_items)
    return python, typescript


def baseline_waivers(comparisons: List[SurfaceComparison], existing: List[Waiver],
                     reason: str = BASELINE_REASON, owner: str = BASELINE_OWNER) -> List[Waiver]:
    """Existing waivers plus one for every currently un-waived gap (never overwrites)."""
    by_key = {w.key: w for w in existing}
    for key in _gap_keys(comparisons):
        if key not in by_key:
            by_key[key] = Waiver(key=key, reason=reason, owner=owner)
    return [by_key[k] for k in sorted(by_key)]


def _gap_keys(comparisons: List[SurfaceComparison]) -> set:
    """Every waiver key a current gap would need, Python-side and TS-only alike."""
    keys = set()
    for c in comparisons:
        keys.update(f'{c.key}.{row.python.name}' for row in c.rows if row.gap is not None)
        keys.update(f'{c.key}.{m.name}' for m in c.ts_only_required())
    return keys


# -------------------------------------------------------------------------- CLI

def prune_waivers(comparisons: List[SurfaceComparison], waivers: List[Waiver]) -> List[Waiver]:
    """Return the waivers whose gap still exists, dropping stale ones."""
    live = _gap_keys(comparisons)
    return [w for w in waivers if w.key in live]


def _print_report(evaluation: Evaluation, comparisons: List[SurfaceComparison], out=None) -> None:
    out = out or sys.stdout
    print(f'Active waivers ({len(evaluation.active_waivers)}):', file=out)
    for w in evaluation.active_waivers:
        expires = f', expires {w.expires.isoformat()}' if w.expires else ''
        issue = f', {w.issue}' if w.issue else ''
        print(f'  - {w.key}: {w.reason} [{w.owner}{issue}{expires}]', file=out)
    t = totals(comparisons)
    print(
        f'Compared {t["surfaces"]} surfaces, {t["params"]} python params: {t["exact"]} exact, '
        f'{t["camelCase"]} camelCase, {t["alias"]} alias, {t["flattened"]} flattened, '
        f'{t["missing"]} missing, {t["mismatches"]} mismatches, {t["waived"]} waived; '
        f'{t["ts_only"]} TS-only of {t["ts_total"]}.', file=out,
    )
    if evaluation.warnings:
        print(f'Warnings ({len(evaluation.warnings)}):', file=out)
        for w in evaluation.warnings:
            print(f'  - {w}', file=out)
    if evaluation.failures:
        print(f'FAILURES ({len(evaluation.failures)}):', file=out)
        for f in evaluation.failures:
            print(f'  - {f}', file=out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f'python -m {GENERATED_BY}',
        description='Signature-level Python <-> TypeScript parity checker.',
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='write SIGNATURE_PARITY.md and signature-parity.json')
    mode.add_argument('--check', action='store_true', help='fail on drift, gaps, or waiver problems (CI gate)')
    mode.add_argument('--diff', metavar='SURFACE', help='print one surface table to stdout')
    mode.add_argument('--baseline', action='store_true', help='add waivers for every current un-waived gap')
    mode.add_argument('--prune', action='store_true', help='delete waivers whose gap no longer exists (stale)')
    parser.add_argument('--repo-root', type=Path, default=None)
    parser.add_argument('--today', type=date.fromisoformat, default=None, help=argparse.SUPPRESS)
    return parser


# A source location is `path/to/file.ext:LINE`. Editing an unrelated part of a
# covered file shifts those line numbers without changing a single fact about
# parity, and comparing the reports byte for byte turned that into a red build
# on main -- the same "a number moved, nothing happened" noise this checker was
# built to remove. Staleness is judged on the report with line numbers masked;
# `--write` still records the real ones.
_SOURCE_LOCATION_RE = re.compile(r'(?P<path>[\w./-]+\.(?:py|ts|mjs|tsx)):(?P<line>\d+)')


def strip_source_lines(text: str) -> str:
    """The report with `file.ext:123` reduced to `file.ext`, for staleness checks."""
    return _SOURCE_LOCATION_RE.sub(lambda m: m.group('path'), text)


def classify_report_freshness(evaluation: 'Evaluation', path: Path, rel: Path, content: str) -> None:
    """Record how a committed generated report compares to the freshly rendered one.

    Missing is a failure: there is no baseline to compare against. Stale is a
    warning: update-parity-tracker.yml regenerates and commits this file on every
    push to main, so a pull request never has to carry it -- and while every branch
    regenerated the same file, every branch conflicted with every other one on it.
    The substantive checks still fail; only the freshness of a file main rewrites
    by itself is downgraded.
    """
    if not path.is_file():
        evaluation.failures.append(f'{rel} does not exist -- run --write and commit it')
    elif strip_source_lines(path.read_text(encoding='utf-8')) != strip_source_lines(content):
        evaluation.warnings.append(
            f'{rel} is out of date -- main regenerates it on push; '
            'run --write if you want it in this change'
        )


def _raise_on_rules_problems(problems: List[str]) -> None:
    """A dead or shadowed rule is a broken tool, not a parity gap: exit 2."""
    if problems:
        raise ToolingError(
            'rules.yaml has {n} entr{y} that can never fire:\n  - {items}'.format(
                n=len(problems), y='y' if len(problems) == 1 else 'ies',
                items='\n  - '.join(problems)))


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo_root = find_repo_root(args.repo_root)
        catalogue = load_surfaces()
        rules = load_rules()
        waivers = load_waivers()

        load_nested_config_defaults(rules, repo_root, catalogue.python_root)

        if args.diff:
            python, typescript = extract_all(repo_root, catalogue, keys=[args.diff])
            _raise_on_rules_problems(validate_rules(rules, python, typescript))
            comparison = compare_all(python, typescript, rules, keys=[args.diff])[0]
            evaluate([comparison], [w for w in waivers if w.key.startswith(args.diff + '.')], args.today)
            print(render_surface_markdown(comparison))
            return EXIT_OK

        python, typescript = extract_all(repo_root, catalogue)
        _raise_on_rules_problems(validate_rules(rules, python, typescript))
        comparisons = compare_all(python, typescript, rules, keys=[s.key for s in catalogue.surfaces])

        if args.baseline:
            before = len(waivers)
            waivers = baseline_waivers(comparisons, waivers)
            write_waivers(DEFAULT_WAIVERS_FILE, waivers)
            print(f'waivers.yaml: {len(waivers) - before} added, {len(waivers)} total -> {DEFAULT_WAIVERS_FILE}')
            return EXIT_OK

        if args.prune:
            before = len(waivers)
            waivers = prune_waivers(comparisons, waivers)
            write_waivers(DEFAULT_WAIVERS_FILE, waivers)
            print(f'waivers.yaml: {before - len(waivers)} stale removed, {len(waivers)} remain -> {DEFAULT_WAIVERS_FILE}')
            return EXIT_OK

        evaluation = evaluate(comparisons, waivers, args.today)
        md = render_markdown(comparisons, waivers)
        js = render_json(comparisons, waivers)
        md_path = repo_root / MD_OUTPUT
        json_path = repo_root / JSON_OUTPUT

        if args.write:
            md_path.write_text(md, encoding='utf-8')
            json_path.write_text(js, encoding='utf-8')
            print(f'wrote {MD_OUTPUT} and {JSON_OUTPUT}')
        else:
            for path, content in ((md_path, md), (json_path, js)):
                classify_report_freshness(evaluation, path, path.relative_to(repo_root), content)

        _print_report(evaluation, comparisons)
        if evaluation.ok:
            print('signature parity: OK')
            return EXIT_OK
        sys.stdout.flush()
        print('signature parity: FAILED', file=sys.stderr)
        return EXIT_PARITY
    except ToolingError as exc:
        sys.stdout.flush()
        print(f'signature parity: tooling error: {exc}', file=sys.stderr)
        return EXIT_TOOLING


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
