"""
Unit tests for the signature-level parity checker
(``praisonai._dev.parity.signatures``).

The comparator tests feed pre-extracted JSON fixtures straight into the
compare/evaluate functions, so they run without Node or TypeScript. Only the
``TestTsExtractor`` class shells out to ``node``.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from praisonai._dev.parity.signatures import compare as C
from praisonai._dev.parity.signatures.py_extract import (
    PythonSurfaceNotFound,
    extract_python_source,
    extract_python_surface,
    python_type_class,
)
from praisonai._dev.parity.signatures.schema import snake_to_camel, split_top_level

TODAY = date(2026, 9, 2)
SURFACE = 'Agent.__init__'
REPO_ROOT = Path(__file__).resolve().parents[5]
TS_EXTRACTOR = C.TS_EXTRACTOR


# ------------------------------------------------------------------ fixtures

def py_param(name, default=None, default_kind='literal', required=False, kind='positional',
             type_text='', type_class='unknown'):
    return {
        'name': name, 'canonical': snake_to_camel(name), 'kind': kind, 'required': required,
        'default': default, 'default_kind': None if required else default_kind,
        'type_text': type_text, 'type_class': type_class,
    }


def ts_param(name, default=None, default_kind=None, required=False, kind='property',
             type_text='', type_class='unknown'):
    return {
        'name': name, 'canonical': name, 'kind': kind, 'required': required,
        'default': default, 'default_kind': default_kind,
        'type_text': type_text, 'type_class': type_class,
    }


def sig(language, params, surface=SURFACE, extra=None):
    return {'surface': surface, 'language': language, 'location': f'{language}.src:1',
            'params': params, 'extra': extra or {}}


def flattening(fields, python_config=None, field_map=None):
    """A `rules.yaml` flattened entry: TS field names, optionally mapped to
    fields of the Python nested-config class those TS defaults must agree with."""
    return C.Flattening(fields=list(fields), python_config=python_config, field_map=field_map or {})


def default_rules(aliases=None, flattened=None, nested_defaults=None):
    return C.Rules(
        aliases={SURFACE: aliases or {}},
        flattened={SURFACE: {k: (v if isinstance(v, C.Flattening) else flattening(v))
                             for k, v in (flattened or {}).items()}},
        default_equivalences=[(None, 'undefined'), (False, 'undefined')],
        nested_defaults=nested_defaults or {},
    )


def waiver(key, reason='baseline', owner='praisonai-ts', expires=None, issue=None):
    return C.Waiver(key=key, reason=reason, owner=owner, expires=expires, issue=issue)


def run(py_items, ts_items, waivers=(), rules=None, today=TODAY):
    comparisons = C.compare_all(
        C.signatures_from_json(py_items), C.signatures_from_json(ts_items), rules or default_rules(),
    )
    evaluation = C.evaluate(comparisons, list(waivers), today)
    return comparisons, evaluation


BASE_PY = [py_param('name', type_class='string'), py_param('goal', type_class='string')]
BASE_TS = [ts_param('name', type_class='string'), ts_param('goal', type_class='string')]


def row(comparisons, name, surface=SURFACE):
    for c in comparisons:
        if c.key == surface:
            for r in c.rows:
                if r.python.name == name:
                    return r
    raise AssertionError(f'{surface}.{name} not in comparison')


# --------------------------------------------------------------------- gates

class TestGate:
    def test_no_drift_passes(self):
        _, ev = run([sig('python', BASE_PY)], [sig('typescript', BASE_TS)])
        assert ev.ok, ev.failures

    def test_extra_python_param_fails_and_names_param_and_surface(self):
        py = BASE_PY + [py_param('memory')]
        _, ev = run([sig('python', py)], [sig('typescript', BASE_TS)])
        assert not ev.ok
        assert len(ev.failures) == 1
        assert 'memory' in ev.failures[0]
        assert SURFACE in ev.failures[0]

    def test_waived_gap_passes_and_is_reported_active(self):
        py = BASE_PY + [py_param('memory')]
        _, ev = run([sig('python', py)], [sig('typescript', BASE_TS)], waivers=[waiver(f'{SURFACE}.memory')])
        assert ev.ok, ev.failures
        assert [w.key for w in ev.active_waivers] == [f'{SURFACE}.memory']

    def test_expired_waiver_fails(self):
        py = BASE_PY + [py_param('memory')]
        _, ev = run([sig('python', py)], [sig('typescript', BASE_TS)],
                    waivers=[waiver(f'{SURFACE}.memory', expires=date(2026, 1, 1))])
        assert not ev.ok
        assert 'expired' in ev.failures[0] and 'memory' in ev.failures[0] and SURFACE in ev.failures[0]
        assert ev.active_waivers == []

    def test_unexpired_waiver_passes(self):
        py = BASE_PY + [py_param('memory')]
        _, ev = run([sig('python', py)], [sig('typescript', BASE_TS)],
                    waivers=[waiver(f'{SURFACE}.memory', expires=date(2030, 1, 1))])
        assert ev.ok, ev.failures

    def test_stale_waiver_fails_with_delete_hint(self):
        _, ev = run([sig('python', BASE_PY)], [sig('typescript', BASE_TS)],
                    waivers=[waiver(f'{SURFACE}.memory')])
        assert not ev.ok
        assert 'stale' in ev.failures[0] and f'{SURFACE}.memory' in ev.failures[0]
        assert 'delete' in ev.failures[0]

    def test_zero_surfaces_fails(self):
        ev = C.evaluate([], [], TODAY)
        assert not ev.ok
        assert 'nothing was checked' in ev.failures[0]

    def test_one_surface_passes_control(self):
        _, ev = run([sig('python', BASE_PY)], [sig('typescript', BASE_TS)])
        assert ev.ok

    def test_zero_python_params_fails(self):
        _, ev = run([sig('python', [])], [sig('typescript', BASE_TS)])
        assert not ev.ok
        assert any('nothing was checked' in f and 'Python' in f for f in ev.failures)

    def test_zero_typescript_params_fails(self):
        _, ev = run([sig('python', BASE_PY)], [sig('typescript', [])])
        assert not ev.ok
        assert any('nothing was checked' in f and 'TypeScript' in f for f in ev.failures)

    def test_variadic_params_are_not_gaps(self):
        py = BASE_PY + [py_param('kwargs', kind='var_keyword', default_kind=None)]
        _, ev = run([sig('python', py)], [sig('typescript', BASE_TS)])
        assert ev.ok, ev.failures

    def test_waiver_requires_reason_and_owner(self):
        with pytest.raises(C.ToolingError):
            C.Waiver.from_dict('x.y', {'reason': 'r'})
        with pytest.raises(C.ToolingError):
            C.Waiver.from_dict('x.y', {'owner': 'o'})


# ------------------------------------------------------------- classification

class TestClassification:
    def test_exact(self):
        comps, _ = run([sig('python', BASE_PY)], [sig('typescript', BASE_TS)])
        assert row(comps, 'name').match == 'exact'

    def test_camel_case(self):
        py = [py_param('expected_output')]
        ts = [ts_param('expectedOutput')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert ev.ok
        assert row(comps, 'expected_output').match == 'camelCase'
        assert row(comps, 'expected_output').ts_name == 'expectedOutput'

    def test_alias_with_rule(self):
        py = [py_param('base_url')]
        ts = [ts_param('baseURL')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)],
                        rules=default_rules(aliases={'base_url': 'baseURL'}))
        assert ev.ok
        assert row(comps, 'base_url').match == 'alias'
        assert comps[0].ts_only == []

    def test_alias_without_rule_is_missing(self):
        py = [py_param('base_url')]
        ts = [ts_param('baseURL')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert not ev.ok
        assert row(comps, 'base_url').match == 'missing'
        assert [p.name for p in comps[0].ts_only] == ['baseURL']

    def test_flattened(self):
        py = [py_param('output')]
        ts = [ts_param('verbose'), ts_param('markdown'), ts_param('stream'), ts_param('other')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)],
                        rules=default_rules(flattened={'output': ['verbose', 'markdown', 'stream']}))
        assert ev.ok
        r = row(comps, 'output')
        assert r.match == 'flattened'
        assert r.ts_names == ['verbose', 'markdown', 'stream']
        assert [p.name for p in comps[0].ts_only] == ['other']

    def test_flattened_requires_all_fields(self):
        py = [py_param('output')]
        ts = [ts_param('verbose'), ts_param('markdown')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)],
                        rules=default_rules(flattened={'output': ['verbose', 'markdown', 'stream']}))
        assert not ev.ok
        assert row(comps, 'output').match == 'missing'

    def test_counts(self):
        py = [py_param('name'), py_param('expected_output'), py_param('base_url'), py_param('gone')]
        ts = [ts_param('name'), ts_param('expectedOutput'), ts_param('baseURL'), ts_param('extra')]
        comps, _ = run([sig('python', py)], [sig('typescript', ts)],
                       rules=default_rules(aliases={'base_url': 'baseURL'}))
        counts = comps[0].counts()
        assert counts == {
            'params': 4, 'exact': 1, 'camelCase': 1, 'alias': 1, 'flattened': 0, 'missing': 1,
            'mismatches': 0, 'waived': 0, 'ts_only': 1, 'ts_total': 4,
        }


# ------------------------------------------------------------------ defaults

class TestDefaultsAndRequired:
    def test_none_vs_false_is_a_default_mismatch(self):
        py = [py_param('cache', default=None)]
        ts = [ts_param('cache', default=False, default_kind='literal')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert not ev.ok
        assert row(comps, 'cache').gap.kind == 'default'
        assert 'cache' in ev.failures[0] and SURFACE in ev.failures[0]

    def test_none_vs_undefined_is_equivalent(self):
        py = [py_param('cache', default=None)]
        ts = [ts_param('cache')]  # no ctor default -> undefined
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert ev.ok, ev.failures
        assert row(comps, 'cache').gap is None

    def test_true_vs_true_is_equivalent(self):
        py = [py_param('markdown', default=True)]
        ts = [ts_param('markdown', default=True, default_kind='literal')]
        _, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert ev.ok, ev.failures

    def test_equal_string_literal_ok_and_different_string_flagged(self):
        py = [py_param('process', default='sequential')]
        ok_ts = [ts_param('process', default='sequential', default_kind='literal')]
        _, ev = run([sig('python', py)], [sig('typescript', ok_ts)])
        assert ev.ok
        bad_ts = [ts_param('process', default='parallel', default_kind='literal')]
        comps, ev = run([sig('python', py)], [sig('typescript', bad_ts)])
        assert not ev.ok and row(comps, 'process').gap.kind == 'default'

    def test_expr_default_vs_literal_is_a_mismatch(self):
        py = [py_param('name', default=None)]
        ts = [ts_param('name', default='`Agent_${rand()}`', default_kind='expr')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert not ev.ok and row(comps, 'name').gap.kind == 'default'

    def test_required_mismatch_detected(self):
        py = [py_param('prompt', required=True)]
        ts = [ts_param('prompt', required=False)]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert not ev.ok
        assert row(comps, 'prompt').gap.kind == 'required'
        assert 'prompt' in ev.failures[0]

    def test_both_required_passes(self):
        py = [py_param('prompt', required=True)]
        ts = [ts_param('prompt', required=True)]
        _, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert ev.ok

    def test_waived_default_mismatch_passes(self):
        py = [py_param('cache', default=None)]
        ts = [ts_param('cache', default=False, default_kind='literal')]
        _, ev = run([sig('python', py)], [sig('typescript', ts)], waivers=[waiver(f'{SURFACE}.cache')])
        assert ev.ok

    def test_python_sentinel_expr_matches_typescript_undefined(self):
        """`_UNSET` and `undefined` are the same "caller passed nothing" marker.

        Python spells the marker as a module-level object because `None` is a
        legal value for the parameter; TypeScript has a native one. Both sides
        then resolve the same value, so this is not a gap.
        """
        rules = C.Rules(
            aliases={SURFACE: {}}, flattened={SURFACE: {}},
            default_equivalences=[(None, 'undefined')],
            default_expr_equivalences=[('_UNSET', 'undefined')],
        )
        py = [py_param('requires_approval', default='_UNSET', default_kind='expr')]
        ts = [ts_param('requiresApproval')]  # no ctor default -> undefined
        comps, ev = run([sig('python', py)], [sig('typescript', ts)], rules=rules)
        assert ev.ok, ev.failures
        assert row(comps, 'requires_approval').gap is None

    def test_control_unlisted_sentinel_expr_is_still_a_mismatch(self):
        """Only the sentinels named in rules.yaml are equivalent to undefined."""
        rules = C.Rules(
            aliases={SURFACE: {}}, flattened={SURFACE: {}},
            default_equivalences=[(None, 'undefined')],
            default_expr_equivalences=[('_UNSET', 'undefined')],
        )
        py = [py_param('requires_approval', default='compute_default()', default_kind='expr')]
        ts = [ts_param('requiresApproval')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)], rules=rules)
        assert not ev.ok
        assert row(comps, 'requires_approval').gap.kind == 'default'

    def test_control_sentinel_expr_does_not_match_a_literal_of_the_same_spelling(self):
        """An expression default and a string literal are different things."""
        rules = C.Rules(
            aliases={SURFACE: {}}, flattened={SURFACE: {}},
            default_equivalences=[(None, 'undefined')],
            default_expr_equivalences=[('_UNSET', 'undefined')],
        )
        py = [py_param('requires_approval', default='_UNSET', default_kind='literal')]
        ts = [ts_param('requiresApproval')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)], rules=rules)
        assert not ev.ok
        assert row(comps, 'requires_approval').gap.kind == 'default'

    def test_type_class_mismatch_is_a_warning_not_a_failure(self):
        py = [py_param('timeout', default=30, type_class='number')]
        ts = [ts_param('timeout', default=30, default_kind='literal', type_class='string')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert ev.ok
        assert row(comps, 'timeout').warnings
        assert ev.warnings and 'timeout' in ev.warnings[0]


# ----------------------------------------------------------------- rendering

class TestRendering:
    def _comps(self):
        py = BASE_PY + [py_param('memory'), py_param('expected_output')]
        ts = BASE_TS + [ts_param('expectedOutput'), ts_param('verbose')]
        return run([sig('python', py)], [sig('typescript', ts)], waivers=[waiver(f'{SURFACE}.memory')])

    def test_markdown_is_deterministic_and_names_things(self):
        comps, ev = self._comps()
        md1 = C.render_markdown(comps, ev.active_waivers)
        md2 = C.render_markdown(comps, ev.active_waivers)
        assert md1 == md2
        assert f'`{SURFACE}`' in md1
        assert '`memory`' in md1 and 'MISSING (waived)' in md1
        assert 'camelCase' in md1
        assert 'TS-only members: `verbose`?' in md1
        assert '## Active waivers' in md1 and f'`{SURFACE}.memory`' in md1
        assert '## What this measures' in md1

    def test_json_is_sorted_and_round_trips(self):
        comps, ev = self._comps()
        text = C.render_json(comps, ev.active_waivers)
        doc = json.loads(text)
        assert list(doc) == sorted(doc)
        assert doc['totals']['surfaces'] == 1
        assert doc['surfaces'][SURFACE]['counts']['waived'] == 1
        params = {p['name']: p for p in doc['surfaces'][SURFACE]['params']}
        assert params['memory']['waived'] == f'{SURFACE}.memory'
        assert params['expected_output']['match'] == 'camelCase'
        assert C.render_json(comps, ev.active_waivers) == text

    def test_baseline_adds_without_overwriting(self):
        comps, _ = self._comps()
        existing = [waiver(f'{SURFACE}.memory', reason='keep me', owner='me')]
        merged = C.baseline_waivers(comps, existing)
        assert [w.key for w in merged] == [f'{SURFACE}.memory']
        assert merged[0].reason == 'keep me'
        merged = C.baseline_waivers(comps, [])
        assert merged[0].reason == C.BASELINE_REASON and merged[0].owner == C.BASELINE_OWNER

    def test_write_and_load_waivers_round_trip(self, tmp_path):
        path = tmp_path / 'waivers.yaml'
        C.write_waivers(path, [waiver('A.b', expires=date(2030, 1, 1), issue='#1')])
        loaded = C.load_waivers(path)
        assert loaded[0].key == 'A.b' and loaded[0].expires == date(2030, 1, 1) and loaded[0].issue == '#1'
        assert C.load_waivers(tmp_path / 'missing.yaml') == []


# ---------------------------------------------------------- python extractor

FIXTURE = '''
from typing import Any, Callable, Dict, List, Optional, Union

class Team:
    def __init__(self, agents, tasks=None):
        pass

class Widget:
    def __init__(
        self,
        name: str,
        count: int = 3,
        *args,
        label: Optional[str] = None,
        hook: Callable[[int], None] = None,
        items: List[str] = [],
        mode: Union[str, int] = "fast",
        raw: Any = _SENTINEL,
        **kwargs,
    ):
        pass

    def start(self, prompt=None):
        pass

def start(a, b=1):
    pass
'''


class TestPythonExtractor:
    def test_kinds_required_defaults_and_types(self):
        sig_ = extract_python_source(FIXTURE, '__init__', class_name='Widget', surface='Widget.__init__')
        params = {p.name: p for p in sig_.params}
        assert 'self' not in params
        assert list(params) == ['name', 'count', 'args', 'label', 'hook', 'items', 'mode', 'raw', 'kwargs']
        assert params['name'].kind == 'positional' and params['name'].required
        assert params['name'].type_class == 'string'
        assert params['count'].default == 3 and params['count'].default_kind == 'literal'
        assert params['count'].type_class == 'number'
        assert params['args'].kind == 'var_positional' and not params['args'].required
        assert params['label'].kind == 'keyword' and params['label'].default is None
        assert params['label'].default_kind == 'literal' and params['label'].type_class == 'string'
        assert params['label'].canonical == 'label'
        assert params['hook'].type_class == 'callable'
        assert params['items'].default == [] and params['items'].type_class == 'array'
        assert params['mode'].default == 'fast' and params['mode'].type_class == 'union'
        assert params['raw'].default == '_SENTINEL' and params['raw'].default_kind == 'expr'
        assert params['raw'].type_class == 'unknown'
        assert params['kwargs'].kind == 'var_keyword'
        assert sig_.location.endswith(':9')
        assert sig_.extra['resolved_class'] == 'Widget'

    def test_canonical_is_camel_case(self):
        src = 'def f(expected_output=None, _private_name=1): pass'
        params = extract_python_source(src, 'f').params
        assert params[0].canonical == 'expectedOutput'
        assert params[1].canonical == '_privateName'

    def test_class_scoped_vs_module_level_lookup(self):
        method = extract_python_source(FIXTURE, 'start', class_name='Widget')
        assert [p.name for p in method.params] == ['prompt']
        module_fn = extract_python_source(FIXTURE, 'start')
        # Without a class the first definition in source order wins (Widget.start comes first here).
        assert module_fn.extra.get('resolved_class') == 'Widget'

    def test_missing_function_raises(self):
        with pytest.raises(PythonSurfaceNotFound):
            extract_python_source(FIXTURE, 'nope', class_name='Widget')

    def test_extract_from_file_with_discovery(self, tmp_path):
        root = tmp_path / 'src' / 'praisonai-agents' / 'praisonaiagents' / 'agents'
        root.mkdir(parents=True)
        (root / 'agents.py').write_text(FIXTURE)
        sig_ = extract_python_surface(
            tmp_path, 'AgentTeam.__init__',
            {'file': 'agents/agents.py', 'function': '__init__', 'discover': {'init_first_param': 'agents'},
             'aliases': ['PraisonAIAgents']},
        )
        assert sig_.extra['resolved_class'] == 'Team'
        assert sig_.extra['aliases'] == ['PraisonAIAgents']
        assert [p.name for p in sig_.params] == ['agents', 'tasks']
        assert sig_.location == 'src/praisonai-agents/praisonaiagents/agents/agents.py:5'
        with pytest.raises(PythonSurfaceNotFound):
            extract_python_surface(tmp_path, 'x', {'file': 'agents/agents.py', 'function': '__init__',
                                                   'discover': {'init_first_param': 'nothing'}})
        with pytest.raises(PythonSurfaceNotFound):
            extract_python_surface(tmp_path, 'x', {'file': 'agents/missing.py', 'function': '__init__'})

    @pytest.mark.parametrize('annotation,expected', [
        ('str', 'string'), ('Optional[str]', 'string'), ('int', 'number'), ('float', 'number'),
        ('bool', 'boolean'), ('Optional[bool]', 'boolean'), ('Dict[str, Any]', 'object'),
        ('Optional[Dict[str, Any]]', 'object'), ('List[str]', 'array'), ('list', 'array'),
        ('Callable[[int], None]', 'callable'), ('Optional[Callable]', 'callable'),
        ('Union[str, int]', 'union'), ('str | int | None', 'union'), ('Union[str, None]', 'string'),
        ('Any', 'unknown'), ('', 'unknown'), ('Agent', 'object'), ("'Agent'", 'object'),
        ('Literal["a", "b"]', 'string'), ('Optional[Union[bool, str]]', 'union'),
        ('typing.Optional[str]', 'string'),
    ])
    def test_python_type_class(self, annotation, expected):
        assert python_type_class(annotation) == expected

    def test_split_top_level(self):
        assert split_top_level('Dict[str, Any] | List[int]', '|') == ['Dict[str, Any] ', ' List[int]']
        assert split_top_level("'a|b' | int", '|') == ["'a|b' ", ' int']


# -------------------------------------------------------------- ts extractor

def _typescript_resolvable():
    """Return True when ts_extract.mjs will find the typescript module."""
    override = os.environ.get('PARITY_TS_NODE_MODULES')
    if override:
        return (Path(override) / 'typescript' / 'package.json').is_file()
    if (REPO_ROOT / 'src' / 'praisonai-ts' / 'node_modules' / 'typescript' / 'package.json').is_file():
        return True
    if shutil.which('node') is None:
        return False
    probe = subprocess.run(['node', '-e', "require('typescript')"], capture_output=True, text=True,
                           cwd=str(TS_EXTRACTOR.parent))
    return probe.returncode == 0


class TestTsExtractor:
    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES or pnpm install in src/praisonai-ts)')
    def test_extracts_real_surfaces(self):
        targets = [
            {'surface': 'Agent.__init__', 'file': 'agent/simple.ts', 'kind': 'interface',
             'name': 'SimpleAgentConfig', 'ctorClass': 'Agent'},
            {'surface': 'Agent.start', 'file': 'agent/simple.ts', 'kind': 'method', 'name': 'start', 'cls': 'Agent'},
        ]
        items = C.run_ts_extractor(REPO_ROOT, targets)
        by_key = {i['surface']: i for i in items}
        assert set(by_key) == {'Agent.__init__', 'Agent.start'}
        cfg = by_key['Agent.__init__']
        assert cfg['language'] == 'typescript'
        assert cfg['location'].startswith('src/praisonai-ts/src/agent/simple.ts:')
        assert 'ctor_location' in cfg['extra']
        params = {p['name']: p for p in cfg['params']}
        assert params['name']['kind'] == 'property' and params['name']['canonical'] == 'name'
        assert params['markdown']['default'] is True and params['markdown']['default_kind'] == 'literal'
        assert params['markdown']['type_class'] == 'boolean'
        assert params['tools']['type_class'] == 'array'
        start = {p['name']: p for p in by_key['Agent.start']['params']}
        # `prompt` is optional on both sides: Python's `start(prompt=None)`
        # falls back to the agent's instructions, and TypeScript now does too.
        assert start['prompt']['required'] is False and start['prompt']['type_class'] == 'string'
        assert start['onToken']['required'] is False and start['onToken']['type_class'] == 'callable'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    def test_missing_typescript_exits_2_with_message(self, tmp_path):
        empty_modules = tmp_path / 'node_modules'
        empty_modules.mkdir()
        fake_repo = tmp_path / 'repo'
        (fake_repo / 'src').mkdir(parents=True)
        env = dict(os.environ, PARITY_TS_NODE_MODULES=str(empty_modules))
        proc = subprocess.run(
            ['node', str(TS_EXTRACTOR), '--repo-root', str(fake_repo), '--targets', '[]'],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 2
        assert proc.stderr.strip()
        assert 'typescript' in proc.stderr
        assert proc.stdout.strip() == ''

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    def test_run_ts_extractor_raises_tooling_error(self, tmp_path, monkeypatch):
        empty_modules = tmp_path / 'node_modules'
        empty_modules.mkdir()
        monkeypatch.setenv('PARITY_TS_NODE_MODULES', str(empty_modules))
        with pytest.raises(C.ToolingError):
            C.run_ts_extractor(REPO_ROOT, [])


# ----------------------------------------------------------------------- CLI

class TestCli:
    def test_unknown_surface_exits_2(self, capsys):
        code = C.main(['--diff', 'Nope.nothing', '--repo-root', str(REPO_ROOT)])
        assert code == C.EXIT_TOOLING
        assert 'Nope.nothing' in capsys.readouterr().err

    def test_bad_repo_root_exits_2(self, tmp_path, capsys):
        code = C.main(['--check', '--repo-root', str(tmp_path)])
        assert code == C.EXIT_TOOLING
        assert 'repo-root' in capsys.readouterr().err

    def test_config_files_load(self):
        catalogue = C.load_surfaces()
        # A minimum, not an exact count: surface.yaml grows as surfaces are curated.
        assert len(catalogue.surfaces) >= 10
        assert {s.key for s in catalogue.surfaces} >= {'Agent.__init__', 'AgentTeam.__init__', 'tool()'}
        assert len({s.key for s in catalogue.surfaces}) == len(catalogue.surfaces), 'duplicate surface keys'
        rules = C.load_rules()
        assert rules.aliases['Agent.__init__']['base_url'] == 'baseURL'
        assert rules.flattened['Agent.__init__']['output'].fields == ['verbose', 'markdown', 'stream']
        assert (None, 'undefined') in rules.default_equivalences
        # NOTE: this test asserts only that the YAML says what the YAML says,
        # which is why eight dead entries survived in it. The check with teeth
        # is TestRulesSelfTest, which runs `validate_rules` against a real
        # extraction.
        for w in C.load_waivers():
            assert w.reason and w.owner


class TestOptionsObjectFlattening:
    """A method's `options?: FooOptions` parameter counts its members as parameters."""

    FIXTURE = '''
export interface ChatOptions {
  temperature?: number;
  reasoningSteps?: boolean;
  seed?: number;
}
export class Agent {
  async chat(prompt: string, signal?: AbortSignal, options?: ChatOptions): Promise<string> {
    const steps = options?.reasoningSteps ?? false;
    const temp = options.temperature ?? 0.7;
    return prompt + String(steps) + String(temp) + String(signal);
  }
  plain(prompt: string): string { return prompt; }
}
'''

    @staticmethod
    def _fake_repo(tmp_path):
        src = tmp_path / 'src' / 'praisonai-ts' / 'src' / 'agent'
        src.mkdir(parents=True)
        (src / 'simple.ts').write_text(TestOptionsObjectFlattening.FIXTURE)
        return tmp_path

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_options_members_become_params_with_defaults(self, tmp_path):
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [
            {'surface': 'Agent.chat', 'file': 'agent/simple.ts', 'kind': 'method', 'name': 'chat', 'cls': 'Agent'},
        ])
        params = {p['name']: p for p in items[0]['params']}
        assert set(params) == {'prompt', 'signal', 'options', 'temperature', 'reasoningSteps', 'seed'}
        assert params['reasoningSteps']['default'] is False and params['reasoningSteps']['via'] == 'options'
        assert params['temperature']['default'] == 0.7
        assert params['seed']['default'] is None and params['seed']['required'] is False
        assert items[0]['extra']['options_interfaces'] == ['options: ChatOptions']

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_method_without_options_is_not_flattened(self, tmp_path):
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [
            {'surface': 'Agent.plain', 'file': 'agent/simple.ts', 'kind': 'method', 'name': 'plain', 'cls': 'Agent'},
        ])
        assert [p['name'] for p in items[0]['params']] == ['prompt']
        assert 'options_interfaces' not in items[0]['extra']


