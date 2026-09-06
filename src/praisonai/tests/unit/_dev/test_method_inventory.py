"""
Unit tests for the public method inventory
(``praisonai._dev.parity.signatures.method_inventory``).

The signature layer compares one function per surface -- almost always
``__init__`` -- so a class could lose every other method and stay green.
``Session`` did: Python has ``save_state``, ``restore_state``, ``add_memory``,
``search_memory`` and ``chat``; the TypeScript class has none of them.

The fixtures build a miniature monorepo in ``tmp_path`` and run the real Python
AST walk and the real TypeScript member lister over it. The TypeScript half
needs ``node`` plus the ``typescript`` package, so those tests skip without it;
the Python half and the comparator run unconditionally.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from praisonai._dev.parity.signatures import compare as C
from praisonai._dev.parity.signatures import method_inventory as M

REPO_ROOT = Path(__file__).resolve().parents[5]
TS_ROOT = 'src/praisonai-ts/src'
PY_ROOT = 'src/praisonai-agents/praisonaiagents'


def _typescript_resolvable() -> bool:
    """True when ts_members.mjs will find the typescript module.

    The same probe ``test_signature_parity`` uses; duplicated rather than
    imported so this module runs when pointed at directly.
    """
    override = os.environ.get('PARITY_TS_NODE_MODULES')
    if override:
        return (Path(override) / 'typescript' / 'package.json').is_file()
    if (REPO_ROOT / 'src' / 'praisonai-ts' / 'node_modules' / 'typescript' / 'package.json').is_file():
        return True
    if shutil.which('node') is None:
        return False
    probe = subprocess.run(['node', '-e', "require('typescript')"], capture_output=True, text=True,
                           cwd=str(M.TS_MEMBERS_SCRIPT.parent))
    return probe.returncode == 0


needs_node = pytest.mark.skipif(
    shutil.which('node') is None or not _typescript_resolvable(),
    reason='node plus the typescript package are needed to list TypeScript members')


# ------------------------------------------------------------------ fixtures

def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def surface(key='Session.__init__', ts_file='session/session.ts', ctor_class='Session',
            py_file='session/api.py', py_class='Session', method_waivers=None):
    return C.Surface(
        key=key,
        python={'file': py_file, 'class': py_class, 'function': '__init__'},
        typescript={'file': ts_file, 'kind': 'interface', 'name': 'SessionConfig',
                    'ctorClass': ctor_class},
        method_waivers=method_waivers or {},
    )


def catalogue(*surfaces):
    return C.SurfaceCatalogue(surfaces=list(surfaces), python_root=PY_ROOT, typescript_root=TS_ROOT)


PY_SESSION = '''
class Session:
    def __init__(self, session_id=None):
        self.session_id = session_id

    def save_state(self, state):
        pass

    def get_state(self, key, default=None):
        pass

    def _private(self):
        pass

    @property
    def expired(self):
        return False
'''

TS_SESSION_MISSING = '''
export interface SessionConfig { sessionId?: string }
export class Session {
  constructor(config: SessionConfig) {}
  getState(): Record<string, any> { return {}; }
  private saveState() {}
}
'''

TS_SESSION_COMPLETE = '''
export interface SessionConfig { sessionId?: string }
export class Session {
  constructor(config: SessionConfig) {}
  getState(key: string, fallback?: any) { return fallback; }
  saveState(state: any) {}
}
'''


def mini_repo(tmp_path: Path, ts_source: str, py_source: str = PY_SESSION) -> Path:
    write(tmp_path, f'{PY_ROOT}/session/api.py', py_source)
    write(tmp_path, f'{TS_ROOT}/session/session.ts', ts_source)
    return tmp_path


# --------------------------------------------------------------- the defect

@needs_node
class TestMissingMethodIsAFinding:
    def test_a_python_method_with_no_typescript_counterpart_fails(self, tmp_path):
        mini_repo(tmp_path, TS_SESSION_MISSING)
        inventory, = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert [m.name for m in inventory.unwaived] == ['save_state']
        assert inventory.missing[0].expected_ts == 'saveState'
        assert inventory.missing[0].location.endswith('session/api.py:6')
        assert not inventory.ok

    def test_the_control_with_every_method_present_passes(self, tmp_path):
        mini_repo(tmp_path, TS_SESSION_COMPLETE)
        inventory, = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert inventory.unwaived == []
        assert sorted(inventory.present) == ['get_state', 'save_state']
        assert inventory.ok

    def test_the_gate_turns_a_missing_method_into_a_failure(self, tmp_path):
        mini_repo(tmp_path, TS_SESSION_MISSING)
        inventories = M.check_method_inventory(tmp_path, catalogue(surface()))
        evaluation = C.evaluate_method_inventory(inventories, C.Evaluation())
        assert not evaluation.ok
        assert 'save_state' in evaluation.failures[0]
        assert 'method_waivers' in evaluation.failures[0], 'the failure must say how to waive'

    def test_the_gate_passes_the_control(self, tmp_path):
        mini_repo(tmp_path, TS_SESSION_COMPLETE)
        inventories = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert C.evaluate_method_inventory(inventories, C.Evaluation()).ok

    def test_a_private_typescript_member_does_not_count_as_a_counterpart(self, tmp_path):
        """`private saveState()` is unreachable from outside; it is not parity."""
        mini_repo(tmp_path, TS_SESSION_MISSING)
        inventory, = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert 'save_state' in [m.name for m in inventory.unwaived]

    def test_an_absent_typescript_class_reports_every_method(self, tmp_path):
        mini_repo(tmp_path, 'export interface SessionConfig { sessionId?: string }\n')
        inventory, = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert sorted(m.name for m in inventory.unwaived) == ['get_state', 'save_state']
        assert any('absent' in note for note in inventory.notes)

    def test_an_accessor_does_not_count_as_a_method_counterpart(self, tmp_path):
        # `get getState()` is not callable as `session.getState()`; a Python
        # *method* matched to it would read as present while the call fails at
        # runtime. So the accessor must not satisfy the method, and `get_state`
        # is still reported missing. `save_state` -> `saveState()` (a real
        # method) matches, proving only the accessor is excluded.
        mini_repo(tmp_path, '''
export interface SessionConfig { sessionId?: string }
export class Session {
  get getState() { return {}; }
  saveState() {}
}
''')
        inventory, = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert [m.name for m in inventory.unwaived] == ['get_state']

    def test_an_arrow_function_property_counts_as_a_counterpart(self, tmp_path):
        mini_repo(tmp_path, '''
export interface SessionConfig { sessionId?: string }
export class Session {
  getState = () => ({});
  saveState = async (s: any) => {};
}
''')
        inventory, = M.check_method_inventory(tmp_path, catalogue(surface()))
        assert inventory.unwaived == []


@needs_node
class TestWaivers:
    def test_a_signed_waiver_accepts_one_missing_method(self, tmp_path):
        mini_repo(tmp_path, TS_SESSION_MISSING)
        waived = surface(method_waivers={
            'save_state': {'reason': 'browser sessions have no state file', 'owner': 'praisonai-ts'}})
        inventory, = M.check_method_inventory(tmp_path, catalogue(waived))
        assert [m.name for m in inventory.missing] == ['save_state'], 'still detected'
        assert inventory.unwaived == [], 'but accepted'
        assert C.evaluate_method_inventory([inventory], C.Evaluation()).ok

    def test_a_waiver_without_a_reason_is_a_tooling_error(self, tmp_path):
        path = tmp_path / 'surface.yaml'
        path.write_text(
            'surfaces:\n'
            '  - key: Session.__init__\n'
            '    python: {file: session/api.py, class: Session, function: __init__}\n'
            '    typescript: {file: session/session.ts, kind: interface, name: SessionConfig}\n'
            '    method_waivers:\n'
            '      save_state: {owner: praisonai-ts}\n',
            encoding='utf-8')
        with pytest.raises(C.ToolingError, match='reason'):
            C.load_surfaces(path)

    def test_control_a_complete_waiver_loads(self, tmp_path):
        path = tmp_path / 'surface.yaml'
        path.write_text(
            'surfaces:\n'
            '  - key: Session.__init__\n'
            '    python: {file: session/api.py, class: Session, function: __init__}\n'
            '    typescript: {file: session/session.ts, kind: interface, name: SessionConfig}\n'
            '    method_waivers:\n'
            '      save_state: {reason: no state file in the browser, owner: praisonai-ts}\n',
            encoding='utf-8')
        cat = C.load_surfaces(path)
        assert cat.surfaces[0].method_waivers['save_state']['owner'] == 'praisonai-ts'


# ---------------------------------------------------------------- python side

class TestPythonMethodListing:
    def index(self, tmp_path, source, rel=f'{PY_ROOT}/mod.py'):
        write(tmp_path, rel, source)
        return M.PythonClassIndex(tmp_path, PY_ROOT)

    def test_public_methods_only(self, tmp_path):
        index = self.index(tmp_path, '''
class Widget:
    def run(self): pass
    async def arun(self): pass
    def _hidden(self): pass
    @property
    def size(self): return 1
    @staticmethod
    def build(): pass
''')
        methods = index.public_methods('Widget')
        assert [m.name for m in methods.methods] == ['arun', 'build', 'run']

    def test_mixin_methods_are_inherited(self, tmp_path):
        """Agent gets `execute`, `chat` and `start` from twelve mixins, not its own body."""
        write(tmp_path, f'{PY_ROOT}/agent/mixins.py', '''
class ExecutionMixin:
    def execute(self, task, context=None): pass
''')
        write(tmp_path, f'{PY_ROOT}/agent/agent.py', '''
from .mixins import ExecutionMixin

class Agent(ExecutionMixin):
    def chat(self, prompt): pass
''')
        index = M.PythonClassIndex(tmp_path, PY_ROOT)
        methods = index.public_methods('Agent')
        names = {m.name: m for m in methods.methods}
        assert set(names) == {'chat', 'execute'}
        assert names['execute'].owner == 'ExecutionMixin'
        assert names['execute'].location.endswith('agent/mixins.py:3')
        assert methods.unresolved_bases == []

    def test_a_base_outside_the_package_is_named_not_swallowed(self, tmp_path):
        index = self.index(tmp_path, '''
class Widget(SomeVendorBase):
    def run(self): pass
''')
        methods = index.public_methods('Widget')
        assert methods.unresolved_bases == ['SomeVendorBase']

    def test_exception_bases_are_not_reported_as_unresolved(self, tmp_path):
        index = self.index(tmp_path, '''
class PraisonAIError(Exception):
    def detail(self): pass
''')
        methods = index.public_methods('PraisonAIError')
        assert methods.unresolved_bases == []
        assert [m.name for m in methods.methods] == ['detail']

    def test_an_override_keeps_the_subclass_location(self, tmp_path):
        write(tmp_path, f'{PY_ROOT}/base.py', 'class Base:\n    def run(self): pass\n')
        write(tmp_path, f'{PY_ROOT}/child.py', 'from .base import Base\n\n\nclass Child(Base):\n    def run(self): pass\n')
        index = M.PythonClassIndex(tmp_path, PY_ROOT)
        method, = index.public_methods('Child').methods
        assert method.owner == 'Child' and method.location.endswith('child.py:5')

    def test_a_missing_class_is_none(self, tmp_path):
        index = self.index(tmp_path, 'class Widget: pass\n')
        assert index.public_methods('Nope') is None

    def test_prefer_disambiguates_a_class_name_declared_in_two_files(self, tmp_path):
        # `Task` (and `DoomLoopDetector`) is declared in more than one file with
        # different methods. Without the surface's `python.file` hint the lookup
        # takes the alphabetically first declaration and compares an unrelated
        # class -- a silent false pass or failure. `prefer` must pin the right one.
        write(tmp_path, f'{PY_ROOT}/a_other.py', 'class Task:\n    def wrong(self): pass\n')
        write(tmp_path, f'{PY_ROOT}/task/task.py', 'class Task:\n    def right(self): pass\n')
        index = M.PythonClassIndex(tmp_path, PY_ROOT)
        # Alphabetically first (a_other.py) is what the old code picked.
        assert [m.name for m in index.public_methods('Task').methods] == ['wrong']
        prefer = tmp_path / PY_ROOT / 'task/task.py'
        picked = index.public_methods('Task', prefer=prefer)
        assert [m.name for m in picked.methods] == ['right']
        assert picked.location.endswith('task/task.py:1')

    def test_configured_python_file_builds_the_hint_from_the_surface(self, tmp_path):
        write(tmp_path, f'{PY_ROOT}/task/task.py', 'class Task: pass\n')
        index = M.PythonClassIndex(tmp_path, PY_ROOT)
        s = surface(key='Task.__init__', py_file='task/task.py', py_class='Task')
        assert M._configured_python_file(index, s) == (tmp_path / PY_ROOT / 'task/task.py').resolve()
        s_no_file = C.Surface(key='x', python={}, typescript={})
        assert M._configured_python_file(index, s_no_file) is None


class TestNameMatching:
    def test_snake_case_matches_camel_case_and_nothing_looser(self):
        assert M._ts_candidates('save_state') == {'save_state', 'saveState'}
        assert 'savestate' not in M._ts_candidates('save_state')
        assert 'save' not in M._ts_candidates('save_state')


class TestSurfacesWithoutAClass:
    def test_a_surface_naming_no_class_is_skipped_with_a_reason(self, tmp_path):
        write(tmp_path, f'{PY_ROOT}/tools/decorator.py', 'def tool(fn=None):\n    pass\n')
        write(tmp_path, f'{TS_ROOT}/tools/decorator.ts', 'export function tool(c: any) { return c; }\n')
        s = C.Surface(key='tool()',
                      python={'file': 'tools/decorator.py', 'function': 'tool'},
                      typescript={'file': 'tools/decorator.ts', 'kind': 'interface', 'name': 'ToolConfig'})
        inventories = M.check_method_inventory(tmp_path, catalogue(s))
        assert inventories == [], 'a surface with no TypeScript class is not inventoried'


# ------------------------------------------------------------- tooling errors

class TestToolingFailures:
    def test_a_missing_node_is_a_tooling_error_not_an_empty_inventory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M.shutil, 'which', lambda name: None)
        with pytest.raises(M.MemberToolingError, match='node'):
            M.run_ts_members(tmp_path, [{'cls': 'Session', 'file': 'session/session.ts'}])

    @needs_node
    def test_an_unresolvable_typescript_package_is_a_tooling_error(self, tmp_path, monkeypatch):
        empty = tmp_path / 'node_modules'
        empty.mkdir()
        monkeypatch.setenv('PARITY_TS_NODE_MODULES', str(empty))
        with pytest.raises(M.MemberToolingError, match='typescript'):
            M.run_ts_members(tmp_path, [{'cls': 'Session', 'file': 'session/session.ts'}])

    def test_no_targets_returns_nothing_without_running_node(self, tmp_path):
        assert M.run_ts_members(tmp_path, []) == {}


# ------------------------------------------------------------ the real repo

@needs_node
class TestTheRealRepository:
    """
    Pins what the inventory says about this checkout, including the four cases
    the audit named. Each assertion is meant to break when the method is ported;
    delete it then.
    """

    def inventories(self):
        return {i.key: i for i in M.check_method_inventory(REPO_ROOT, C.load_surfaces())}

    def test_session_is_missing_the_state_and_memory_api(self):
        missing = {m.name for m in self.inventories()['Session'].unwaived}
        assert {'save_state', 'restore_state', 'add_memory', 'search_memory', 'chat'} <= missing

    def test_function_tool_is_missing_run(self):
        assert 'run' in {m.name for m in self.inventories()['FunctionTool'].unwaived}

    def test_agent_execute_counts_as_present_because_this_check_reads_names_only(self):
        """The documented limit, pinned so nobody reads a green Agent.execute as parity.

        Python `execute(task, context=None)` runs the task it is handed;
        TypeScript `execute(previousResult?)` runs the agent's own instructions.
        Same name, different job -- and this check, by design, cannot see it.
        """
        agent = self.inventories()['Agent']
        assert 'execute' in agent.present
        assert 'execute' not in {m.name for m in agent.unwaived}

    def test_classes_with_no_findings_are_reported_as_such(self):
        clean = {k for k, i in self.inventories().items() if not i.skipped and not i.unwaived}
        assert {'GoalEngineer', 'DoomLoopDetector', 'EscalationPipeline', 'Knowledge'} <= clean

    def test_every_python_side_class_resolves(self):
        unresolved = {k: i.skipped for k, i in self.inventories().items() if i.skipped}
        assert unresolved == {}, unresolved


# --------------------------------------------------------------------- CLI

class TestMethodsCli:
    @needs_node
    def test_methods_mode_exits_1_while_methods_are_unported(self, capsys):
        code = C.main(['--methods', '--repo-root', str(REPO_ROOT)])
        out = capsys.readouterr().out
        assert code == C.EXIT_PARITY, out
        assert 'NAMES ONLY' in out, 'the output must say what it compares'
        assert 'Session' in out

    def test_a_missing_node_exits_2_not_0(self, monkeypatch, capsys):
        monkeypatch.setattr(M.shutil, 'which', lambda name: None)
        code = C.main(['--methods', '--repo-root', str(REPO_ROOT)])
        assert code == C.EXIT_TOOLING
        assert 'method inventory' in capsys.readouterr().err
