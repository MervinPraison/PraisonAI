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
    "---\nfalse\n---\nBody",
    "---\n0\n---\nBody",
    "---\n[]\n---\nBody",
    "---\ndescription: 2026-02-30\n---\nBody",
])
def test_unusable_frontmatter_keeps_original_instruction_text(manager, source):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(source, encoding="utf-8")
    manager.reload()
    assert manager.get_rule_by_name("reference").content == source


@pytest.mark.parametrize("priority", ["08", "010"])
@pytest.mark.parametrize("scope", ["workspace", "global"])
def test_handwritten_priority_uses_decimal_value(manager, priority, scope):
    rules_dir = manager.global_rules_path if scope == "global" else manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(f"---\npriority: {priority}\n---\nBody", encoding="utf-8")
    manager.reload()
    expected = int(priority, 10) - (1000 if scope == "global" else 0)
    assert manager.get_rule_by_name("reference").priority == expected
    assert manager.build_rules_context()


@pytest.mark.parametrize("pattern", ["2024", "010"])
def test_numeric_glob_remains_original_pattern_text(manager, pattern):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(
        f"---\nglobs: [{pattern}]\nactivation: glob\n---\nBody", encoding="utf-8"
    )
    manager.reload()
    assert manager.get_rule_by_name("reference").globs == [pattern]
    assert [item.name for item in manager.get_active_rules(file_path=pattern)] == ["reference"]


@pytest.mark.parametrize("opening,closing", [("--- \t", "---"), ("---", "--- \t")])
def test_delimiter_accepts_trailing_whitespace(manager, opening, closing):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(
        f'{opening}\ndescription: "before---after"\nactivation: manual\n{closing}\nBody', encoding="utf-8"
    )
    manager.reload()
    rule = manager.get_rule_by_name("reference")
    assert rule.content == "Body"
    assert rule.description == "before---after"
    assert rule.activation == "manual"
    assert manager.get_active_rules() == []


@pytest.mark.parametrize("priority,expected", [("1_000", 1000), ("0x10", 16), ("0b10", 2), ("1:20", 80)])
@pytest.mark.parametrize("scope", ["workspace", "global"])
def test_yaml_integer_priority_preserves_all_metadata(manager, priority, expected, scope):
    rules_dir = manager.global_rules_path if scope == "global" else manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(
        f'---\npriority: {priority}\ndescription: reference\nactivation: manual\n---\nBody', encoding="utf-8"
    )
    manager.reload()
    rule = manager.get_rule_by_name("reference")
    assert rule.priority == expected - (1000 if scope == "global" else 0)
    assert rule.description == "reference"
    assert rule.activation == "manual"
    assert rule.content == "Body"
    assert manager.get_active_rules() == []


def test_empty_frontmatter_remains_valid(manager):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text("---\n---\nBody", encoding="utf-8")
    manager.reload()
    assert manager.get_rule_by_name("reference").content == "Body"


def test_merged_yaml_metadata_retains_decimal_priority_and_pattern_spelling(manager):
    rules_dir = manager.workspace_path / manager.RULES_DIR_NAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "reference.md").write_text(
        "---\ndefaults: &defaults\n  priority: 010\n  globs: [010]\n  activation: glob\n"
        "<<: *defaults\n---\nBody", encoding="utf-8"
    )
    manager.reload()
    rule = manager.get_rule_by_name("reference")
    assert rule.priority == 10
    assert rule.globs == ["010"]
    assert manager.get_active_rules(file_path="010") == [rule]
