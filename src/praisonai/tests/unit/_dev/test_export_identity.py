"""
Unit tests for the export-identity check
(``praisonai._dev.parity.signatures.export_identity``).

The check exists because ``surface.yaml`` mapped ``Task.__init__`` to
``agent/types.ts`` and the gate reported 60 of 60 parameters matched, while
``src/index.ts`` exports a *different* ``Task`` from ``./workflows``. Every
parameter agreed; no caller could obtain the class being validated.

Every fixture builds a miniature monorepo in ``tmp_path`` and runs the real
resolver over it -- no mocks -- so a change to the barrel walk shows up here.
"""

from pathlib import Path

import pytest

from praisonai._dev.parity.signatures import compare as C
from praisonai._dev.parity.signatures import export_identity as E

REPO_ROOT = Path(__file__).resolve().parents[5]
TS_ROOT = 'src/praisonai-ts/src'


# ------------------------------------------------------------------ fixtures

def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def surface(key, ts_file, ctor_class=None, cls=None, name='Config', kind='interface',
            py_class=None, aliases=None, export_identity=None):
    ts = {'file': ts_file, 'kind': kind, 'name': name}
    if ctor_class:
        ts['ctorClass'] = ctor_class
    if cls:
        ts['cls'] = cls
    python = {'file': 'x.py', 'function': '__init__'}
    if py_class:
        python['class'] = py_class
    if aliases:
        python['aliases'] = list(aliases)
    return C.Surface(key=key, python=python, typescript=ts, export_identity=export_identity)


def catalogue(*surfaces):
    return C.SurfaceCatalogue(surfaces=list(surfaces), typescript_root=TS_ROOT)


def two_tasks(tmp_path: Path) -> Path:
    """The real shape of the defect: two classes called Task, one exported."""
    write(tmp_path, f'{TS_ROOT}/index.ts', "export { Task } from './workflows';\n")
    write(tmp_path, f'{TS_ROOT}/workflows/index.ts',
          'export class Task<TInput = any> {\n  name!: string;\n  execute() {}\n}\n')
    write(tmp_path, f'{TS_ROOT}/agent/types.ts',
          'export interface TaskConfig { description: string; }\n'
          'export class Task {\n  description!: string;\n}\n')
    return tmp_path


# --------------------------------------------------------------- the defect

