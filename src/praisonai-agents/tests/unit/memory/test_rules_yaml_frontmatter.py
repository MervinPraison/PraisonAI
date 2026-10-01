"""Rule frontmatter preserves declared YAML values and generated metadata."""

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
    return RulesManager(workspace_path=str(tmp_path), global_rules_path=str(tmp_path / "global"))


@pytest.mark.parametrize("priority", [-5, 200])
def test_created_priority_remains_numeric_and_sortable(manager, priority):
    manager.create_rule("reference", "Body", priority=priority)
    manager.create_rule("control", "Control", priority=0)
    manager.reload()
    assert manager.get_rule_by_name("reference").priority == priority
    assert manager.build_rules_context()


@pytest.mark.parametrize("globs_yaml", ['["file,a.py"]', '\n  - "file,a.py"'])
def test_yaml_glob_list_preserves_a_pattern_with_comma(manager, globs_yaml):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(
        f'---\nglobs: {globs_yaml}\nactivation: glob\n---\nBody', encoding="utf-8"
    )
    manager.reload()
    rule = manager.get_rule_by_name("reference")
    assert rule.globs == ["file,a.py"]
    assert [item.name for item in manager.get_active_rules(file_path="file,a.py")] == ["reference"]


@pytest.mark.parametrize("text", ['Use "quoted" text', "first\nsecond", "before---after", "plain"])
def test_created_description_survives_disk_reload(manager, text):
    manager.create_rule("reference", "Body", description=text, priority=200)
    manager.reload()
    rule = manager.get_rule_by_name("reference")
    assert rule.description == text
    assert rule.content == "Body"
    assert rule.priority == 200


def test_created_glob_with_comma_survives_reload(manager):
    manager.create_rule("reference", "Body", globs=["file,a.py"], activation="glob")
    manager.reload()
    assert manager.get_rule_by_name("reference").globs == ["file,a.py"]


@pytest.mark.parametrize("text", [r"C:\new\rules", "Unicode 😀\u0085next"])
def test_escaped_description_survives_reload(manager, text):
    manager.create_rule("reference", "Body", description=text)
    manager.reload()
    assert manager.get_rule_by_name("reference").description == text


@pytest.mark.parametrize("source", [
    "---\ndescription: [\n---\nBody",
    "---\nunfinished",
    "---\n- item\n---\nBody",
])
def test_unusable_frontmatter_keeps_original_instruction_text(manager, source):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(source, encoding="utf-8")
    manager.reload()
    assert manager.get_rule_by_name("reference").content == source
