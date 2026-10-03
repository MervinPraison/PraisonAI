"""Opt-in real LLM regression for documentation priority across reload.

Run with RUN_REAL_KEY_TESTS=1 and a configured provider key.
"""

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1",
    reason="requires an explicitly enabled real provider",
)
def test_real_agent_uses_same_document_context_after_reload(tmp_path):
    """Effective priority must select the same source for real agent answers."""
    from praisonaiagents import Agent
    from praisonaiagents.memory.docs_manager import DocsManager

    options = dict(
        workspace_path=str(tmp_path),
        global_docs_path=str(tmp_path / "global"),
    )
    manager = DocsManager(**options)
    manager.create_doc("local", "The project codename is NEBULA-7.", priority=200)
    manager.create_doc(
        "shared", "The project codename is ORBIT-9.", priority=300, scope="global"
    )
    manager.create_doc("zero", "Supplementary reference.", priority=0)
    original_context = manager.format_docs_for_prompt()

    def verify(current):
        assert current.get_doc("zero").priority == 0
        assert current.get_doc("shared").priority == -700
        context = current.format_docs_for_prompt()
        assert context == original_context
        assert "NEBULA-7" in context
        assert "ORBIT-9" not in context
        reader = Agent(
            name="documentation-reader",
            instructions="Answer only from this documentation:\n" + context,
        )
        result = reader.start("What is the project codename? Return only the codename.")
        print(result)
        assert "NEBULA-7" in str(result)
        assert "ORBIT-9" not in str(result)

    verify(manager)
    manager.reload()
    verify(manager)
    verify(DocsManager(**options))