class TestPositionalConstructorParams:
    """A constructor's positional parameters are reported alongside the flattened options."""

    FIXTURE = """
export interface ErrOptions {
  agentId?: string;
  runId?: string;
}
export class PraisonAIError extends Error {
  constructor(message: string, options: ErrOptions = {}) {
    super(message);
    const a = options.agentId ?? 'unknown';
    void a;
  }
}
export interface DetectorOptions { threshold?: number; }
export class Detector {
  constructor(config: DetectorOptions | null = null) {
    const t = config?.threshold ?? 3;
    void t;
  }
}
"""

    @staticmethod
    def _fake_repo(tmp_path):
        src = tmp_path / 'src' / 'praisonai-ts' / 'src'
        src.mkdir(parents=True)
        (src / 'errors.ts').write_text(TestPositionalConstructorParams.FIXTURE)
        return tmp_path

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_positional_param_is_reported_and_options_still_flattened(self, tmp_path):
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [
            {'surface': 'PraisonAIError.__init__', 'file': 'errors.ts', 'kind': 'interface',
             'name': 'ErrOptions', 'ctorClass': 'PraisonAIError'},
        ])
        params = {p['name']: p for p in items[0]['params']}
        # The positional `message` is reported, and so are the flattened options members.
        assert 'message' in params
        assert params['message']['kind'] == 'positional' and params['message']['required'] is True
        assert {'agentId', 'runId'} <= set(params)
        assert params['agentId']['default'] == 'unknown'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_options_parameter_is_also_reported_under_its_own_name(self, tmp_path):
        """A Python parameter literally named `config` matches the TS options parameter."""
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [
            {'surface': 'Detector.__init__', 'file': 'errors.ts', 'kind': 'interface',
             'name': 'DetectorOptions', 'ctorClass': 'Detector'},
        ])
        params = {p['name']: p for p in items[0]['params']}
        assert 'config' in params, 'the options parameter should be reported by name'
        assert params['config']['required'] is False
        # Control: its members are still flattened, so both spellings resolve.
        assert 'threshold' in params and params['threshold']['default'] == 3


