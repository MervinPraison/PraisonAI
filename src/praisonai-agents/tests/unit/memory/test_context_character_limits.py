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
