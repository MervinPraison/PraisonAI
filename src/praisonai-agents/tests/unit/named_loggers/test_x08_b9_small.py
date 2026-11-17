"""These modules log through named loggers, so logging.getLogger("praisonaiagents")
can quiet or route them (X-08, batch b9-small)."""

import ast
from pathlib import Path

import pytest

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
FILES = ['compaction/compactor.py', 'knowledge/knowledge.py', 'session/api.py']


@pytest.mark.parametrize("rel", FILES)
def test_module_does_not_log_to_the_root_logger(rel):
    path = Path(praisonaiagents.__file__).parent / rel
    calls = [
        node.lineno for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LEVELS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logging"
    ]
    assert calls == [], f"{rel}: root-logger calls on lines {calls}"