class TestBareConstructorAsMethod:
    """`kind: method, name: constructor` addresses a class's constructor declaration.

    Ported classes whose constructor takes plain positional parameters and no
    options interface (FileTracker, Knowledge) are only checkable this way.
    """

    FIXTURE = """
export interface TrackerOptions {
  retries?: number;
}
export class Tracker {
  constructor(a: string, b: number = 3) {
    void a;
    void b;
  }
  scan(target: string, deep: boolean = false): number {
    void target;
    return deep ? 1 : 0;
  }
}
export class Configured {
  constructor(label: string, options: TrackerOptions = {}) {
    const r = options.retries ?? 5;
    void label;
    void r;
  }
}
export class Bare {
  private x = 1;
  ping(): number { return this.x; }
}
export interface RunOptions {
  deep?: boolean;
}
export type RunOptionsInput = RunOptions | { shallow?: boolean };
export class Overloaded {
  run(target?: string, options?: RunOptions): number;
  run(target?: string, options?: RunOptionsInput): number {
    void target;
    void options;
    return 1;
  }
}
"""

    @staticmethod
    def _fake_repo(tmp_path):
        src = tmp_path / 'src' / 'praisonai-ts' / 'src'
        src.mkdir(parents=True)
        (src / 'tracker.ts').write_text(TestBareConstructorAsMethod.FIXTURE)
        return tmp_path

    @staticmethod
    def _target(surface, name, cls):
        return {'surface': surface, 'file': 'tracker.ts', 'kind': 'method', 'name': name, 'cls': cls}

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_constructor_params_are_reported_with_defaults_and_requiredness(self, tmp_path):
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [self._target('Tracker.__init__', 'constructor', 'Tracker')])
        assert [p['name'] for p in items[0]['params']] == ['a', 'b']
        params = {p['name']: p for p in items[0]['params']}
        assert params['a']['required'] is True
        assert params['a']['default'] is None and params['a']['default_kind'] is None
        assert params['a']['kind'] == 'positional' and params['a']['type_class'] == 'string'
        assert params['b']['required'] is False
        assert params['b']['default'] == 3 and params['b']['default_kind'] == 'literal'
        assert params['b']['type_class'] == 'number'
        assert items[0]['extra']['resolved_class'] == 'Tracker'
        assert items[0]['location'].endswith('/tracker.ts:6')  # the constructor line

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_constructor_options_object_is_still_flattened(self, tmp_path):
        """A constructor addressed this way keeps the options-interface flattening."""
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [self._target('Configured.__init__', 'constructor', 'Configured')])
        params = {p['name']: p for p in items[0]['params']}
        assert set(params) == {'label', 'options', 'retries'}
        assert params['label']['required'] is True
        assert params['retries']['default'] == 5 and params['retries']['via'] == 'options'
        assert items[0]['extra']['options_interfaces'] == ['options: TrackerOptions']

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_class_without_constructor_is_a_loud_error(self, tmp_path):
        """Control: a missing constructor must fail the extraction, not report zero params."""
        repo = self._fake_repo(tmp_path)
        with pytest.raises(C.ToolingError) as excinfo:
            C.run_ts_extractor(repo, [self._target('Bare.__init__', 'constructor', 'Bare')])
        message = str(excinfo.value)
        assert 'Bare.__init__' in message and 'Bare' in message and 'constructor' in message

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_missing_class_is_named_in_the_error(self, tmp_path):
        repo = self._fake_repo(tmp_path)
        with pytest.raises(C.ToolingError) as excinfo:
            C.run_ts_extractor(repo, [self._target('Nope.__init__', 'constructor', 'Nope')])
        assert 'class Nope not found' in str(excinfo.value)

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_ordinary_method_is_unchanged(self, tmp_path):
        """Control: `kind: method` on a named method behaves exactly as before."""
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [self._target('Tracker.scan', 'scan', 'Tracker')])
        params = {p['name']: p for p in items[0]['params']}
        assert [p['name'] for p in items[0]['params']] == ['target', 'deep']
        assert params['target']['required'] is True and params['target']['type_class'] == 'string'
        assert params['deep']['required'] is False and params['deep']['default'] is False
        assert items[0]['extra']['resolved_class'] == 'Tracker'
        assert 'options_interfaces' not in items[0]['extra']

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_overloaded_method_still_reads_its_first_overload(self, tmp_path):
        """Control: an overloaded method keeps reporting its leading (public) signature.

        This is the shape of the real `AgentTeam.start`: the documented overload
        names an interface that flattens, while the implementation widens to a
        union type alias with nothing to flatten. Preferring the implementation
        would silently drop `deep` and report a false parity gap.
        """
        repo = self._fake_repo(tmp_path)
        items = C.run_ts_extractor(repo, [self._target('Overloaded.run', 'run', 'Overloaded')])
        params = {p['name']: p for p in items[0]['params']}
        assert set(params) == {'target', 'options', 'deep'}
        assert params['options']['type_text'] == 'RunOptions'
        assert params['deep']['via'] == 'options'
        assert items[0]['extra']['options_interfaces'] == ['options: RunOptions']


