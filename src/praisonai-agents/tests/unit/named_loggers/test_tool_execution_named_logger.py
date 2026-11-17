"""praisonaiagents/agent/tool_execution.py logs through its named logger, so logging.getLogger("praisonaiagents")
can quiet or route it (X-08)."""

import ast
from pathlib import Path

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def test_module_does_not_log_to_the_root_logger():
    path = Path(praisonaiagents.__file__).parent / "agent/tool_execution.py"
    calls = [
        node.lineno for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LEVELS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logging"
    ]
    assert calls == [], f"root-logger calls on lines {calls}"
