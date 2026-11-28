"""Tests for forwarding shims praisonai.{knowledge,memory,eval} -> praisonaiagents.*."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys


def test_wrapper_import_does_not_load_forwarded_packages(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
import praisonai

for package in ("praisonai", "praisonaiagents"):
    for name in ("eval", "knowledge", "memory"):
        module = f"{package}.{name}"
        assert module not in sys.modules, module
"""],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


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
    assert importlib.import_module("praisonai.memory.adapters") is importlib.import_module(
        "praisonaiagents.memory.adapters"
    )


def test_eval_shim_preserves_identity():
    from praisonai.eval import Judge
    from praisonaiagents.eval import Judge as CoreJudge

    assert Judge is CoreJudge
