"""Tests for skill bundles (named, reusable sets of skills)."""

import tempfile
from pathlib import Path


def _make_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: The {name} skill\n---\n\n# {name}\n"
    )


def _make_bundle(root: Path, name: str, skills, *, in_bundles_dir=True,
                 description="", instruction=None) -> Path:
    lines = [f"name: {name}"]
    if description:
        lines.append(f"description: {description}")
    lines.append("skills: [" + ", ".join(skills) + "]")
    if instruction:
        lines.append(f"instruction: {instruction}")
    content = "\n".join(lines) + "\n"
    if in_bundles_dir:
        bundles_dir = root / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)
        path = bundles_dir / f"{name}.yaml"
    else:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "BUNDLE.yaml"
    path.write_text(content)
    return path


class TestBundleManifest:
    def test_from_dict_minimal(self):
        from praisonaiagents.skills.bundles import BundleManifest

        m = BundleManifest.from_dict({"name": "backend", "skills": ["a", "b"]})
        assert m.name == "backend"
        assert m.skills == ["a", "b"]
        assert m.instruction is None

    def test_from_dict_string_members(self):
        from praisonaiagents.skills.bundles import BundleManifest

        m = BundleManifest.from_dict({"name": "x", "skills": "a, b c"})
        assert m.skills == ["a", "b", "c"]

    def test_from_dict_requires_name(self):
        from praisonaiagents.skills.bundles import BundleManifest

        try:
            BundleManifest.from_dict({"skills": ["a"]})
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestSelectorHelpers:
    def test_is_bundle_selector(self):
        from praisonaiagents.skills.bundles import is_bundle_selector

        assert is_bundle_selector("@backend")
        assert not is_bundle_selector("backend")
        assert not is_bundle_selector("./skills/code-review")

    def test_strip_marker(self):
        from praisonaiagents.skills.bundles import strip_bundle_marker

        assert strip_bundle_marker("@backend") == "backend"
        assert strip_bundle_marker("backend") == "backend"


class TestDiscoverBundles:
    def test_empty_dir(self):
        from praisonaiagents.skills.bundles import discover_bundles

        with tempfile.TemporaryDirectory() as tmp:
            assert discover_bundles([tmp], include_defaults=False) == []

    def test_discover_from_bundles_dir(self):
        from praisonaiagents.skills.bundles import discover_bundles

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_bundle(root, "backend-dev", ["code-review", "tdd"],
                         description="Backend work")
            bundles = discover_bundles([tmp], include_defaults=False)
            assert len(bundles) == 1
            assert bundles[0].name == "backend-dev"
            assert bundles[0].skills == ["code-review", "tdd"]

    def test_discover_bundle_yaml_in_skill_dir(self):
        from praisonaiagents.skills.bundles import discover_bundles

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_bundle(root, "frontend", ["ui"], in_bundles_dir=False)
            bundles = discover_bundles([tmp], include_defaults=False)
            names = {b.name for b in bundles}
            assert "frontend" in names

    def test_invalid_bundle_is_skipped(self):
        from praisonaiagents.skills.bundles import discover_bundles

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundles_dir = root / "bundles"
            bundles_dir.mkdir()
            (bundles_dir / "broken.yaml").write_text("skills: [a]\n")  # no name
            _make_bundle(root, "good", ["a"])
            bundles = discover_bundles([tmp], include_defaults=False)
            assert {b.name for b in bundles} == {"good"}

    def test_collision_first_wins(self):
        from praisonaiagents.skills.bundles import discover_bundles

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundles_dir = root / "bundles"
            bundles_dir.mkdir()
            (bundles_dir / "a.yaml").write_text("name: dup\nskills: [x]\n")
            (bundles_dir / "b.yaml").write_text("name: dup\nskills: [y]\n")
            bundles = discover_bundles([tmp], include_defaults=False)
            dup = [b for b in bundles if b.name == "dup"]
            assert len(dup) == 1
            assert dup[0].skills == ["x"]