class TestStalenessIgnoresLineNumbers:
    """A pure line-number shift is not staleness; a content change still is."""

    REPORT = (
        "# Signature Parity\n\n"
        "### `Agent.__init__`\n\n"
        "- Python: `src/praisonai-agents/praisonaiagents/agent/agent.py:583`\n"
        "- TypeScript: `src/praisonai-ts/src/agent/simple.ts:116`\n"
        "| `name` | positional | null | exact |\n"
    )

    def test_line_shift_is_not_staleness(self):
        shifted = self.REPORT.replace('agent.py:583', 'agent.py:603').replace('simple.ts:116', 'simple.ts:141')
        assert shifted != self.REPORT
        assert C.strip_source_lines(shifted) == C.strip_source_lines(self.REPORT)

    def test_content_change_is_still_staleness(self):
        """Control: masking line numbers must not hide a real difference."""
        changed = self.REPORT.replace('| `name` |', '| `renamed` |')
        assert C.strip_source_lines(changed) != C.strip_source_lines(self.REPORT)

    def test_a_changed_path_is_still_staleness(self):
        """Control: the file a surface points at is content, not a line number."""
        moved = self.REPORT.replace('agent/simple.ts:116', 'agent/team.ts:116')
        assert C.strip_source_lines(moved) != C.strip_source_lines(self.REPORT)

    def test_masking_only_touches_source_locations(self):
        """Control: a bare number in prose is left alone."""
        text = 'Compared 15 surfaces, 219 python params: 121 exact'
        assert C.strip_source_lines(text) == text


