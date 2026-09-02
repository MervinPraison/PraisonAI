"""
Unit tests for Feature Parity Tracker.

Tests the Python and TypeScript feature extractors and the parity tracker generator.
"""

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _real_repo_root() -> Optional[Path]:
    """Walk up from this test file to the monorepo root, if the layout exists."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "src" / "praisonai-ts").is_dir() and (parent / "src" / "praisonai-agents").is_dir():
            return parent
    return None


REAL_REPO_ROOT = _real_repo_root()
requires_real_repo = pytest.mark.skipif(
    REAL_REPO_ROOT is None,
    reason="monorepo layout (src/praisonai-ts + src/praisonai-agents) not found above this test file",
)


def make_repo(
    root: Path,
    py_init: str = "_LAZY_IMPORTS = {}",
    ts_index: str = "",
    ts_files: Optional[Dict[str, str]] = None,
    rust_lib: Optional[str] = None,
    cli_features: Optional[Dict[str, str]] = None,
) -> Path:
    """Create a minimal monorepo layout under ``root`` and return it."""
    pkg_dir = root / "src" / "praisonai-agents" / "praisonaiagents"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text(py_init)

    ts_dir = root / "src" / "praisonai-ts" / "src"
    ts_dir.mkdir(parents=True, exist_ok=True)
    (ts_dir / "index.ts").write_text(ts_index)
    for rel, content in (ts_files or {}).items():
        target = ts_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    wrapper_dir = root / "src" / "praisonai" / "praisonai" / "cli" / "features"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    for name, content in (cli_features or {}).items():
        (wrapper_dir / f"{name}.py").write_text(content)

    if rust_lib is not None:
        rust_src = root / "src" / "praisonai-rust" / "praisonai" / "src"
        rust_src.mkdir(parents=True, exist_ok=True)
        (rust_src / "lib.rs").write_text(rust_lib)
    return root


def py_init_with(*names: str) -> str:
    """Build a ``_LAZY_IMPORTS`` block exporting the given names from agent.agent."""
    entries = ",\n".join(f"    '{n}': ('praisonaiagents.agent.agent', '{n}')" for n in names)
    return f"_LAZY_IMPORTS = {{\n{entries}\n}}\n"


def all_rows(tracker: dict) -> Dict[str, dict]:
    return {g['feature']: g for gaps in tracker['gapMatrix'].values() for g in gaps}


# ---------------------------------------------------------------------------
# Repo root discovery
# ---------------------------------------------------------------------------

class TestFindRepoRoot:
    """Tests for the shared _paths.find_repo_root helper."""

    def test_no_personal_fallback_path_in_source(self):
        """No parity module may hard-code a developer's home checkout."""
        from praisonai._dev import parity

        pkg_dir = Path(parity.__file__).parent
        feature_parity_modules = [
            "_paths.py", "generator.py", "python_extractor.py",
            "rust_extractor.py", "typescript_extractor.py",
        ]
        offenders = [
            name for name in feature_parity_modules
            if "/Users/praison" in (pkg_dir / name).read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_raises_when_layout_absent(self, monkeypatch, tmp_path):
        """With no monorepo above __file__ or cwd, a clear RuntimeError is raised."""
        from praisonai._dev.parity import _paths

        fake_module = tmp_path / "elsewhere" / "pkg" / "_paths.py"
        fake_module.parent.mkdir(parents=True)
        fake_module.write_text("")
        monkeypatch.setattr(_paths, "__file__", str(fake_module))
        monkeypatch.chdir(tmp_path)

        with pytest.raises(RuntimeError) as excinfo:
            _paths.find_repo_root()
        assert "--repo-root" in str(excinfo.value)

    def test_finds_layout_above_module_file(self, monkeypatch, tmp_path):
        """Control: the same setup succeeds once the layout exists above __file__."""
        from praisonai._dev.parity import _paths

        root = make_repo(tmp_path / "repo")
        fake_module = root / "src" / "praisonai" / "praisonai" / "_dev" / "parity" / "_paths.py"
        fake_module.parent.mkdir(parents=True)
        fake_module.write_text("")
        monkeypatch.setattr(_paths, "__file__", str(fake_module))
        monkeypatch.chdir(tmp_path)  # cwd deliberately outside the repo

        assert _paths.find_repo_root() == root.resolve()

    def test_extractors_default_to_discovered_root(self, monkeypatch, tmp_path):
        """Every extractor and the generator use the shared discovery when given no root."""
        from praisonai._dev.parity import _paths
        from praisonai._dev.parity.generator import ParityTrackerGenerator
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor
        from praisonai._dev.parity.rust_extractor import RustFeatureExtractor
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        root = make_repo(tmp_path / "repo")
        fake_module = root / "src" / "praisonai" / "praisonai" / "_dev" / "parity" / "_paths.py"
        fake_module.parent.mkdir(parents=True)
        fake_module.write_text("")
        monkeypatch.setattr(_paths, "__file__", str(fake_module))
        monkeypatch.chdir(tmp_path)

        for cls in (PythonFeatureExtractor, RustFeatureExtractor, TypeScriptFeatureExtractor, ParityTrackerGenerator):
            assert cls().repo_root == root.resolve(), cls.__name__


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------

class TestPythonFeatureExtractor:
    """Tests for PythonFeatureExtractor."""

    def test_extract_lazy_imports(self):
        """Test extraction of _LAZY_IMPORTS dictionary."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor

        mock_init = '''
_LAZY_IMPORTS = {
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
    'Tool': ('praisonaiagents.tools.base', 'Tool'),
}
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=mock_init)
            init_file = root / "src" / "praisonai-agents" / "praisonaiagents" / "__init__.py"

            extractor = PythonFeatureExtractor(root)
            lazy_imports = extractor._extract_lazy_imports(init_file)

            assert 'Agent' in lazy_imports
            assert lazy_imports['Agent'] == ('praisonaiagents.agent.agent', 'Agent')
            assert 'Tool' in lazy_imports

    def test_extract_all_exports(self):
        """Test extraction of __all__ list."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor

        mock_init = '''
__all__ = [
    'Agent',
    'Tool',
    'Memory',
]
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=mock_init)
            init_file = root / "src" / "praisonai-agents" / "praisonaiagents" / "__init__.py"

            extractor = PythonFeatureExtractor(root)
            all_exports = extractor._extract_all_exports(init_file)

            assert 'Agent' in all_exports
            assert 'Tool' in all_exports
            assert 'Memory' in all_exports

    def test_categorize_module_path(self):
        """Test categorization of module paths."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PythonFeatureExtractor(make_repo(Path(tmpdir)))

            assert extractor._categorize('praisonaiagents.agent.agent') == 'agent'
            assert extractor._categorize('praisonaiagents.tools.base') == 'tools'
            assert extractor._categorize('praisonaiagents.memory.memory') == 'memory'
            assert extractor._categorize('praisonaiagents.workflows') == 'workflows'
            assert extractor._categorize('praisonaiagents.unknown') == 'other'

    def test_infer_kind(self):
        """Test inference of export kind from name."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PythonFeatureExtractor(make_repo(Path(tmpdir)))

            assert extractor._infer_kind('Agent') == 'class'
            assert extractor._infer_kind('MemoryConfig') == 'type'
            assert extractor._infer_kind('ToolResult') == 'type'
            assert extractor._infer_kind('HandoffError') == 'type'
            assert extractor._infer_kind('get_tool') == 'function'
            assert extractor._infer_kind('create_agent') == 'function'
            assert extractor._infer_kind('RECOMMENDED_PROMPT_PREFIX') == 'constant'

    def test_extract_cli_features(self):
        """Test extraction of CLI features from wrapper."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), cli_features={
                "chat": "# chat feature",
                "code": "# code feature",
                "_internal": "# internal, should be ignored",
            })

            extractor = PythonFeatureExtractor(root)
            cli_features = extractor._extract_cli_features()

            assert 'chat' in cli_features
            assert 'code' in cli_features
            assert '_internal' not in cli_features


# ---------------------------------------------------------------------------
# TypeScript extractor
# ---------------------------------------------------------------------------

class TestTypeScriptFeatureExtractor:
    """Tests for TypeScriptFeatureExtractor."""

    def test_extract_exports(self):
        """Test extraction of TypeScript exports."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        mock_index = '''
export { Agent, ImageAgent } from './agent';
export { Tool, BaseTool } from './tools';
export type { AgentConfig, ToolConfig } from './types';
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), ts_index=mock_index)
            features = TypeScriptFeatureExtractor(root).extract()

            export_names = {e.name for e in features.exports}
            assert 'Agent' in export_names
            assert 'ImageAgent' in export_names
            assert 'Tool' in export_names
            assert 'BaseTool' in export_names
            assert 'AgentConfig' in export_names
            assert 'ToolConfig' in export_names

    def test_parse_export_names_with_alias(self):
        """Test parsing export names with 'as' alias."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = TypeScriptFeatureExtractor(make_repo(Path(tmpdir)))

            names = extractor._parse_export_names("Agent, Tool as MyTool, Memory")
            assert names == ['Agent', 'MyTool', 'Memory']

    def test_categorize_source_path(self):
        """Test categorization of TypeScript source paths."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = TypeScriptFeatureExtractor(make_repo(Path(tmpdir)))

            assert extractor._categorize('./agent') == 'agent'
            assert extractor._categorize('./agent/index') == 'agent'
            assert extractor._categorize('./tools') == 'tools'
            assert extractor._categorize('./memory') == 'memory'
            assert extractor._categorize('./unknown') == 'other'

    def test_export_star_resolves_target_module(self):
        """`export * from './session'` surfaces the declarations of src/session/index.ts."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        session_index = '''
// a comment mentioning export class Ghost {} must be ignored
/* export function alsoGhost() {} */
export interface SessionConfig { id: string }
export type SessionStatus = 'a' | 'b';
export class Session {}
export abstract class BaseSession {}
export async function openSession() {}
export const SESSION_VERSION = 1;
const foo = 1;
export { foo as bar };
export * from './store';
'''
        store = '''
export class FileStore {}
export * from './index';  // circular — must not recurse forever
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                ts_index="export * from './session';\n",
                ts_files={"session/index.ts": session_index, "session/store.ts": store},
            )
            features = TypeScriptFeatureExtractor(root).extract()
            by_name = features.get_exports_by_name()

            for expected in ('Session', 'BaseSession', 'openSession', 'SESSION_VERSION',
                             'bar', 'SessionConfig', 'SessionStatus', 'FileStore'):
                assert expected in by_name, expected
                assert by_name[expected][0].source_file == './session'

            assert 'foo' not in by_name            # alias side wins
            assert 'Ghost' not in by_name          # inside a line comment
            assert 'alsoGhost' not in by_name      # inside a block comment
            assert by_name['SessionConfig'][0].is_type is True
            assert by_name['SessionStatus'][0].is_type is True
            assert by_name['Session'][0].is_type is False
            assert 'session' in features.modules
            assert 'Session' in features.modules['session'].exports

    def test_export_star_resolves_single_file_module(self):
        """`export * from './tools/arxivTools'` resolves to src/tools/arxivTools.ts."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                ts_index="export * from './tools/arxivTools';\n",
                ts_files={"tools/arxivTools.ts": "export class ArxivSearchTool {}\n"},
            )
            names = TypeScriptFeatureExtractor(root).extract().get_export_names()
            assert 'ArxivSearchTool' in names

    def test_module_without_star_export_stays_invisible(self):
        """Control: declarations in a module that index.ts does not star-export are not counted."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                ts_index="export { Agent } from './agent';\n",
                ts_files={"session/index.ts": "export class Session {}\n"},
            )
            names = TypeScriptFeatureExtractor(root).extract().get_export_names()
            assert 'Agent' in names
            assert 'Session' not in names

    def test_export_star_depth_limit(self):
        """A chain deeper than the limit stops instead of walking forever."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        files = {}
        for i in range(10):
            files[f"chain/l{i}.ts"] = f"export class L{i} {{}}\nexport * from './l{i + 1}';\n"
        files["chain/l10.ts"] = "export class L10 {}\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), ts_index="export * from './chain/l0';\n", ts_files=files)
            names = TypeScriptFeatureExtractor(root).extract().get_export_names()
            assert 'L0' in names and 'L3' in names
            assert 'L10' not in names


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class TestParityTrackerGenerator:
    """Tests for ParityTrackerGenerator."""

    def test_generate_structure(self):
        """Test that generated tracker has correct structure."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';")
            tracker = ParityTrackerGenerator(root).generate()

            for key in ('version', 'lastUpdated', 'summary', 'pythonCoreSDK',
                        'pythonWrapper', 'typescriptSDK', 'gapMatrix'):
                assert key in tracker

    def test_summary_counts(self):
        """Test that summary counts are correct."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                py_init='''
