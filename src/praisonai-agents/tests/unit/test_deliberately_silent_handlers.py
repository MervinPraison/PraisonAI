"""T-08: silent 'except Exception: pass' blocks kept on purpose in files no
other guard covers. Each one is pinned here by (file, function, count) so a new
silent block in these files fails, and every kept block has a stated reason.
"""
import ast
from collections import Counter
from pathlib import Path

import praisonaiagents

ROOT = Path(praisonaiagents.__file__).parent

KEPT = {
    # Stuck-event-loop watchdog. It must not use logging: a wedged thread can
    # hold the logging lock, so a log call would hang the watchdog instead of
    # dumping stacks and restarting the process.
    "gateway/liveness.py": {
        "_on_deadline": 2, "_on_wedge": 2, "_dump_stacks": 6, "disarm": 1,
        "cancel": 1, "confirm_loop_live": 1, "_on_expire": 2,
    },
    # atexit handler: logging may already be shut down.
    "utils/async_bridge.py": {"_close_thread_runner": 1},
    # litellm's completion_cost raises for every model it has no price for;
    # the fallback table is the normal path, so a log would fire on most calls.
    "utils/cost_utils.py": {"_estimate_cost": 1},
}


def _silent_by_function(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    found = Counter()
    for n in ast.walk(tree):
        if not (isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)):
            continue
        els = n.type.elts if isinstance(n.type, ast.Tuple) else [n.type]
        if n.type is None or any(getattr(e, "id", None) in ("Exception", "BaseException") for e in els):
            owners = [f for f in funcs if f.lineno <= n.lineno <= f.end_lineno]
            found[min(owners, key=lambda f: f.end_lineno - f.lineno).name if owners else "<module>"] += 1
    return dict(found)


def test_only_the_kept_silent_handlers_exist():
    assert {rel: _silent_by_function(rel) for rel in KEPT} == KEPT