class TestWaiverScopeByGapKind:
    """A waiver is keyed by parameter, so it must not silence every KIND of gap.

    Found by making `verbose`, `markdown` and `stream` required behind the
    `Agent.__init__.output` waiver, which covers their DEFAULTS: the gate stayed
    green over a change that stops `new Agent({ name: 'x' })` compiling.
    Required-ness is therefore never covered implicitly.
    """

    @staticmethod
    def _waiver(**kw):
        return C.Waiver(key=SURFACE + '.name', reason='r', owner='o', **kw)

    def test_a_default_waiver_does_not_cover_a_required_gap(self):
        assert self._waiver().covers('default') is True
        assert self._waiver().covers('required') is False

    def test_naming_required_covers_it(self):
        """Control: a waiver may still cover required-ness when it says so."""
        assert self._waiver(kinds=['required']).covers('required') is True

    def test_naming_kinds_excludes_the_others(self):
        """Control: an explicit list is exhaustive, not additive."""
        w = self._waiver(kinds=['required'])
        assert w.covers('default') is False and w.covers('missing') is False

    def test_kinds_survives_a_write_read_round_trip(self, tmp_path):
        path = tmp_path / 'waivers.yaml'
        C.write_waivers(path, [self._waiver(kinds=['required'])])
        assert C.load_waivers(path)[0].kinds == ['required']

    def test_a_malformed_kinds_is_a_tooling_error(self):
        """Control: a typo must fail loudly, not silently waive nothing."""
        with pytest.raises(C.ToolingError, match='kinds'):
            C.Waiver.from_dict('S.p', {'reason': 'r', 'owner': 'o', 'kinds': 'required'})


class TestPruneWaivers:
    def _comparison_with_gap(self, gap_name='auth'):
        py = C.signatures_from_json([sig('python', [py_param(gap_name), py_param('name')])])[SURFACE]
        ts = C.signatures_from_json([sig('typescript', [ts_param('name')])])[SURFACE]
        return C.compare_surface(py, ts, default_rules())

    def test_prune_drops_only_stale_waivers(self):
        comparison = self._comparison_with_gap()
        live = waiver('Agent.__init__.auth')
        stale = waiver('Agent.__init__.ported')
        kept = C.prune_waivers([comparison], [live, stale])
        assert [w.key for w in kept] == ['Agent.__init__.auth']

    def test_control_prune_keeps_everything_when_nothing_is_stale(self):
        comparison = self._comparison_with_gap()
        live = waiver('Agent.__init__.auth')
        assert [w.key for w in C.prune_waivers([comparison], [live])] == ['Agent.__init__.auth']


