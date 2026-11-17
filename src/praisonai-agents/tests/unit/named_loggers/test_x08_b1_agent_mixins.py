"""These modules log through named loggers, so logging.getLogger("praisonaiagents")
can quiet or route them (X-08, batch b1-agent-mixins)."""

import ast
from pathlib import Path

import pytest

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
FILES = ['agent/memory_mixin.py', 'agent/execution_mixin.py', 'agent/unified_execution_mixin.py', 'agent/attachments.py', 'agent/image_agent.py']


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
