"""Tests for skill provenance, usage telemetry, archival, and rollback."""

from pathlib import Path
import tempfile


def _make_manager(tmpdir, name="my-skill", body="Original body."):
    from praisonaiagents.skills.manager import SkillManager

    skill_dir = Path(tmpdir) / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: A test skill
---

{body}
"""
    )
    manager = SkillManager()
    manager.add_skill(str(skill_dir))
    return manager


class TestProvenanceFields:
    def test_properties_have_provenance_defaults(self):
        from praisonaiagents.skills.models import SkillProperties

        props = SkillProperties(name="x", description="y")
        assert props.agent_created is False
        assert props.created_at is None
        assert props.use_count == 0
        assert props.last_used is None
        assert props.patch_count == 0

    def test_to_dict_includes_provenance(self):
        from praisonaiagents.skills.models import SkillProperties

        props = SkillProperties(
            name="x",
            description="y",
            agent_created=True,
            created_at="2024-01-01T00:00:00+00:00",
            use_count=3,
            patch_count=1,
        )
        d = props.to_dict()
        assert d["agent-created"] is True
        assert d["created-at"] == "2024-01-01T00:00:00+00:00"
        assert d["use-count"] == 3
        assert d["patch-count"] == 1

    def test_parser_reads_provenance(self):
        from praisonaiagents.skills.parser import read_properties

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "prov-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: prov-skill
description: provenance test
agent-created: true
created-at: "2024-01-01T00:00:00+00:00"
use-count: 5
patch-count: 2
---

Body.
"""
            )
            props = read_properties(skill_dir)
            assert props.agent_created is True
            assert props.created_at == "2024-01-01T00:00:00+00:00"
            assert props.use_count == 5
            assert props.patch_count == 2

    def test_idle_days_none_without_timestamps(self):
        from praisonaiagents.skills.models import SkillProperties

        props = SkillProperties(name="x", description="y")
        assert props.idle_days is None

    def test_idle_days_positive_for_old_timestamp(self):
        from praisonaiagents.skills.models import SkillProperties

        props = SkillProperties(
            name="x", description="y", created_at="2000-01-01T00:00:00+00:00"
        )
        assert props.idle_days is not None
        assert props.idle_days > 1000


class TestCreateProvenance:
    def test_create_skill_marks_agent_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonaiagents.skills import manager as manager_mod

            orig = manager_mod.get_default_skill_dirs
            manager_mod.get_default_skill_dirs = lambda: [tmpdir]
            try:
                manager = manager_mod.SkillManager()
                result = manager.create_skill("scrape-x", "Do the scrape.")
                assert result["success"] is True
                skill = manager.get_skill("scrape-x")
                assert skill.properties.agent_created is True
                assert skill.properties.created_at is not None
                assert skill.properties.use_count == 0
            finally:
                manager_mod.get_default_skill_dirs = orig


class TestUsageTelemetry:
    def test_invoke_increments_use_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            manager.invoke("my-skill")
            skill = manager.get_skill("my-skill")
            assert skill.properties.use_count == 1
            assert skill.properties.last_used is not None

    def test_get_instructions_increments_use_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            manager.get_instructions("my-skill")
            skill = manager.get_skill("my-skill")
            assert skill.properties.use_count == 1

    def test_use_count_persists_to_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            manager.get_instructions("my-skill")
            content = (Path(tmpdir) / "my-skill" / "SKILL.md").read_text()
            assert "use-count: 1" in content
            assert "last-used:" in content

    def test_patch_increments_patch_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            res = manager.patch_skill("my-skill", "Original body.", "New body.")
            assert res["success"] is True
            skill = manager.get_skill("my-skill")
            assert skill.properties.patch_count == 1

    def test_telemetry_preserves_embedded_fence_in_value(self):
        """A frontmatter value containing '---' must not corrupt the file
        when telemetry is persisted line-wise."""
        from praisonaiagents.skills.manager import SkillManager

        skill_dir = Path(tmpdir := tempfile.mkdtemp()) / "fence-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: fence-skill
description: Parse YAML---based configs
---

The body --- with a fence-like line stays intact.
"""
        )
        manager = SkillManager()
        manager.add_skill(str(skill_dir))
        manager.get_instructions("fence-skill")

        content = (skill_dir / "SKILL.md").read_text()
        assert "description: Parse YAML---based configs" in content
        assert "The body --- with a fence-like line stays intact." in content
        assert "use-count: 1" in content


class TestArchivalAndRestore:
    def test_archive_then_restore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonaiagents.skills import manager as manager_mod

            orig = manager_mod.get_default_skill_dirs
            manager_mod.get_default_skill_dirs = lambda: [str(Path(tmpdir) / "skills")]
            try:
                (Path(tmpdir) / "skills").mkdir()
                manager = manager_mod.SkillManager()
                manager.create_skill("temp-skill", "content")
                assert "temp-skill" in manager

                res = manager.archive_skill("temp-skill")
                assert res["success"] is True
                assert "temp-skill" not in manager
                assert "temp-skill" in manager.list_archived_skills()

                restored = manager.restore_skill("temp-skill")
                assert restored["success"] is True
                assert "temp-skill" in manager
            finally:
                manager_mod.get_default_skill_dirs = orig

    def test_delete_default_is_recoverable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonaiagents.skills import manager as manager_mod

            orig = manager_mod.get_default_skill_dirs
            manager_mod.get_default_skill_dirs = lambda: [str(Path(tmpdir) / "skills")]
            try:
                (Path(tmpdir) / "skills").mkdir()
                manager = manager_mod.SkillManager()
                manager.create_skill("temp-skill", "content")
                res = manager.delete_skill("temp-skill")
                assert res["success"] is True
                assert "temp-skill" in manager.list_archived_skills()
            finally:
                manager_mod.get_default_skill_dirs = orig

    def test_hard_delete_is_unrecoverable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            res = manager.delete_skill("my-skill", hard=True)
            assert res["success"] is True
            assert "my-skill" not in manager


class TestRollback:
    def test_rollback_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            manager.patch_skill("my-skill", "Original body.", "Broken body.")
            instructions = manager.get_instructions("my-skill")
            assert "Broken body." in instructions

            res = manager.rollback_skill("my-skill")
            assert res["success"] is True
            assert "Original body." in manager.get_instructions("my-skill")

    def test_rollback_edit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            manager.edit_skill("my-skill", "Replacement body.")
            assert "Replacement body." in manager.get_instructions("my-skill")

            res = manager.rollback_skill("my-skill")
            assert res["success"] is True
            assert "Original body." in manager.get_instructions("my-skill")

    def test_rollback_without_snapshot_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = _make_manager(tmpdir)
            res = manager.rollback_skill("my-skill")
            assert res["success"] is False
            assert "No rollback snapshot" in res["error"]