# --------------------------------------------------- flattened parameters (D1)

class TestFlattenedGapDetection:
    """
    A `flattened` match sets `ts_names` and leaves `ts` None, and
    `compare_surface` used to run gap detection only `if row.ts is not None`.
    The required-ness and defaults of the TS fields a flattening names were
    therefore never compared at all.

    Reproduced on the real repository: deleting three `?` in `SimpleAgentConfig`
    to make `verbose`, `markdown` and `stream` REQUIRED -- which stops
    `new Agent({ name: 'x' })` compiling for every user -- passed `--check`,
    the names gate, the behaviour gate and all 142 tests, with a byte-identical
    report.
    """

    PY = [py_param('output', default=None)]
    FIELDS = ['verbose', 'markdown', 'stream']
    NESTED = {
        'praisonaiagents:OutputConfig': {
            name: C.Param(name=name, canonical=name, kind='keyword', required=False,
                          default=False, default_kind='literal')
            for name in FIELDS
        }
    }

    def _rules(self, mapped=True):
        flat = flattening(
            self.FIELDS,
            python_config='praisonaiagents:OutputConfig' if mapped else None,
            field_map={f: f for f in self.FIELDS} if mapped else None,
        )
        return default_rules(flattened={'output': flat},
                             nested_defaults=self.NESTED if mapped else None)

    def _ts(self, **overrides):
        out = []
        for name in self.FIELDS:
            kwargs = {'default': False, 'default_kind': 'literal'}
            kwargs.update(overrides.get(name, {}))
            out.append(ts_param(name, **kwargs))
        return out

    def test_control_all_optional_with_matching_defaults_passes(self):
        comps, ev = run([sig('python', self.PY)], [sig('typescript', self._ts())],
                        rules=self._rules())
        assert ev.ok, ev.failures
        assert row(comps, 'output').match == 'flattened'
        assert [p.name for p in row(comps, 'output').ts_members] == self.FIELDS

    def test_a_required_flattened_member_is_a_gap(self):
        """The headline defect: `verbose: boolean` instead of `verbose?: boolean`."""
        ts = self._ts(verbose={'required': True, 'default': None, 'default_kind': None})
        comps, ev = run([sig('python', self.PY)], [sig('typescript', ts)], rules=self._rules())
        assert not ev.ok
        gap = row(comps, 'output').gap
        assert gap is not None and gap.kind == 'required'
        assert 'verbose' in gap.detail and 'required in TypeScript' in gap.detail
        assert any('output' in f and 'verbose' in f for f in ev.failures)

    def test_every_required_member_is_named_not_just_the_first(self):
        ts = self._ts(**{n: {'required': True, 'default': None, 'default_kind': None}
                         for n in self.FIELDS})
        comps, ev = run([sig('python', self.PY)], [sig('typescript', ts)], rules=self._rules())
        assert not ev.ok
        detail = row(comps, 'output').gap.detail
        for name in self.FIELDS:
            assert f'`{name}`' in detail

    def test_member_default_is_compared_against_the_nested_config_field(self):
        """`Agent(output=None)` resolves to `OutputConfig()`, so its field
        defaults -- not the parameter's own `None` -- are the Python side."""
        ts = self._ts(markdown={'default': True, 'default_kind': 'literal'},
                      stream={'default': True, 'default_kind': 'literal'})
        comps, ev = run([sig('python', self.PY)], [sig('typescript', ts)], rules=self._rules())
        assert not ev.ok
        gap = row(comps, 'output').gap
        assert gap.kind == 'default'
        assert '`markdown` default differs' in gap.detail
        assert '`stream` default differs' in gap.detail
        # `verbose` agrees with OutputConfig.verbose, so only the field list mentions it.
        assert '`verbose` default differs' not in gap.detail

    def test_field_with_no_python_counterpart_is_checked_for_requiredness_only(self):
        """`cacheTTL` has no field on `CachingConfig`: nothing to compare a
        default against, but a required one is still a gap."""
        rules = default_rules(
            flattened={'caching': flattening(['cache', 'cacheTTL'],
                                             python_config='praisonaiagents:CachingConfig',
                                             field_map={'cache': 'enabled', 'cacheTTL': None})},
            nested_defaults={'praisonaiagents:CachingConfig': {
                'enabled': C.Param(name='enabled', canonical='enabled', kind='keyword',
                                   required=False, default=False, default_kind='literal')}},
        )
        py = [py_param('caching', default=None)]
        ok_ts = [ts_param('cache', default=False, default_kind='literal'),
                 ts_param('cacheTTL', default=3600, default_kind='literal')]
        _, ev = run([sig('python', py)], [sig('typescript', ok_ts)], rules=rules)
        assert ev.ok, ev.failures
        bad_ts = [ts_param('cache', default=False, default_kind='literal'),
                  ts_param('cacheTTL', required=True)]
        comps, ev = run([sig('python', py)], [sig('typescript', bad_ts)], rules=rules)
        assert not ev.ok and row(comps, 'caching').gap.kind == 'required'
        assert 'cacheTTL' in row(comps, 'caching').gap.detail

    def test_a_flattened_gap_is_waivable_under_the_python_parameter_name(self):
        ts = self._ts(markdown={'default': True, 'default_kind': 'literal'})
        _, ev = run([sig('python', self.PY)], [sig('typescript', ts)], rules=self._rules(),
                    waivers=[waiver(f'{SURFACE}.output')])
        assert ev.ok, ev.failures

    def test_without_a_nested_config_only_requiredness_is_checked(self):
        """A flattening with no `python_config` cannot know what the fields
        should default to, so it must not invent a default gap."""
        ts = self._ts(markdown={'default': True, 'default_kind': 'literal'})
        _, ev = run([sig('python', self.PY)], [sig('typescript', ts)], rules=self._rules(mapped=False))
        assert ev.ok, ev.failures


# --------------------------------------------------- unrecognised defaults (D2)

class TestUnknownTsDefault:
    """
    `collectDefaultsFrom` recognised only a handful of TS defaulting forms, and
    anything else recorded nothing -- `default_kind: null`, compared as
    `undefined`, silently matched by the `null <-> undefined` and
    `false <-> undefined` equivalences.

    Reproduced on the real repository: rewriting one line to
    `this.reasoningEffort = ({ reasoningEffort: 'high', ...config }).reasoningEffort;`
    left the report byte-identical and every gate green, and so did an
    `if`-statement default that gated every tool behind an interactive prompt.
    """

    def test_unknown_ts_default_is_a_gap(self):
        py = [py_param('reasoning_effort', default=None)]
        ts = [ts_param('reasoningEffort', default=None, default_kind='unknown')]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert not ev.ok
        assert row(comps, 'reasoning_effort').gap.kind == 'default'
        assert 'unknown' in row(comps, 'reasoning_effort').gap.detail

    def test_unknown_is_not_matched_by_the_false_undefined_equivalence(self):
        """A `false <-> undefined` Python default must not absorb an unknown."""
        py = [py_param('approval', default=False)]
        ts = [ts_param('approval', default=None, default_kind='unknown')]
        _, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert not ev.ok

    def test_control_genuinely_no_default_is_still_undefined(self):
        py = [py_param('approval', default=None)]
        ts = [ts_param('approval')]
        _, ev = run([sig('python', py)], [sig('typescript', ts)])
        assert ev.ok, ev.failures

    def test_unknown_is_waivable(self):
        py = [py_param('reasoning_effort', default=None)]
        ts = [ts_param('reasoningEffort', default=None, default_kind='unknown')]
        _, ev = run([sig('python', py)], [sig('typescript', ts)],
                    waivers=[waiver(f'{SURFACE}.reasoning_effort')])
        assert ev.ok, ev.failures

    def test_unknown_renders_distinctly_from_undefined(self):
        py = [py_param('reasoning_effort', default=None), py_param('other', default=None)]
        ts = [ts_param('reasoningEffort', default=None, default_kind='unknown'), ts_param('other')]
        comps, _ = run([sig('python', py)], [sig('typescript', ts)],
                       waivers=[waiver(f'{SURFACE}.reasoning_effort')])
        md = C.render_markdown(comps, [])
        assert '| unknown |' in md and '| undefined |' in md


