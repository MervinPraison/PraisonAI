"""The number of silent ``except Exception: pass`` blocks may only go down (T-08).

A failure in one of these blocks leaves no trace, which is how several
"setting accepted and ignored" findings stayed hidden (X-01, X-13, D-11). New
code must at least log at debug with ``exc_info=True``. When you convert
blocks, lower CEILING to the new count.
"""

import ast
from pathlib import Path

import praisonaiagents

CEILING = 41  # T-08 PRs (#6600-#6630) + agent.py __init__ local descriptor (T-05 2c)


def _silent_handlers():
    root = Path(praisonaiagents.__file__).parent
    found = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                    and isinstance(node.body[0], ast.Pass)):
                continue
            t = node.type
            names = ([t.id] if isinstance(t, ast.Name)
                     else [e.id for e in t.elts if isinstance(e, ast.Name)] if isinstance(t, ast.Tuple)
                     else [])
            if t is None or {"Exception", "BaseException"} & set(names):
                found.append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    return found


def test_silent_except_blocks_do_not_grow():
    found = _silent_handlers()
    assert len(found) <= CEILING, (
        f"{len(found)} silent 'except Exception: pass' blocks, ceiling {CEILING}. "
        "Log the error (logger.debug(..., exc_info=True)) instead of passing. "
        f"Newest candidates: {found[-5:]}"
    )
