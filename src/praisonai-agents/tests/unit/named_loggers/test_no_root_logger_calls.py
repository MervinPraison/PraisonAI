"""No package module logs through the root logger (T-03).

Every module must use a named logger, so ``logging.getLogger("praisonaiagents")``
can quiet or route all SDK output (X-08). This walks every module, so a
root-logger call in any file, new or old, is caught.
"""

import ast
from pathlib import Path

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}

ROOT = Path(praisonaiagents.__file__).parent


def _root_logger_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Names bound to the logging module, so `import logging as _logging` is covered.
    names = {"logging"} | {
        alias.asname for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names if alias.name == "logging" and alias.asname
    }
    lines = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in LEVELS and isinstance(node.func.value, ast.Name)
                and node.func.value.id in names):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "logging":
            lines += [node.lineno for alias in node.names if alias.name in LEVELS]
    return lines


def test_no_module_logs_to_the_root_logger():
    over = {}
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        lines = _root_logger_calls(path)
        if lines:
            over[rel] = lines
    assert not over, (
        "Use a named logger (logger = logging.getLogger(__name__)) instead of "
        f"logging.<level>(...): {over}"
    )

