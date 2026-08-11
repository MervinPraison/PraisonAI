"""Tests for declarative remote skill sources (skills/remote.py)."""

import shutil
import subprocess
from pathlib import Path

import pytest


def _git(args, cwd):
    subprocess.run(
        ["git"] + args, cwd=str(cwd), check=True,
        capture_output=True, text=True,
    )


def _make_skill(directory: Path, name: str, description: str = "A remote skill"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"
    )


def _make_git_repo(tmp_path: Path, skill_name: str) -> Path:
    repo = tmp_path / "remote-repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "t@t.com"], repo)
    _git(["config", "user.name", "t"], repo)
    _make_skill(repo / skill_name, skill_name)
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "init"], repo)
    return repo


def _make_root_skill_git_repo(tmp_path: Path, skill_name: str) -> Path:
    """A repo whose SKILL.md sits at the repository root (single skill)."""
    repo = tmp_path / "remote-root-repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "t@t.com"], repo)
    _git(["config", "user.name", "t"], repo)
    _make_skill(repo, skill_name)
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "init"], repo)
    return repo


class _FakeSource:
    """In-memory source that copies a fixed skill tree into the cache."""

    def __init__(self, skills_root: Path):
        self.skills_root = skills_root
        self.calls = 0

    def fetch(self, cache_dir: Path):
        self.calls += 1
        return [self.skills_root]


class TestFetchRemoteSkillDirs:
    def test_object_source_returns_dirs(self, tmp_path):
        from praisonaiagents.skills.remote import fetch_remote_skill_dirs

        skills_root = tmp_path / "skills"
        _make_skill(skills_root / "my-skill", "my-skill")

        cache = tmp_path / "cache"
        dirs = fetch_remote_skill_dirs([_FakeSource(skills_root)], cache_dir=cache)

        assert skills_root in dirs

    def test_unrecognised_source_skipped(self, tmp_path):
        from praisonaiagents.skills.remote import fetch_remote_skill_dirs

        dirs = fetch_remote_skill_dirs([12345], cache_dir=tmp_path / "c")
        assert dirs == []


class TestGitRemoteSkillSource:
    def test_fetch_and_discover(self, tmp_path):
        from praisonaiagents.skills.remote import GitRemoteSkillSource
        from praisonaiagents.skills.discovery import discover_skills

        repo = _make_git_repo(tmp_path, "remote-skill")
        cache = tmp_path / "cache"

        source = GitRemoteSkillSource(repo.as_uri())
        dirs = source.fetch(cache)
        assert dirs, "expected at least one cache dir"

        skills = discover_skills(sources=[repo.as_uri()], include_defaults=False)
        # discover with cache override isn't exposed, so validate via direct scan
        names = {s.name for s in discover_skills(
            [str(d) for d in dirs], include_defaults=False)}
        assert "remote-skill" in names

    def test_offline_fallback_to_cache(self, tmp_path):
        from praisonaiagents.skills.remote import GitRemoteSkillSource

        repo = _make_git_repo(tmp_path, "cached-skill")
        cache = tmp_path / "cache"

        source = GitRemoteSkillSource(repo.as_uri())
        first = source.fetch(cache)
        assert first

        # Break the remote, then fetch again -> should return cached copy.
        shutil.rmtree(repo)
        broken = GitRemoteSkillSource(repo.as_uri())
        second = broken.fetch(cache)
        assert second, "offline fetch should fall back to last-good cache"
        # The cached skill is still discoverable.
        current = second[0]
        assert (current / "cached-skill" / "SKILL.md").exists()

    def test_version_update_atomic_swap(self, tmp_path):
        from praisonaiagents.skills.remote import GitRemoteSkillSource

        repo = _make_git_repo(tmp_path, "v1-skill")
        cache = tmp_path / "cache"
        source = GitRemoteSkillSource(repo.as_uri())

        first = source.fetch(cache)
        assert (first[0] / "v1-skill" / "SKILL.md").exists()

        # Add a new skill and commit -> new version.
        _make_skill(repo / "v2-skill", "v2-skill")
        _git(["add", "-A"], repo)
        _git(["commit", "-m", "add v2"], repo)

        second = source.fetch(cache)
        current = second[0]
        assert (current / "v1-skill" / "SKILL.md").exists()
        assert (current / "v2-skill" / "SKILL.md").exists()

    def test_missing_source_returns_empty_when_no_cache(self, tmp_path):
        from praisonaiagents.skills.remote import GitRemoteSkillSource

        source = GitRemoteSkillSource("https://invalid.invalid/nope.git")
        dirs = source.fetch(tmp_path / "cache")
        assert dirs == []


class TestRootLevelSkillRepo:
    def test_root_skill_discovered_exactly_once(self, tmp_path):
        """A repo with SKILL.md at its root must not be counted twice.

        Regression: the fetched ``current`` alias lives next to its versioned
        cache dir; returning the parent would surface both and double-count.
        """
        from praisonaiagents.skills.remote import (
            GitRemoteSkillSource,
            fetch_remote_skill_dirs,
        )
        from praisonaiagents.skills.discovery import discover_skills

        repo = _make_root_skill_git_repo(tmp_path, "root-skill")
        cache = tmp_path / "cache"

        dirs = fetch_remote_skill_dirs([repo.as_uri()], cache_dir=cache)
        assert dirs, "expected the root-level skill dir to be returned"

        skills = discover_skills(
            [str(d) for d in dirs], include_defaults=False
        )
        names = [s.name for s in skills]
        assert names.count("root-skill") == 1, names


class TestValidatorAppliedToFetched:
    def test_fetched_skills_validate(self, tmp_path):
        from praisonaiagents.skills.remote import fetch_remote_skill_dirs
        from praisonaiagents.skills import validate as validate_skill

        skills_root = tmp_path / "skills"
        _make_skill(skills_root / "good-skill", "good-skill")

        cache = tmp_path / "cache"
        dirs = fetch_remote_skill_dirs([_FakeSource(skills_root)], cache_dir=cache)

        errors = validate_skill(skills_root / "good-skill")
        assert errors == []
        assert skills_root in dirs