_LAZY_IMPORTS = {
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
    'Tool': ('praisonaiagents.tools.base', 'Tool'),
    'Memory': ('praisonaiagents.memory.memory', 'Memory'),
}
''',
                ts_index="export { Agent } from './agent';",
                cli_features={"chat": ""},
            )
            tracker = ParityTrackerGenerator(root).generate()

            assert tracker['summary']['pythonCoreFeatures'] == 3
            assert tracker['summary']['typescriptFeatures'] == 1
            assert tracker['summary']['gapCount'] == 2  # Tool and Memory missing
            assert tracker['summary']['stubCount'] == 0
            assert tracker['summary']['pythonWrapperFeatures'] == 1  # chat

    def test_gap_matrix_status(self):
        """Test that gap matrix correctly identifies DONE vs TODO."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent', 'Tool'),
                             ts_index="export { Agent } from './agent';")
            rows = all_rows(ParityTrackerGenerator(root).generate())

            assert rows['Agent']['status'] == 'DONE'
            assert rows['Agent']['typescript'] is True
            assert rows['Tool']['status'] == 'TODO'
            assert rows['Tool']['typescript'] is False

    def test_output_paths_are_relative(self):
        """JSON 'path' fields are repo-relative posix paths, never absolute."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';", rust_lib="")
            generator = ParityTrackerGenerator(root)
            tracker = generator.generate()
            rust_tracker = generator.generate_rust()

            assert tracker['pythonCoreSDK']['path'] == 'src/praisonai-agents/praisonaiagents'
            assert tracker['pythonWrapper']['path'] == 'src/praisonai/praisonai'
            assert tracker['typescriptSDK']['path'] == 'src/praisonai-ts/src'
            assert rust_tracker['rustSDK']['path'] == 'src/praisonai-rust'

            # Control: the relative paths still resolve to the real directories
            for p in (tracker['pythonCoreSDK']['path'], tracker['typescriptSDK']['path'],
                      rust_tracker['rustSDK']['path']):
                assert not Path(p).is_absolute()
                assert (generator.repo_root / p).is_dir()
            assert str(root.resolve()) not in json.dumps(tracker)

    def test_last_updated_preserved_when_content_unchanged(self):
        """A rerun with identical content keeps the committed lastUpdated."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';", rust_lib="")
            generator = ParityTrackerGenerator(root)
            assert generator.write_typescript() == 0
            assert generator.write_rust() == 0

            # Pretend the committed file is old
            for path in (generator.ts_output, generator.rust_output):
                data = json.loads(path.read_text())
                data['lastUpdated'] = '2000-01-01'
                path.write_text(json.dumps(data, indent=2) + '\n')

            assert ParityTrackerGenerator(root).generate()['lastUpdated'] == '2000-01-01'
            assert ParityTrackerGenerator(root).generate_rust()['lastUpdated'] == '2000-01-01'

            # Markdown derives from the tracker, so it follows
            assert "**Last Updated:** 2000-01-01" in ParityTrackerGenerator(root).generate_markdown()

    def test_last_updated_refreshed_when_content_changes(self):
        """Control: once the content differs, lastUpdated moves to today."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';", rust_lib="")
            generator = ParityTrackerGenerator(root)
            generator.write_typescript()
            generator.write_rust()
            for path in (generator.ts_output, generator.rust_output):
                data = json.loads(path.read_text())
                data['lastUpdated'] = '2000-01-01'
                path.write_text(json.dumps(data, indent=2) + '\n')

            # Add a Python export → content changes
            init_file = root / "src" / "praisonai-agents" / "praisonaiagents" / "__init__.py"
            init_file.write_text(py_init_with('Agent', 'Tool'))

            today = date.today().isoformat()
            assert ParityTrackerGenerator(root).generate()['lastUpdated'] == today
            assert ParityTrackerGenerator(root).generate_rust()['lastUpdated'] == today

    def test_markdown_check_ignores_date_line_only(self):
        """Check mode tolerates a different date line but not a different body."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';")
            generator = ParityTrackerGenerator(root)
            assert generator.write_typescript_markdown() == 0

            md = generator.ts_md_output.read_text()
            aged = md.replace(f"**Last Updated:** {date.today().isoformat()}", "**Last Updated:** 2000-01-01")
            assert aged != md
            generator.ts_md_output.write_text(aged)
            assert generator.write_typescript_markdown(check=True) == 0

            # Control: a body change is still detected
            generator.ts_md_output.write_text(aged.replace("| `Agent` |", "| `Agentt` |"))
            assert generator.write_typescript_markdown(check=True) == 1

    def test_export_star_names_count_as_present(self):
        """A Python name only reachable through `export *` is DONE, not missing."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                py_init=py_init_with('Session', 'bar'),
                ts_index="export * from './session';\n",
                ts_files={"session/index.ts": "export class Session {}\nconst foo = 1;\nexport { foo as bar };\n"},
            )
            tracker = ParityTrackerGenerator(root).generate()
            rows = all_rows(tracker)
            assert rows['Session']['status'] == 'DONE'
            assert rows['bar']['status'] == 'DONE'
            assert tracker['summary']['gapCount'] == 0

    def test_export_star_control_without_star_is_missing(self):
        """Control: the same module not star-exported leaves the names missing."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                py_init=py_init_with('Session', 'bar'),
                ts_index="export { Agent } from './agent';\n",
                ts_files={"session/index.ts": "export class Session {}\nconst foo = 1;\nexport { foo as bar };\n"},
            )
            tracker = ParityTrackerGenerator(root).generate()
            rows = all_rows(tracker)
            assert rows['Session']['status'] == 'TODO'
            assert rows['bar']['status'] == 'TODO'
            assert tracker['summary']['gapCount'] == 2

    def test_camel_case_fallback_marks_done_with_ts_name(self):
        """snake_case Python names match their camelCase TS spelling."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('discover_skills', 'load_skill'),
                             ts_index="export { discoverSkills, loadSkill } from './skills';")
            tracker = ParityTrackerGenerator(root).generate()
            rows = all_rows(tracker)

            assert rows['discover_skills']['status'] == 'DONE'
            assert rows['discover_skills']['typescript'] is True
            assert rows['discover_skills']['tsName'] == 'discoverSkills'
            assert rows['load_skill']['tsName'] == 'loadSkill'
            assert tracker['summary']['gapCount'] == 0
            assert "`discover\\_skills` → `discoverSkills`" in ParityTrackerGenerator(root).generate_markdown()

    def test_camel_case_fallback_control_requires_exact_camel(self):
        """Control: a near-miss spelling, or a SCREAMING_CASE constant, stays missing."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('discover_skills', 'MAX_DEPTH', '__version__'),
                             ts_index="export { discoverSkillz, mAXDEPTH, version } from './skills';")
            tracker = ParityTrackerGenerator(root).generate()
            rows = all_rows(tracker)

            for name in ('discover_skills', 'MAX_DEPTH', '__version__'):
                assert rows[name]['status'] == 'TODO', name
                assert 'tsName' not in rows[name]
            assert tracker['summary']['gapCount'] == 3

    def test_ts_alias_mapping_is_honoured(self, monkeypatch):
        """An explicit TS_ALIAS_MAPPING entry counts as present; without it the name is missing."""
        from praisonai._dev.parity import generator as gen_mod
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Handoff'),
                             ts_index="export { Handover } from './agent';")
            assert all_rows(ParityTrackerGenerator(root).generate())['Handoff']['status'] == 'TODO'

            monkeypatch.setattr(ParityTrackerGenerator, 'TS_ALIAS_MAPPING', {'Handoff': 'Handover'})
            row = all_rows(ParityTrackerGenerator(root).generate())['Handoff']
            assert row['status'] == 'DONE'
            assert row['tsName'] == 'Handover'

    def test_summary_and_gap_matrix_agree(self):
        """gapCount / stubCount / priority counts equal what the gap matrix contains."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                py_init=py_init_with('Agent', 'CodeAgent', 'discover_skills', 'Missing'),
                ts_index=(
                    "export { Agent } from './agent';\n"
                    "export { CodeAgent } from './parity';\n"
                    "export { discoverSkills } from './skills';\n"
                ),
            )
            tracker = ParityTrackerGenerator(root).generate()
            rows = list(all_rows(tracker).values())
            summary = tracker['summary']

            assert summary['gapCount'] == sum(1 for r in rows if r['status'] == 'TODO') == 1
            assert summary['stubCount'] == sum(1 for r in rows if r['status'] == 'STUB') == 1
            assert sum(summary[f'priorityP{i}'] for i in range(4)) == summary['gapCount']

    def test_stub_only_provider_is_tagged_stub(self):
        """A name whose only TS provider is ./parity is STUB, not DONE."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('CodeAgent'),
                             ts_index="export { CodeAgent } from './parity';")
            generator = ParityTrackerGenerator(root)
            tracker = generator.generate()
            row = all_rows(tracker)['CodeAgent']

            assert row['status'] == 'STUB'
            assert row['typescript'] is True
            assert row['tsSource'] == './parity'
            assert tracker['summary']['stubCount'] == 1
            assert tracker['summary']['gapCount'] == 0

            md = generator.generate_markdown()
            assert "| `CodeAgent` | ✅ | ✅ | high | ⚠️ stub exported |" in md
            assert "(0 exported, 1 stub, 0 missing)" in md
            assert "parity" in md.split("## Summary")[0]  # header explains the shim

    def test_stub_control_real_provider_is_done(self):
        """Control: the same name also exported from ./agent is DONE with no tsSource."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(
                Path(tmpdir),
                py_init=py_init_with('CodeAgent'),
                ts_index="export { CodeAgent } from './parity';\nexport { CodeAgent } from './agent';\n",
            )
            generator = ParityTrackerGenerator(root)
            tracker = generator.generate()
            row = all_rows(tracker)['CodeAgent']

            assert row['status'] == 'DONE'
            assert 'tsSource' not in row
            assert tracker['summary']['stubCount'] == 0

            md = generator.generate_markdown()
            assert "| ⚠️ stub exported |" not in md
            assert "| `CodeAgent` | ✅ | ✅ | high | ✅ exported |" in md
            assert "(1 exported, 0 stub, 0 missing)" in md

    def test_markdown_states_it_measures_names_not_behaviour(self):
        """Markdown must disclose it measures exported names, not behaviour.

        Guards against the false-confidence bug where an exported-but-unreachable
        symbol (e.g. ApprovalCallback) is read as a working capability.
        """
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent', 'Tool'),
                             ts_index="export { Agent } from './agent';")
            md = ParityTrackerGenerator(root).generate_markdown()

            # Header discloses the methodology limitation
            assert "What this measures" in md
            assert "exported symbol name" in md
            # An exported name is labelled "exported", not "DONE"/"works"
            assert "✅ exported" in md
            assert "✅ DONE" not in md

    def test_write_typescript_creates_file(self):
        """Test that write_typescript creates the output file."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            # A non-empty surface: the generator now refuses a source it read
            # nothing from, because "0 exports" was indistinguishable from
            # "no gaps".
            generator = ParityTrackerGenerator(make_repo(
                Path(tmpdir),
                py_init=py_init_with('Agent'),
                ts_index='export { Agent } from "./agent";\n',
            ))
            assert generator.write_typescript() == 0
            assert generator.ts_output.exists()
            with open(generator.ts_output) as f:
                assert 'version' in json.load(f)

    def test_write_rust_creates_file(self):
        """Test that write_rust creates the output file."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir))
            (root / "src" / "praisonai-rust").mkdir(parents=True)

            generator = ParityTrackerGenerator(root)
            assert generator.write_rust() == 0
            assert generator.rust_output.exists()
            with open(generator.rust_output) as f:
                assert json.load(f)['status'] == 'NOT_STARTED'

    def test_rust_status_not_parity_achieved_while_gaps_remain(self):
        """More Rust exports than Python exports must not yield >100% or PARITY_ACHIEVED."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        rust_lib = "pub use agent::{Agent, Extra1, Extra2, Extra3};\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent', 'Tool'), rust_lib=rust_lib)
            tracker = ParityTrackerGenerator(root).generate_rust()

            assert tracker['summary']['rustFeatures'] > tracker['summary']['pythonCoreFeatures']
            assert tracker['summary']['gapCount'] == 1
            assert tracker['summary']['parityPercentage'] == 50.0
            assert tracker['status'] != 'PARITY_ACHIEVED'
            rows = all_rows(tracker)
            assert rows['Tool']['status'] == 'TODO'
            assert rows['Agent']['status'] == 'DONE'

    def test_rust_status_parity_achieved_when_no_gaps(self):
        """Control: every Python name exported by Rust → PARITY_ACHIEVED at 100%."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        rust_lib = "pub use agent::{Agent, Tool, Extra};\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent', 'Tool'), rust_lib=rust_lib)
            tracker = ParityTrackerGenerator(root).generate_rust()

            assert tracker['summary']['gapCount'] == 0
            assert tracker['summary']['parityPercentage'] == 100.0
            assert tracker['status'] == 'PARITY_ACHIEVED'

    def test_rust_alias_counts_as_done(self):
        """RUST_ALIAS_MAPPING entries match in the JSON gap matrix (as the markdown already did)."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = make_repo(Path(tmpdir), py_init=py_init_with('loop'),
                             rust_lib="pub use workflows::{loop_step};\n")
            row = all_rows(ParityTrackerGenerator(root).generate_rust())['loop']
            assert row['status'] == 'DONE'
            assert row['rustName'] == 'loop_step'

            # Control: without the alias the name is missing
            root2 = make_repo(Path(tmpdir) / "other", py_init=py_init_with('loop'),
                              rust_lib="pub use workflows::{loop_forever};\n")
            assert all_rows(ParityTrackerGenerator(root2).generate_rust())['loop']['status'] == 'TODO'


# ---------------------------------------------------------------------------
# generate_parity_tracker entry point
# ---------------------------------------------------------------------------

class TestGenerateParityTracker:
    """Tests for the generate_parity_tracker function."""

    def test_stdout_mode(self, capsys):
        """Test stdout mode prints JSON."""
        from praisonai._dev.parity.generator import generate_parity_tracker

        with tempfile.TemporaryDirectory() as tmpdir:
            # A non-empty surface: the generator now refuses a source it read
            # nothing from, because "0 exports" was indistinguishable from
            # "no gaps".
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index='export { Agent } from "./agent";\n')
            result = generate_parity_tracker(repo_root=root, stdout=True)

            assert result == 0
            captured = capsys.readouterr()
            assert 'version' in json.loads(captured.out)

    def test_check_mode_up_to_date(self):
        """Test check mode returns 0 when up to date."""
        from praisonai._dev.parity.generator import generate_parity_tracker

        with tempfile.TemporaryDirectory() as tmpdir:
            # A non-empty surface: the generator now refuses a source it read
            # nothing from, because "0 exports" was indistinguishable from
            # "no gaps".
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index='export { Agent } from "./agent";\n')
            generate_parity_tracker(repo_root=root, target='ts')
            assert generate_parity_tracker(repo_root=root, target='ts', check=True) == 0

    def test_check_mode_passes_from_different_cwd(self, monkeypatch):
        """Files written from one cwd verify from another (paths are repo-relative)."""
        from praisonai._dev.parity.generator import generate_parity_tracker

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as other_cwd:
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';", rust_lib="")
            monkeypatch.chdir(root)
            assert generate_parity_tracker(repo_root=root, target='all') == 0

            monkeypatch.chdir(other_cwd)
            assert generate_parity_tracker(repo_root=root, target='all', check=True) == 0

            # Control: drift is still caught from the other cwd
            init_file = root / "src" / "praisonai-agents" / "praisonaiagents" / "__init__.py"
            init_file.write_text(py_init_with('Agent', 'Tool'))
            assert generate_parity_tracker(repo_root=root, target='all', check=True) == 1

    def test_check_mode_fails_when_out_of_date(self):
        """Control for check mode: a stale tracker returns 1."""
        from praisonai._dev.parity.generator import generate_parity_tracker

        with tempfile.TemporaryDirectory() as tmpdir:
            # Non-empty on both sides so the generator produces a baseline
            # (an empty source is now refused before drift can be checked).
            root = make_repo(Path(tmpdir), py_init=py_init_with('Agent'),
                             ts_index="export { Agent } from './agent';")
            generate_parity_tracker(repo_root=root, target='ts')
            # Mutate the TypeScript surface: the committed tracker is now stale.
            (root / "src" / "praisonai-ts" / "src" / "index.ts").write_text(
                "export { Agent, Tool } from './agent';")
            assert generate_parity_tracker(repo_root=root, target='ts', check=True) == 1


# ---------------------------------------------------------------------------
# Integration against the real checkout (skipped when the layout is absent)
# ---------------------------------------------------------------------------

class TestRealExtraction:
    """Integration tests using the real PraisonAI repository."""

    @requires_real_repo
    def test_extract_real_python_features(self):
        """Test extraction from real Python SDK."""
        from praisonai._dev.parity.python_extractor import PythonFeatureExtractor

        features = PythonFeatureExtractor(REAL_REPO_ROOT).extract()

        assert len(features.exports) > 50
        export_names = {e.name for e in features.exports}
        assert 'Agent' in export_names
        assert 'Tool' in export_names or 'tool' in export_names
        assert 'Memory' in export_names
        assert len(features.modules) > 5
        assert 'agent' in features.modules

    @requires_real_repo
    def test_extract_real_typescript_features(self):
        """Test extraction from real TypeScript SDK, including export * targets."""
        from praisonai._dev.parity.typescript_extractor import TypeScriptFeatureExtractor

        features = TypeScriptFeatureExtractor(REAL_REPO_ROOT).extract()

        assert len(features.exports) > 10
        export_names = features.get_export_names()
        assert 'Agent' in export_names
        # Reachable only via `export * from './session'` in index.ts
        assert 'Session' in export_names

    @requires_real_repo
    def test_generate_real_tracker(self):
        """Test generating tracker from real repository with auto-discovered root."""
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        generator = ParityTrackerGenerator()
        assert generator.repo_root == REAL_REPO_ROOT.resolve()
        tracker = generator.generate()

        assert tracker['summary']['pythonCoreFeatures'] > 50
        assert tracker['summary']['typescriptFeatures'] > 10
        assert tracker['summary']['gapCount'] >= 0
        assert not Path(tracker['pythonCoreSDK']['path']).is_absolute()


class TestExtractorFailureIsNotParity:
    """A source the extractor could not read must fail, not report zero gaps.

    Both extractors swallow their errors and return an empty result, and every
    downstream number is a set difference -- so a missing or unparseable source
    produced a plausible tracker instead of an error. Measured before the fix:
    an unparseable ``__init__.py`` yielded ``{'pythonCoreFeatures': 0,
    'gapCount': 0}`` and exit 0, and CI would have committed that as "no gaps".
    """

    def _tree(self, tmpdir, init_source, index_source):
        pkg = Path(tmpdir) / "src" / "praisonai-agents" / "praisonaiagents"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(init_source)
        ts = Path(tmpdir) / "src" / "praisonai-ts" / "src"
        ts.mkdir(parents=True)
        (ts / "index.ts").write_text(index_source)
        return Path(tmpdir)

    def test_unparseable_python_source_raises_instead_of_reporting_no_gaps(self):
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._tree(tmpdir, "def broken(\n", 'export { Agent } from "./agent";\n')
            with pytest.raises(RuntimeError, match="0 exports"):
                ParityTrackerGenerator(root).generate()

    def test_unreadable_typescript_source_raises_too(self):
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._tree(
                tmpdir,
                '_LAZY_IMPORTS = {"Agent": ("praisonaiagents.agent", "Agent")}\n__all__ = ["Agent"]\n',
                "",  # present but exporting nothing
            )
            with pytest.raises(RuntimeError, match="TypeScript"):
                ParityTrackerGenerator(root).generate()

    def test_a_readable_source_still_generates__the_pair(self):
        # Without this, a generator that raised unconditionally would satisfy
        # both tests above and never produce a tracker again.
        from praisonai._dev.parity.generator import ParityTrackerGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._tree(
                tmpdir,
                '_LAZY_IMPORTS = {"Agent": ("praisonaiagents.agent", "Agent")}\n__all__ = ["Agent"]\n',
                'export { Agent } from "./agent";\n',
            )
            tracker = ParityTrackerGenerator(root).generate()
            assert tracker["summary"]["pythonCoreFeatures"] == 1
            assert tracker["summary"]["gapCount"] == 0