# ------------------------------------------------ TS-only required member (D3)

class TestTsOnlyRequiredMember:
    """
    `ts_only` was computed and rendered but `evaluate()` never looked at it.
    Reproduced on the real repository: adding a required `tenantId` to
    `SimpleAgentConfig` failed only on report freshness, and running `--write`
    -- exactly what the CI error tells you to do -- made it green.
    """

    def test_required_ts_only_member_fails(self):
        ts = BASE_TS + [ts_param('tenantId', required=True)]
        comps, ev = run([sig('python', BASE_PY)], [sig('typescript', ts)])
        assert not ev.ok
        assert any('tenantId' in f and SURFACE in f for f in ev.failures)
        assert [p.name for p in comps[0].ts_only_required()] == ['tenantId']

    def test_optional_ts_only_member_stays_informational(self):
        ts = BASE_TS + [ts_param('tenantId', required=False)]
        comps, ev = run([sig('python', BASE_PY)], [sig('typescript', ts)])
        assert ev.ok, ev.failures
        assert [p.name for p in comps[0].ts_only] == ['tenantId']
        assert comps[0].ts_only_required() == []

    def test_required_ts_only_member_is_waivable(self):
        ts = BASE_TS + [ts_param('tenantId', required=True)]
        _, ev = run([sig('python', BASE_PY)], [sig('typescript', ts)],
                    waivers=[waiver(f'{SURFACE}.tenantId')])
        assert ev.ok, ev.failures

    def test_expired_waiver_on_a_ts_only_member_fails(self):
        ts = BASE_TS + [ts_param('tenantId', required=True)]
        _, ev = run([sig('python', BASE_PY)], [sig('typescript', ts)],
                    waivers=[waiver(f'{SURFACE}.tenantId', expires=date(2026, 1, 1))])
        assert not ev.ok
        assert any('expired' in f for f in ev.failures)

    def test_the_options_parameter_itself_is_not_a_gap(self):
        """`constructor(config: SimpleAgentConfig)` is required, but a required
        options OBJECT is not a parity gap: its members are the surface, and
        Python spells them out as keyword arguments."""
        ts = BASE_TS + [ts_param('config', required=True, kind='positional')]
        comps, ev = run([sig('python', BASE_PY)],
                        [sig('typescript', ts, extra={'options_parameters': ['config']})])
        assert ev.ok, ev.failures
        assert comps[0].ts_only_required() == []

    def test_baseline_and_prune_cover_ts_only_gaps(self):
        """Without this, `--baseline` would never write the waiver the gate
        demands and `--prune` would delete it again as stale."""
        ts = BASE_TS + [ts_param('tenantId', required=True)]
        comps, _ = run([sig('python', BASE_PY)], [sig('typescript', ts)])
        assert [w.key for w in C.baseline_waivers(comps, [])] == [f'{SURFACE}.tenantId']
        live = waiver(f'{SURFACE}.tenantId')
        assert [w.key for w in C.prune_waivers(comps, [live, waiver(f'{SURFACE}.gone')])] == [live.key]

    def test_required_ts_only_member_is_named_in_the_report(self):
        ts = BASE_TS + [ts_param('tenantId', required=True), ts_param('optional_extra')]
        comps, _ = run([sig('python', BASE_PY)], [sig('typescript', ts)],
                       waivers=[waiver(f'{SURFACE}.tenantId')])
        md = C.render_markdown(comps, [])
        assert 'TS-only members that are REQUIRED' in md and '`tenantId`' in md


# --------------------------------------------------- rules.yaml self-test (D4)

class TestRulesSelfTest:
    """
    Eight entries in `rules.yaml` fired zero times on a real run and nothing
    noticed, because `test_config_files_load` only asserted that the YAML says
    what the YAML says. `validate_rules` checks the config against a real
    extraction so dead config cannot accumulate again.
    """

    @staticmethod
    def _sides(py_names, ts_names):
        python = C.signatures_from_json([sig('python', [py_param(n) for n in py_names])])
        typescript = C.signatures_from_json([sig('typescript', [ts_param(n) for n in ts_names])])
        return python, typescript

    def _problems(self, rules, py_names=('name',), ts_names=('name',)):
        python, typescript = self._sides(py_names, ts_names)
        return C.validate_rules(rules, python, typescript)

    def test_control_a_live_alias_is_clean(self):
        rules = default_rules(aliases={'base_url': 'baseURL'})
        assert self._problems(rules, ['base_url'], ['baseURL']) == []

    def test_alias_for_a_python_parameter_that_does_not_exist(self):
        rules = default_rules(aliases={'output_json': 'outputSchema'})
        problems = self._problems(rules, ['name'], ['outputSchema'])
        assert len(problems) == 1
        assert 'output_json' in problems[0] and 'no Python parameter' in problems[0]

    def test_alias_shadowed_by_the_exact_name_tier(self):
        rules = default_rules(aliases={'model': 'llm'})
        problems = self._problems(rules, ['model'], ['model', 'llm'])
        assert len(problems) == 1
        assert 'never fires' in problems[0] and 'exact-name' in problems[0]

    def test_alias_shadowed_by_the_camel_case_tier(self):
        rules = default_rules(aliases={'session_id': 'id'})
        problems = self._problems(rules, ['session_id'], ['sessionId', 'id'])
        assert len(problems) == 1
        assert 'never fires' in problems[0] and 'camelCase' in problems[0]

    def test_alias_that_is_a_pure_case_change(self):
        rules = default_rules(aliases={'agent_url': 'agentUrl'})
        problems = self._problems(rules, ['agent_url'], ['agentUrl'])
        assert len(problems) == 1
        assert 'pure case change' in problems[0]

    def test_alias_shadowed_by_a_flattening(self):
        """`caching -> cache` used to win over the stricter two-field rule."""
        rules = default_rules(aliases={'caching': 'cache'},
                              flattened={'caching': flattening(['cache', 'cacheTTL'])})
        problems = self._problems(rules, ['caching'], ['cache', 'cacheTTL'])
        assert len(problems) == 1
        assert 'never fires' in problems[0] and 'flattened' in problems[0]

    def test_alias_naming_a_typescript_member_that_does_not_exist(self):
        rules = default_rules(aliases={'base_url': 'baseURL'})
        problems = self._problems(rules, ['base_url'], ['name'])
        assert len(problems) == 1 and 'no TypeScript member' in problems[0]

    def test_flattening_for_a_python_parameter_that_does_not_exist(self):
        rules = default_rules(flattened={'output': flattening(['verbose'])})
        problems = self._problems(rules, ['name'], ['verbose'])
        assert len(problems) == 1 and 'no Python parameter' in problems[0]

    def test_flattening_whose_typescript_fields_do_not_exist(self):
        rules = default_rules(flattened={'output': flattening(['verbose', 'markdown'])})
        problems = self._problems(rules, ['output'], ['verbose'])
        assert len(problems) == 1 and 'markdown' in problems[0] and 'never fires' in problems[0]

    def test_flattening_mapping_a_field_the_config_class_does_not_have(self):
        rules = default_rules(
            flattened={'output': flattening(['verbose'], python_config='m.py:OutputConfig',
                                            field_map={'verbose': 'nope'})},
            nested_defaults={'m.py:OutputConfig': {}},
        )
        problems = self._problems(rules, ['output'], ['verbose'])
        assert len(problems) == 1 and 'nope' in problems[0]

    def test_unreachable_default_equivalence(self):
        rules = C.Rules(default_equivalences=[(True, True), (False, False), (None, 'undefined')])
        problems = C.validate_rules(rules, {}, {})
        assert len(problems) == 2
        assert all('unreachable' in p for p in problems)

    def test_raise_on_rules_problems_is_a_tooling_error(self):
        with pytest.raises(C.ToolingError) as excinfo:
            C._raise_on_rules_problems(['a dead rule'])
        assert 'a dead rule' in str(excinfo.value)
        C._raise_on_rules_problems([])  # no problems -> no raise

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_the_shipped_rules_are_clean_against_the_real_extraction(self):
        """The check that would have caught all eight dead entries."""
        catalogue = C.load_surfaces()
        rules = C.load_rules()
        C.load_nested_config_defaults(rules, REPO_ROOT, catalogue.python_root)
        python, typescript = C.extract_all(REPO_ROOT, catalogue)
        assert C.validate_rules(rules, python, typescript) == []


