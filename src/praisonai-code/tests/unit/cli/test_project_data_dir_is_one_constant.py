"""Project-local CLI data must live in the one canonical directory.

Nine CLI features each hard-coded ``.praison/<file>`` while the runtime reads
``.praisonai/`` (``praisonaiagents.paths``). That is not cosmetic: ``.praison``
is the FIRST entry of ``paths._PROJECT_MARKERS``, so the moment one of those
features creates ``./.praison/`` in a project whose config lives in
``./.praisonai/``, ``_config_dirname_for`` flips and the project's real
``.praisonai/config.toml`` silently stops being read.

Every assertion here is made against the shared constant, never a literal, so a
future drift back to ``.praison`` fails these tests rather than shipping.
"""

import json
import os
from pathlib import Path

import pytest

from praisonai_code.cli.configuration.paths import (
    LEGACY_PROJECT_DATA_DIRNAME,
    PROJECT_DATA_DIRNAME,
    get_knowledge_store_path,
    get_project_data_path,
    resolve_project_data_path,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty project directory, as cwd, with no PRAISONAI_PROJECT override."""
    monkeypatch.delenv("PRAISONAI_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestTheConstantItself:

    def test_matches_the_sdk_canonical_dir_name(self):
        from praisonaiagents.paths import DEFAULT_DIR_NAME

        assert PROJECT_DATA_DIRNAME == DEFAULT_DIR_NAME

    def test_the_legacy_name_is_not_the_canonical_one(self):
        assert LEGACY_PROJECT_DATA_DIRNAME != PROJECT_DATA_DIRNAME


class TestSettingsHandlersWriteToTheCanonicalDir:
    """thinking / compaction / output-style each owned a `.praison/*.json`."""

    HANDLERS = [
        ("praisonai_code.cli.features.thinking", "ThinkingHandler"),
        ("praisonai_code.cli.features.compaction", "CompactionHandler"),
        ("praisonai_code.cli.features.output_style", "OutputStyleHandler"),
    ]

    def _handlers(self):
        import importlib

        for mod_name, cls_name in self.HANDLERS:
            mod = importlib.import_module(mod_name)
            yield cls_name, getattr(mod, cls_name)

    def test_save_lands_under_the_canonical_dir(self, project):
        for name, cls in self._handlers():
            handler = cls()
            handler._save_config({"probe": name})
            written = Path(handler._get_config_write_path())
            assert written.parent == project / PROJECT_DATA_DIRNAME, name
            assert written.exists(), name

    def test_no_legacy_directory_is_created(self, project):
        for name, cls in self._handlers():
            cls()._save_config({"probe": name})
        assert not (project / LEGACY_PROJECT_DATA_DIRNAME).exists()

    def test_a_save_round_trips(self, project):
        for name, cls in self._handlers():
            handler = cls()
            handler._save_config({"probe": name})
            assert handler._load_config() == {"probe": name}, name

    def test_an_existing_legacy_file_is_still_read(self, project):
        """Data written before the fix must not be orphaned."""
        for name, cls in self._handlers():
            handler = cls()
            legacy = project / LEGACY_PROJECT_DATA_DIRNAME / handler.CONFIG_NAME
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(json.dumps({"legacy": name}))
            assert handler._load_config() == {"legacy": name}, name

    def test_saving_over_a_legacy_file_writes_the_canonical_one(self, project):
        for name, cls in self._handlers():
            handler = cls()
            legacy = project / LEGACY_PROJECT_DATA_DIRNAME / handler.CONFIG_NAME
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(json.dumps({"legacy": name}))
            handler._save_config({"fresh": name})
            canonical = project / PROJECT_DATA_DIRNAME / handler.CONFIG_NAME
            assert canonical.exists(), name
            assert json.loads(canonical.read_text()) == {"fresh": name}, name


class TestTheProjectConfigIsNoLongerHijacked:
    """The user-visible consequence: which config.toml gets read."""

    def test_saving_a_setting_does_not_change_the_resolved_project_config(
        self, project
    ):
        (project / PROJECT_DATA_DIRNAME).mkdir()
        (project / PROJECT_DATA_DIRNAME / "config.toml").write_text(
            '[model]\ndefault = "from-the-project"\n'
        )

        from praisonai_code.cli.configuration.loader import ConfigLoader
        from praisonai_code.cli.features.thinking import ThinkingHandler

        before = ConfigLoader().load().model.default
        assert before == "from-the-project"

        ThinkingHandler()._save_config({"level": "high"})

        after = ConfigLoader().load().model.default
        assert after == before, (
            "saving a thinking budget silently changed which config.toml is read"
        )


class TestQueueDefaults:

    def test_config_default_uses_the_constant(self):
        from praisonai_code.cli.features.queue.models import (
            DEFAULT_QUEUE_DB_PATH,
            QueueConfig,
        )

        assert DEFAULT_QUEUE_DB_PATH.startswith(PROJECT_DATA_DIRNAME + "/")
        assert QueueConfig().db_path == DEFAULT_QUEUE_DB_PATH

    def test_from_dict_default_uses_the_constant(self):
        from praisonai_code.cli.features.queue.models import (
            DEFAULT_QUEUE_DB_PATH,
            QueueConfig,
        )

        assert QueueConfig.from_dict({}).db_path == DEFAULT_QUEUE_DB_PATH

    def test_persistence_default_uses_the_constant(self, project):
        from praisonai_code.cli.features.queue.models import DEFAULT_QUEUE_DB_PATH
        from praisonai_code.cli.features.queue.persistence import QueuePersistence

        assert QueuePersistence().db_path == DEFAULT_QUEUE_DB_PATH

    def test_persistence_still_opens_an_existing_legacy_database(self, project):
        legacy = project / LEGACY_PROJECT_DATA_DIRNAME / "queue.db"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b"")

        from praisonai_code.cli.features.queue.persistence import QueuePersistence

        assert Path(QueuePersistence().db_path).name == "queue.db"
        assert LEGACY_PROJECT_DATA_DIRNAME in QueuePersistence().db_path


class TestKnowledgeStorePath:

    def test_default_is_under_the_canonical_dir(self, project):
        assert get_knowledge_store_path("docs") == (
            f"./{PROJECT_DATA_DIRNAME}/knowledge/docs"
        )

    def test_an_existing_legacy_store_is_still_used(self, project):
        legacy = project / LEGACY_PROJECT_DATA_DIRNAME / "knowledge" / "docs"
        legacy.mkdir(parents=True)
        assert get_knowledge_store_path("docs") == (
            f"./{LEGACY_PROJECT_DATA_DIRNAME}/knowledge/docs"
        )

    def test_every_knowledge_consumer_agrees(self, project):
        """config_loader, unified_schema and retrieval must not diverge."""
        from praisonai_code.cli.config_loader import RAGCliConfig

        cfg = RAGCliConfig(collection="docs")
        path = cfg.to_knowledge_config()["vector_store"]["config"]["path"]
        assert path == get_knowledge_store_path("docs")

    def test_no_source_file_still_hard_codes_the_legacy_knowledge_path(self):
        import praisonai_code

        root = Path(praisonai_code.__file__).parent
        offenders = []
        for py in root.rglob("*.py"):
            text = py.read_text(errors="ignore")
            if f'"./{LEGACY_PROJECT_DATA_DIRNAME}/knowledge/' in text:
                offenders.append(str(py))
        assert not offenders, offenders


class TestDoctorScansWhatTheRuntimeReads:
    """`doctor` validated `.praison/skills` while the loader reads
    `.praisonai/skills`, so it reported a different skill than `skills list`."""

    def _make_skill(self, parent, name):
        d = parent / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: a probe skill\n---\nBody.\n"
        )
        return d

    def test_the_project_skills_dir_doctor_finds_is_the_canonical_one(
        self, project, monkeypatch
    ):
        monkeypatch.setenv("PRAISONAI_HOME", str(project / "home"))
        self._make_skill(project / PROJECT_DATA_DIRNAME / "skills", "newskill")
        self._make_skill(project / LEGACY_PROJECT_DATA_DIRNAME / "skills", "ghost")

        from praisonai_code.cli.features.doctor.checks import skills_checks

        dirs = skills_checks._find_skills_dirs()
        assert str(project / PROJECT_DATA_DIRNAME / "skills") in dirs
        assert str(project / LEGACY_PROJECT_DATA_DIRNAME / "skills") not in dirs

    def test_doctor_and_the_loader_report_the_same_project_skill(
        self, project, monkeypatch
    ):
        monkeypatch.setenv("PRAISONAI_HOME", str(project / "home"))
        self._make_skill(project / PROJECT_DATA_DIRNAME / "skills", "newskill")
        self._make_skill(project / LEGACY_PROJECT_DATA_DIRNAME / "skills", "ghost")

        from praisonaiagents.skills.discovery import discover_skills

        from praisonai_code.cli.features.doctor.checks import skills_checks

        loader_names = {s.name for s in discover_skills(include_defaults=True)}
        doctor_names = set()
        for d in skills_checks._find_skills_dirs():
            for child in Path(d).iterdir():
                if child.is_dir() and (child / "SKILL.md").exists():
                    doctor_names.add(child.name)

        assert "newskill" in loader_names and "newskill" in doctor_names
        assert "ghost" not in loader_names, "the loader read the legacy dir"
        assert "ghost" not in doctor_names, (
            "doctor validated a skill directory the runtime never reads"
        )

    def test_the_empty_state_names_the_canonical_dir(self):
        from praisonai_code.cli.features.doctor.checks import skills_checks

        hint = skills_checks._skills_dir_hint()
        assert hint.startswith(PROJECT_DATA_DIRNAME + "/")
        assert not hint.startswith(LEGACY_PROJECT_DATA_DIRNAME + "/")


class TestFileHistoryUsesTheSdkDataRoot:

    def test_history_dir_is_under_the_sdk_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
        import praisonaiagents.paths as core_paths

        core_paths._clear_cache()

        from praisonai_code.cli.features import file_history

        assert file_history._default_history_dir() == str(
            core_paths.get_data_dir() / "history"
        )
