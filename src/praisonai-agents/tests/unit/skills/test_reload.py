"""Tests for SkillManager.reload() live-refresh behaviour."""

import os
import time
from pathlib import Path
import tempfile


def _write_skill(base: Path, name: str, body: str = "# Instructions\n") -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: {name} skill
---

{body}"""
    )
    return skill_dir


class TestSkillReload:
    """Tests for reloading skills into a live session without restart."""

    def test_reload_picks_up_new_skill_md(self):
        """A SKILL.md added after discovery is picked up by reload()."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _write_skill(base, "alpha")

            manager = SkillManager()
            manager.discover([tmpdir], include_defaults=False)
            assert "alpha" in manager
            assert "beta" not in manager

            # Simulate `skills install`: a new skill appears on disk.
            _write_skill(base, "beta")

            diff = manager.reload()

            assert "beta" in manager
            assert diff["added"] == ["beta"]
            assert diff["changed"] == []
            assert diff["removed"] == []

    def test_reload_reports_diff(self):
        """reload() reports added, changed and removed skills together."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _write_skill(base, "keep")
            edited = _write_skill(base, "edited", body="# Old\n")
            _write_skill(base, "gone")

            manager = SkillManager()
            manager.discover([tmpdir], include_defaults=False)
            # Establish an mtime baseline for change detection.
            manager.reload()

            # add a new skill
            _write_skill(base, "fresh")
            # edit an existing skill (bump mtime past baseline)
            skill_md = edited / "SKILL.md"
            os.utime(skill_md, (time.time() + 5, time.time() + 5))
            # remove a skill
            import shutil

            shutil.rmtree(base / "gone")

            diff = manager.reload()

            assert diff["added"] == ["fresh"]
            assert diff["changed"] == ["edited"]
            assert diff["removed"] == ["gone"]
            assert "fresh" in manager
            assert "gone" not in manager

    def test_removed_skill_deactivated(self):
        """A removed skill is dropped and its cached instructions cleared."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _write_skill(base, "temp", body="# Live instructions\n")

            manager = SkillManager()
            manager.discover([tmpdir], include_defaults=False)
            manager.activate_by_name("temp")
            skill = manager.get_skill("temp")
            assert skill is not None and skill.is_activated

            import shutil

            shutil.rmtree(base / "temp")

            diff = manager.reload()

            assert diff["removed"] == ["temp"]
            assert "temp" not in manager
            # The previously-held LoadedSkill was deactivated.
            assert skill.instructions is None
            assert not skill.is_activated

    def test_reload_preserves_unchanged_activation(self):
        """Unchanged skills keep their activated instructions across reload."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _write_skill(base, "stable", body="# Stable\n")

            manager = SkillManager()
            manager.discover([tmpdir], include_defaults=False)
            manager.reload()  # baseline mtime
            manager.activate_by_name("stable")
            original = manager.get_skill("stable")

            diff = manager.reload()

            assert diff == {"added": [], "changed": [], "removed": []}
            # Same object retained (activation + telemetry preserved).
            assert manager.get_skill("stable") is original
            assert original.is_activated

    def test_reload_without_prior_discover(self):
        """reload() works even if discover() was never called explicitly."""
        from praisonaiagents.skills.manager import SkillManager

        manager = SkillManager()
        diff = manager.reload()

        assert set(diff.keys()) == {"added", "changed", "removed"}