class TestSkillManagerBundles:
    def test_add_and_get_bundle(self):
        from praisonaiagents.skills import SkillManager
        from praisonaiagents.skills.bundles import BundleManifest

        mgr = SkillManager()
        mgr.add_bundle(BundleManifest(name="b", skills=["a", "c"]))
        assert mgr.get_bundle("b") is not None
        assert mgr.get_bundle("@b") is not None
        assert "b" in mgr.bundle_names

    def test_resolve_expands_bundle(self):
        from praisonaiagents.skills import SkillManager
        from praisonaiagents.skills.bundles import BundleManifest

        mgr = SkillManager()
        mgr.add_bundle(BundleManifest(name="backend", skills=["code-review", "tdd"]))
        resolved = mgr.resolve(["@backend", "extra"])
        assert resolved == ["code-review", "tdd", "extra"]

    def test_resolve_passthrough_plain(self):
        from praisonaiagents.skills import SkillManager

        mgr = SkillManager()
        assert mgr.resolve(["a", "./b"]) == ["a", "./b"]

    def test_resolve_unknown_bundle_forgiving(self):
        from praisonaiagents.skills import SkillManager

        mgr = SkillManager()
        # Unknown bundle is skipped, not fatal.
        assert mgr.resolve(["@nope", "keep"]) == ["keep"]

    def test_resolve_dedupes(self):
        from praisonaiagents.skills import SkillManager
        from praisonaiagents.skills.bundles import BundleManifest

        mgr = SkillManager()
        mgr.add_bundle(BundleManifest(name="b1", skills=["x", "y"]))
        mgr.add_bundle(BundleManifest(name="b2", skills=["y", "z"]))
        assert mgr.resolve(["@b1", "@b2"]) == ["x", "y", "z"]

    def test_resolve_nested_bundle(self):
        from praisonaiagents.skills import SkillManager
        from praisonaiagents.skills.bundles import BundleManifest

        mgr = SkillManager()
        mgr.add_bundle(BundleManifest(name="common", skills=["log", "cfg"]))
        mgr.add_bundle(BundleManifest(name="backend", skills=["@common", "api"]))
        assert mgr.resolve(["@backend"]) == ["log", "cfg", "api"]

    def test_resolve_cycle_is_safe(self):
        from praisonaiagents.skills import SkillManager
        from praisonaiagents.skills.bundles import BundleManifest

        mgr = SkillManager()
        mgr.add_bundle(BundleManifest(name="a", skills=["@b", "sa"]))
        mgr.add_bundle(BundleManifest(name="b", skills=["@a", "sb"]))
        # No infinite recursion; each plain member appears once.
        assert mgr.resolve(["@a"]) == ["sb", "sa"]

    def test_bundle_instruction_in_prompt(self):
        from praisonaiagents.skills import SkillManager
        from praisonaiagents.skills.bundles import BundleManifest

        mgr = SkillManager()
        mgr.add_bundle(BundleManifest(
            name="backend", skills=["x"],
            instruction="Prefer small commits.",
        ))
        mgr.resolve(["@backend"])
        xml = mgr.to_prompt()
        assert "Prefer small commits." in xml
        assert "<bundle_instructions>" in xml

    def test_no_bundle_instruction_no_block(self):
        from praisonaiagents.skills import SkillManager

        mgr = SkillManager()
        xml = mgr.to_prompt()
        assert "<bundle_instructions>" not in xml

    def test_discover_bundles_registers(self):
        from praisonaiagents.skills import SkillManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_bundle(root, "backend-dev", ["code-review"])
            mgr = SkillManager()
            count = mgr.discover_bundles([tmp], include_defaults=False)
            assert count == 1
            assert mgr.get_bundle("backend-dev") is not None

    def test_add_skill_by_name(self):
        from praisonaiagents.skills import SkillManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_skill(root, "code-review")
            mgr = SkillManager()
            loaded = mgr.add_skill_by_name(
                "code-review", [tmp], include_defaults=False
            )
            assert loaded is not None
            assert "code-review" in mgr.skill_names


class TestEndToEnd:
    def test_bundle_expands_to_member_skills(self):
        """A '@bundle' selector materialises its member skills by name."""
        from praisonaiagents.skills import SkillManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_skill(root, "code-review")
            _make_skill(root, "tdd")
            _make_bundle(root, "backend-dev", ["code-review", "tdd"])

            mgr = SkillManager()
            mgr.discover_bundles([tmp], include_defaults=False)
            for member in mgr.resolve(["@backend-dev"]):
                mgr.add_skill_by_name(member, [tmp], include_defaults=False)

            assert set(mgr.skill_names) == {"code-review", "tdd"}
            # Members flow through the existing prompt path.
            xml = mgr.to_prompt()
            assert "code-review" in xml
            assert "tdd" in xml
