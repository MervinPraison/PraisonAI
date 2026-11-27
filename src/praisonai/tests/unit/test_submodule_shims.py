"""Tests for forwarding shims praisonai.{knowledge,memory,eval} -> praisonaiagents.*."""

from __future__ import annotations


def test_knowledge_shim_preserves_identity():
    from praisonai.knowledge import KeywordIndex, Knowledge
    from praisonaiagents.knowledge import (
        KeywordIndex as CoreKeywordIndex,
        Knowledge as CoreKnowledge,
    )

    assert KeywordIndex is CoreKeywordIndex
    assert Knowledge is CoreKnowledge


def test_memory_shim_and_adapters_preserve_identity():
    from praisonai.memory import FileMemory
    from praisonai.memory.adapters import SqliteMemoryAdapter
    from praisonaiagents.memory import FileMemory as CoreFileMemory
    from praisonaiagents.memory.adapters import (
        SqliteMemoryAdapter as CoreSqliteMemoryAdapter,
    )

    assert FileMemory is CoreFileMemory
    assert SqliteMemoryAdapter is CoreSqliteMemoryAdapter


def test_eval_shim_preserves_identity():
    from praisonai.eval import Judge
    from praisonaiagents.eval import Judge as CoreJudge

    assert Judge is CoreJudge
