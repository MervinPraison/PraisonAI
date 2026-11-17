"""No package module logs through the root logger (T-03).

Every module must use a named logger, so ``logging.getLogger("praisonaiagents")``
can quiet or route all SDK output (X-08). The per-file guards next to this test
cover only the files they name; this one walks every module, so a root-logger
call in a file nobody listed is caught too.

ALLOWED is a ratchet: a file not listed must have none, and a listed file may
go down but never up. Lower or remove an entry when its file is converted.
"""

import ast
from pathlib import Path

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}

# Not yet converted. process/process.py: #6581 re-lands its conversion (#6497).
ALLOWED = {
    "process/process.py": 61,
}

ROOT = Path(praisonaiagents.__file__).parent


def _root_logger_calls(path):
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in LEVELS and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logging"):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "logging":
            lines += [node.lineno for alias in node.names if alias.name in LEVELS]
    return lines


def test_no_module_logs_to_the_root_logger():
    over = {}
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        lines = _root_logger_calls(path)
        if len(lines) > ALLOWED.get(rel, 0):
            over[rel] = lines
    assert not over, (
        "Use a named logger (logger = logging.getLogger(__name__)) instead of "
        f"logging.<level>(...): {over}"
    )


def test_allowed_entries_are_real_files():
    missing = [rel for rel in ALLOWED if not (ROOT / rel).is_file()]
    assert not missing, f"Remove these from ALLOWED: {missing}"
