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


def sig(language, params, surface=SURFACE):
    return {'surface': surface, 'language': language, 'location': f'{language}.src:1', 'params': params}


def default_rules(aliases=None, flattened=None):
    return C.Rules(
        aliases={SURFACE: aliases or {}},
        flattened={SURFACE: flattened or {}},
        default_equivalences=[(None, 'undefined'), (True, True), (False, False)],
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
        assert start['prompt']['required'] is True and start['prompt']['type_class'] == 'string'
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
        assert len(catalogue.surfaces) == 10
        assert {s.key for s in catalogue.surfaces} >= {'Agent.__init__', 'AgentTeam.__init__', 'tool()'}
        rules = C.load_rules()
        assert rules.aliases['Agent.__init__']['base_url'] == 'baseURL'
        assert rules.flattened['Agent.__init__']['output'] == ['verbose', 'markdown', 'stream']
        assert (None, 'undefined') in rules.default_equivalences
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
