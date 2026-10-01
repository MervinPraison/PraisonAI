"""Prompt context limits include headers, separators and truncation markers."""

import pytest

from praisonaiagents.memory.docs_manager import DocsManager
from praisonaiagents.memory.rules_manager import RulesManager


@pytest.mark.parametrize("kind", ["docs", "rules"])
@pytest.mark.parametrize("budget", [-1, 0, 1, 20, 100, 125, 250, 10000])
def test_formatted_context_respects_complete_character_limit(tmp_path, monkeypatch, kind, budget):
    if kind == "docs":
        manager = DocsManager(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
        create = manager.create_doc
        format_context = manager.format_docs_for_prompt
    else:
        monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
        manager = RulesManager(workspace_path=str(tmp_path), global_rules_path=str(tmp_path / "global"))
        create = manager.create_rule
        format_context = manager.build_rules_context
    for i in range(3):
        create(f"entry{i}", f"Distinct content {i}: " + "x" * 100, priority=300 - i)
    context = format_context(max_chars=budget)
    assert len(context) <= max(0, budget)
    if budget <= 0:
        assert context == ""
    elif budget == 10000:
        for i in range(3):
            assert f"Distinct content {i}: " in context
        assert context.index("entry0") < context.index("entry1") < context.index("entry2")


@pytest.fixture(params=["docs", "rules"])
def formatter(tmp_path, monkeypatch, request):
    if request.param == "docs":
        manager = DocsManager(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
        return manager.create_doc, manager.format_docs_for_prompt, "# Project Documentation\n\n"
    monkeypatch.setattr(RulesManager, "_find_git_root", lambda self: None)
    manager = RulesManager(workspace_path=str(tmp_path), global_rules_path=str(tmp_path / "global"))
    return manager.create_rule, manager.build_rules_context, ""


@pytest.mark.parametrize("preceding", [False, True])
def test_truncated_context_keeps_complete_marker_and_header(formatter, preceding):
    create, format_context, _ = formatter
    if preceding:
        create("first", "keep this", priority=300)
    create("large", "x" * 500, priority=200)
    budget = 250 if preceding else 125
    context = format_context(max_chars=budget)
    assert len(context) <= budget
    assert "## large\n" in context
    assert context.endswith("\n... (truncated)")
    if preceding:
        assert "## first\nkeep this\n" in context


@pytest.mark.parametrize("budget", [1, 20, 23, 24])
def test_budget_without_room_for_a_section_returns_empty(formatter, budget):
    create, format_context, _ = formatter
    create("large", "x" * 500, priority=200)
    assert format_context(max_chars=budget) == ""


def test_truncation_does_not_split_a_long_header(formatter):
    create, format_context, _ = formatter
    create("large", "x" * 500, description="d" * 200, priority=200)
    assert format_context(max_chars=125) == ""


def test_exact_section_budget_preserves_complete_output(formatter):
    create, format_context, prefix = formatter
    create("entry", "complete", priority=200)
    expected = prefix + "## entry\ncomplete\n"
    assert format_context(max_chars=len(expected)) == expected