class TestBarrelExportsADifferentSymbol:
    """The failing case: the surface validates a class nobody can import."""

    def test_a_different_declaration_under_the_same_name_fails(self, tmp_path):
        two_tasks(tmp_path)
        cat = catalogue(surface('Task.__init__', 'agent/types.ts',
                                ctor_class='Task', name='TaskConfig'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MISMATCH
        assert not finding.ok
        assert 'workflows/index.ts' in finding.detail()
        assert 'agent/types.ts' in finding.detail()

    def test_the_control_pointing_at_the_exported_one_passes(self, tmp_path):
        two_tasks(tmp_path)
        cat = catalogue(surface('Task.__init__', 'workflows/index.ts',
                                ctor_class='Task', name='TaskConfig'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH, finding.detail()
        assert finding.ok

    def test_the_gate_turns_the_mismatch_into_a_failure(self, tmp_path):
        two_tasks(tmp_path)
        cat = catalogue(surface('Task.__init__', 'agent/types.ts', ctor_class='Task'))
        evaluation = C.evaluate_export_identity(E.check_export_identity(tmp_path, cat), C.Evaluation())
        assert not evaluation.ok
        assert 'Task.__init__' in evaluation.failures[0]
        assert 'export_identity' in evaluation.failures[0], 'the failure must say how to record a reason'

    def test_the_gate_passes_the_control(self, tmp_path):
        two_tasks(tmp_path)
        cat = catalogue(surface('Task.__init__', 'workflows/index.ts', ctor_class='Task'))
        evaluation = C.evaluate_export_identity(E.check_export_identity(tmp_path, cat), C.Evaluation())
        assert evaluation.ok, evaluation.failures


class TestNotExportedAtAll:
    def test_a_symbol_the_barrel_never_exports_fails(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts', "export { Agent } from './agent';\n")
        write(tmp_path, f'{TS_ROOT}/agent/index.ts', 'export class Agent {}\n')
        write(tmp_path, f'{TS_ROOT}/auto/index.ts', 'export class AutoAgents {}\n')
        cat = catalogue(surface('AutoAgents.__init__', 'auto/index.ts', ctor_class='AutoAgents'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_NOT_EXPORTED
        assert 'AutoAgents' in finding.detail()

    def test_control_an_exported_symbol_matches(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts',
              "export { Agent } from './agent';\nexport { AutoAgents } from './auto';\n")
        write(tmp_path, f'{TS_ROOT}/agent/index.ts', 'export class Agent {}\n')
        write(tmp_path, f'{TS_ROOT}/auto/index.ts', 'export class AutoAgents {}\n')
        cat = catalogue(surface('AutoAgents.__init__', 'auto/index.ts', ctor_class='AutoAgents'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH, finding.detail()


# ------------------------------------------------------------- barrel walking

class TestBarrelResolution:
    def test_a_chain_of_barrels_is_followed_to_the_declaration(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts', "export { Agent } from './agent';\n")
        write(tmp_path, f'{TS_ROOT}/agent/index.ts', "export { Agent } from './simple';\n")
        write(tmp_path, f'{TS_ROOT}/agent/simple.ts', 'export class Agent {}\n')
        cat = catalogue(surface('Agent.__init__', 'agent/simple.ts', ctor_class='Agent'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH
        assert finding.exported.line == 1

    def test_a_rename_resolves_to_the_source_declaration(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts', "export { AgentTeam as Agents } from './team';\n")
        write(tmp_path, f'{TS_ROOT}/team.ts', '\n\nexport class AgentTeam {}\n')
        cat = catalogue(surface('Agents.__init__', 'team.ts', ctor_class='AgentTeam'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH
        assert finding.exported.name == 'AgentTeam' and finding.exported.line == 3

    def test_a_star_export_is_followed(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts', "export * from './goal';\n")
        write(tmp_path, f'{TS_ROOT}/goal/index.ts', "export * from './engineer';\n")
        write(tmp_path, f'{TS_ROOT}/goal/engineer.ts', 'export class GoalEngineer {}\n')
        cat = catalogue(surface('GoalEngineer.__init__', 'goal/engineer.ts', ctor_class='GoalEngineer'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH, finding.detail()

    def test_a_local_export_list_over_an_import_is_followed(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts',
              "import { Knowledge } from './knowledge/knowledge';\nexport { Knowledge };\n")
        write(tmp_path, f'{TS_ROOT}/knowledge/knowledge.ts', 'export class Knowledge {}\n')
        cat = catalogue(surface('Knowledge.__init__', 'knowledge/knowledge.ts', ctor_class='Knowledge'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH, finding.detail()

    def test_an_export_inside_a_comment_or_string_does_not_count(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts',
              "// export { Task } from './workflows';\n"
              "const sample = \"export { Task } from './workflows'\";\n"
              "export { Agent } from './agent';\n")
        write(tmp_path, f'{TS_ROOT}/agent.ts', 'export class Agent {}\n')
        write(tmp_path, f'{TS_ROOT}/workflows.ts', 'export class Task {}\n')
        cat = catalogue(surface('Task.__init__', 'workflows.ts', ctor_class='Task'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_NOT_EXPORTED

    def test_an_alias_the_barrel_exports_is_accepted(self, tmp_path):
        """Python exports the team class as PraisonAIAgents; TypeScript as AgentTeam."""
        write(tmp_path, f'{TS_ROOT}/index.ts', "export { AgentTeam } from './agent/team';\n")
        write(tmp_path, f'{TS_ROOT}/agent/team.ts', 'export class AgentTeam {}\n')
        cat = catalogue(surface('AgentTeam.__init__', 'agent/team.ts', ctor_class='AgentTeam',
                                py_class='PraisonAIAgents', aliases=['Agents']))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MATCH, finding.detail()

    def test_a_type_only_export_is_reported_as_a_type(self, tmp_path):
        """`import { LLM }` yielding an interface is not a constructible class."""
        write(tmp_path, f'{TS_ROOT}/index.ts', "export type { LLM } from './llm';\n")
        write(tmp_path, f'{TS_ROOT}/llm/index.ts',
              'export interface LLM { generate(): void }\nexport class BaseLLM implements LLM { generate() {} }\n')
        cat = catalogue(surface('LLM.__init__', 'llm/index.ts', ctor_class='BaseLLM'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MISMATCH
        assert 'interface' in finding.detail() and 'not constructible' in finding.detail()


class TestMethodSurfacesUseTheOwningClass:
    def test_a_method_surface_checks_the_class_it_belongs_to(self, tmp_path):
        two_tasks(tmp_path)
        cat = catalogue(surface('Task.execute', 'agent/types.ts', cls='Task',
                                kind='method', name='execute'))
        finding, = E.check_export_identity(tmp_path, cat)
        assert finding.status == E.STATUS_MISMATCH
        assert finding.validated.name == 'Task'


# ---------------------------------------------------------- explicit "why not"

class TestExplicitReason:
    def test_a_signed_reason_downgrades_the_failure_to_a_warning(self, tmp_path):
        two_tasks(tmp_path)
        cat = catalogue(surface(
            'Task.__init__', 'agent/types.ts', ctor_class='Task',
            export_identity={'reason': 'the ported Task lives in agent/types.ts until #1234 lands',
                             'owner': 'praisonai-ts'},
        ))
        findings = E.check_export_identity(tmp_path, cat)
        assert findings[0].status == E.STATUS_MISMATCH, 'the mismatch must still be detected'
        assert findings[0].ok, 'a signed reason accepts it'
        evaluation = C.evaluate_export_identity(findings, C.Evaluation())
        assert evaluation.ok, evaluation.failures
        assert '#1234' in evaluation.warnings[0], 'the reason is printed, not hidden'

    def test_a_reason_without_an_owner_is_a_tooling_error(self, tmp_path):
        path = tmp_path / 'surface.yaml'
        path.write_text(
            'surfaces:\n'
            '  - key: Task.__init__\n'
            '    python: {file: task/task.py, class: Task, function: __init__}\n'
            '    typescript: {file: agent/types.ts, kind: interface, name: TaskConfig}\n'
            '    export_identity: {reason: because}\n',
            encoding='utf-8')
        with pytest.raises(C.ToolingError, match='owner'):
            C.load_surfaces(path)

    def test_control_a_reason_with_an_owner_loads(self, tmp_path):
        path = tmp_path / 'surface.yaml'
        path.write_text(
            'surfaces:\n'
            '  - key: Task.__init__\n'
            '    python: {file: task/task.py, class: Task, function: __init__}\n'
            '    typescript: {file: agent/types.ts, kind: interface, name: TaskConfig}\n'
            '    export_identity: {reason: because, owner: praisonai-ts}\n',
            encoding='utf-8')
        cat = C.load_surfaces(path)
        assert cat.surfaces[0].export_identity['owner'] == 'praisonai-ts'


# ------------------------------------------------------------- tooling errors

class TestToolingFailures:
    def test_a_missing_barrel_is_a_tooling_error_not_a_pass(self, tmp_path):
        (tmp_path / TS_ROOT).mkdir(parents=True)
        cat = catalogue(surface('Task.__init__', 'agent/types.ts', ctor_class='Task'))
        with pytest.raises(FileNotFoundError, match='index.ts'):
            E.check_export_identity(tmp_path, cat)
        with pytest.raises(C.ToolingError, match='export identity'):
            C.run_extra_checks(tmp_path, cat)

    def test_an_empty_barrel_is_a_tooling_error_not_a_pass(self, tmp_path):
        write(tmp_path, f'{TS_ROOT}/index.ts', '// nothing here\n')
        cat = catalogue(surface('Task.__init__', 'agent/types.ts', ctor_class='Task'))
        with pytest.raises(FileNotFoundError, match='exports nothing'):
            E.check_export_identity(tmp_path, cat)


# ------------------------------------------------------------ the real repo

class TestTheRealRepository:
    """
    Pins what the check says about this checkout.

    These assertions are meant to break the day the divergence is closed. When
    one fails because ``surface.yaml`` now points at the exported symbol (or the
    package now exports the validated one), delete the assertion -- do not
    re-point ``surface.yaml`` at whatever keeps the test quiet.
    """

    def findings(self):
        cat = C.load_surfaces()
        return {f.surface: f for f in E.check_export_identity(REPO_ROOT, cat)}

    def test_every_curated_surface_is_reported_on(self):
        cat = C.load_surfaces()
        assert set(self.findings()) == {s.key for s in cat.surfaces}

    def test_task_init_validates_a_task_no_caller_can_import(self):
        finding = self.findings()['Task.__init__']
        assert finding.status == E.STATUS_MISMATCH
        assert finding.validated.file.endswith('agent/types.ts')
        assert finding.exported.file.endswith('workflows/index.ts')

    def test_agent_init_is_the_control_and_matches(self):
        finding = self.findings()['Agent.__init__']
        assert finding.status == E.STATUS_MATCH, finding.detail()
        assert finding.exported.file.endswith('agent/simple.ts')


# --------------------------------------------------------------------- CLI

class TestIdentityCli:
    def test_identity_mode_exits_1_while_a_surface_validates_an_unexported_symbol(self, capsys):
        code = C.main(['--identity', '--repo-root', str(REPO_ROOT)])
        out = capsys.readouterr().out
        assert code == C.EXIT_PARITY, out
        assert 'Task.__init__' in out
        assert 'workflows/index.ts' in out

    def test_identity_mode_needs_no_node(self, monkeypatch, capsys):
        """The barrel walk is pure Python; only the method inventory shells out."""
        monkeypatch.setattr(C.shutil, 'which', lambda name: None)
        code = C.main(['--identity', '--repo-root', str(REPO_ROOT)])
        assert code == C.EXIT_PARITY
        assert 'node' not in capsys.readouterr().err

class TestBaselineRatchet:
    """The two inventory checks ratchet against a recorded baseline.

    165 pre-existing divergences as hard failures would redden main and block
    every unrelated change, and a gate everyone routes around stops being a
    gate. So the known set is recorded and only growth fails -- the same shape
    that already works for the behaviour ledger. Proved on the real repo by
    making `Agent.steer` private: exit 1, naming `Agent.steer`.
    """

    def test_a_key_in_the_baseline_does_not_fail(self, tmp_path):
        ev = C.Evaluation()
        C.ratchet_against_baseline({'methods': ['Agent.steer']}, 'methods', ['Agent.steer'], ev)
        assert ev.failures == []

    def test_a_key_absent_from_the_baseline_fails_and_is_named(self, tmp_path):
        ev = C.Evaluation()
        C.ratchet_against_baseline({'methods': ['Agent.run']}, 'methods', ['Agent.run', 'Agent.steer'], ev)
        assert len(ev.failures) == 1 and 'Agent.steer' in ev.failures[0]

    def test_closing_one_is_a_note_not_a_failure(self):
        """Control: progress must never read as a regression."""
        ev = C.Evaluation()
        C.ratchet_against_baseline({'methods': ['Agent.run', 'Agent.steer']}, 'methods', ['Agent.run'], ev)
        assert ev.failures == []
        assert any('closed since the baseline' in w for w in ev.warnings)

    def test_the_baseline_survives_a_write_read_round_trip(self, tmp_path):
        (tmp_path / 'src/praisonai/praisonai/_dev/parity/signatures').mkdir(parents=True)
        C.write_inventory_baseline(tmp_path, ['Task.__init__'], ['Agent.run'])
        assert C.load_inventory_baseline(tmp_path) == {'identity': ['Task.__init__'], 'methods': ['Agent.run']}

    def test_a_missing_baseline_reads_as_empty_not_as_clean(self, tmp_path):
        """Control: no file must not silently mean 'nothing outstanding'."""
        assert C.load_inventory_baseline(tmp_path) == {}

    def _write_baseline(self, tmp_path: Path, text: str) -> None:
        path = tmp_path / C.INVENTORY_BASELINE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def test_a_truncated_baseline_is_a_tooling_error_not_a_first_run(self, tmp_path):
        # A conflicted or half-written file must not read as "nothing recorded",
        # which would drop the ratchet to a first-run warning and let a fresh
        # divergence pass CI. It must fail loudly instead.
        self._write_baseline(tmp_path, '{"methods": ["Agent.run"')
        with pytest.raises(C.BaselineError):
            C.load_inventory_baseline(tmp_path)

    def test_a_baseline_that_is_not_an_object_is_a_tooling_error(self, tmp_path):
        self._write_baseline(tmp_path, '["Agent.run"]')
        with pytest.raises(C.BaselineError):
            C.load_inventory_baseline(tmp_path)

    def test_a_baseline_entry_that_is_not_a_list_is_a_tooling_error(self, tmp_path):
        self._write_baseline(tmp_path, '{"methods": "Agent.run"}')
        with pytest.raises(C.BaselineError):
            C.load_inventory_baseline(tmp_path)

    def test_baseline_error_is_a_tooling_error_so_the_cli_exits_two(self):
        # It maps to EXIT_TOOLING via the ToolingError handler, not EXIT_PARITY.
        assert issubclass(C.BaselineError, C.ToolingError)
