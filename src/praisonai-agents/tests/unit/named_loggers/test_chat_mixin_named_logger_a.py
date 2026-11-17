"""agent/chat_mixin.py logs through its named logger (X-08, part A of 2).

Part A covers the methods of `ChatMixin` up to and including `chat`; part B covers
the rest of the file (split to keep each PR under 100 lines).
"""

import ast
from pathlib import Path

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def test_part_a_methods_do_not_log_to_the_root_logger():
    tree = ast.parse((Path(praisonaiagents.__file__).parent / "agent/chat_mixin.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ChatMixin")
    methods = [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
    names = [m.name for m in methods]
    part_a = methods[: names.index("chat") + 1]
    calls = [
        (m.name, n.lineno) for m in part_a for n in ast.walk(m)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in LEVELS and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "logging"
    ]
    assert calls == []