class TestFlattenedBeatsAlias:
    """MATCH_ORDER puts `flattened` before `alias`: it is the stricter rule."""

    def test_flattening_wins_over_an_alias_for_the_same_parameter(self):
        rules = default_rules(aliases={'caching': 'cache'},
                              flattened={'caching': flattening(['cache', 'cacheTTL'])})
        py = [py_param('caching', default=None)]
        ts = [ts_param('cache', default=False, default_kind='literal'),
              ts_param('cacheTTL', default=3600, default_kind='literal')]
        comps, _ = run([sig('python', py)], [sig('typescript', ts)], rules=rules)
        assert row(comps, 'caching').match == 'flattened'
        assert row(comps, 'caching').ts_names == ['cache', 'cacheTTL']

    def test_alias_still_wins_when_the_flattening_cannot_resolve(self):
        rules = default_rules(aliases={'caching': 'cache'},
                              flattened={'caching': flattening(['cache', 'cacheTTL'])})
        py = [py_param('caching', default=None)]
        ts = [ts_param('cache', default=None, default_kind=None)]
        comps, ev = run([sig('python', py)], [sig('typescript', ts)], rules=rules)
        assert row(comps, 'caching').match == 'alias'
        assert ev.ok, ev.failures

    def test_exact_and_camel_case_still_win_over_a_flattening(self):
        rules = default_rules(flattened={'output': flattening(['verbose'])})
        py = [py_param('output', default=None)]
        ts = [ts_param('output', default=None), ts_param('verbose', default=None)]
        comps, _ = run([sig('python', py)], [sig('typescript', ts)], rules=rules)
        assert row(comps, 'output').match == 'exact'


class TestTsExtractorUnrecognisedDefaults:
    """
    The TypeScript extractor must tell "the constructor assigns no default"
    apart from "the constructor decides the default in a form I cannot read".
    Everything in the second group is reported as `default_kind: 'unknown'`,
    which the comparator treats as a gap.
    """

    FIXTURE = """
export interface Cfg {
  spread?: string;
  overwritten?: string;
  assigned?: number;
  ifDefault?: number;
  fromProperty?: boolean;
  model?: string;
  guarded?: any[];
  passedThrough?: string;
  chained?: string;
  recognised?: number;
}
export class Nested { model = 'unset'; }
export class Widget {
  private fromProperty: boolean = true;
  private nested: Nested;
  private spread?: string;
  private overwritten?: string;
  private assigned?: number;
  private ifDefault?: number;
  private guarded?: any[];
  private passedThrough?: string;
  private chained?: string;
  private recognised?: number;

  constructor(config: Cfg) {
    this.recognised = config.recognised ?? 7;
    this.spread = ({ spread: 'high', ...config }).spread;
    this.overwritten = ({ ...config, overwritten: 'forced' }).overwritten;
    this.assigned = Object.assign({ assigned: 42 }, config).assigned;
    if (config.ifDefault === undefined) {
      this.ifDefault = 20;
    } else {
      this.ifDefault = config.ifDefault;
    }
    if (config.fromProperty !== undefined) {
      this.fromProperty = config.fromProperty;
    }
    this.nested = new Nested();
    if (config.model != null) {
      this.nested.model = config.model;
    }
    if (config.guarded && Array.isArray(config.guarded)) {
      this.guarded = config.guarded.slice();
    }
    this.passedThrough = config.passedThrough;
    if (config.chained) {
      this.chained = config.chained;
    } else if (config.passedThrough) {
      this.chained = 'derived';
    } else {
      this.chained = 'fallback';
    }
  }
}
"""

    @staticmethod
    def _params(tmp_path):
        src = tmp_path / 'src' / 'praisonai-ts' / 'src'
        src.mkdir(parents=True)
        (src / 'widget.ts').write_text(TestTsExtractorUnrecognisedDefaults.FIXTURE)
        items = C.run_ts_extractor(tmp_path, [
            {'surface': 'Widget.__init__', 'file': 'widget.ts', 'kind': 'interface',
             'name': 'Cfg', 'ctorClass': 'Widget'},
        ])
        return {p['name']: p for p in items[0]['params'] if p['kind'] == 'property'}

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_recognised_forms_are_unchanged(self, tmp_path):
        p = self._params(tmp_path)['recognised']
        assert p['default'] == 7 and p['default_kind'] == 'literal'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_object_spread_default_is_read(self, tmp_path):
        """`({ x: 'high', ...config }).x` -- the exact rewrite that left the
        real report byte-identical and every gate green."""
        p = self._params(tmp_path)['spread']
        assert p['default'] == 'high' and p['default_kind'] == 'literal'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_a_property_written_after_the_spread_is_unknown(self, tmp_path):
        """`{ ...config, x: 'forced' }` ignores whatever the caller passed."""
        assert self._params(tmp_path)['overwritten']['default_kind'] == 'unknown'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_object_assign_default_is_read(self, tmp_path):
        p = self._params(tmp_path)['assigned']
        assert p['default'] == 42 and p['default_kind'] == 'literal'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_if_statement_default_is_read(self, tmp_path):
        p = self._params(tmp_path)['ifDefault']
        assert p['default'] == 20 and p['default_kind'] == 'literal'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_class_property_initialiser_is_the_default_when_nothing_else_runs(self, tmp_path):
        """`if (config.x !== undefined) this.x = config.x;` keeps `private x = true`."""
        p = self._params(tmp_path)['fromProperty']
        assert p['default'] is True and p['default_kind'] == 'literal'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_default_held_in_a_nested_config_object_is_unknown(self, tmp_path):
        """The real GoalEngineer shape: the fallback lives in `new Nested()`,
        which this extractor cannot evaluate. Reporting `undefined` would say
        the two SDKs agree when nobody has checked."""
        assert self._params(tmp_path)['model']['default_kind'] == 'unknown'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_multi_way_derivation_is_unknown_not_one_arbitrary_arm(self, tmp_path):
        assert self._params(tmp_path)['chained']['default_kind'] == 'unknown'

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_control_a_guard_is_not_a_default(self, tmp_path):
        """`if (config.x && Array.isArray(config.x)) { ...use it... }` decides no
        default. Flagging these was a false positive worth avoiding: an
        `unknown` costs a hand-written waiver."""
        params = self._params(tmp_path)
        assert params['guarded']['default_kind'] is None
        assert params['passedThrough']['default_kind'] is None

    @pytest.mark.skipif(shutil.which('node') is None, reason='node is not on PATH')
    @pytest.mark.skipif(not _typescript_resolvable(),
                        reason='typescript module not resolvable (set PARITY_TS_NODE_MODULES)')
    def test_the_options_parameter_is_named_in_extra(self, tmp_path):
        """So the comparator can tell the options bag from a real TS-only member."""
        src = tmp_path / 'src' / 'praisonai-ts' / 'src'
        src.mkdir(parents=True)
        (src / 'widget.ts').write_text(self.FIXTURE)
        items = C.run_ts_extractor(tmp_path, [
            {'surface': 'Widget.__init__', 'file': 'widget.ts', 'kind': 'interface',
             'name': 'Cfg', 'ctorClass': 'Widget'},
        ])
        assert items[0]['extra']['options_parameters'] == ['config']
