"""process/process.py logs through its named logger (X-08, part A of 2).

Part A covers every method up to ``workflow``; part B covers ``workflow`` and
``hierarchical`` (the file was split to keep each PR under 100 lines).
"""

import ast
from pathlib import Path

import praisonaiagents

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
PART_A = {
    "__init__", "_create_loop_subtasks", "_resolve_when_routing", "_find_next_not_started_task",
    "_get_manager_instructions_with_fallback_async", "_get_manager_instructions_with_fallback",
    "_check_all_tasks_completed", "_check_all_tasks_completed_sync", "_warn_workflow_iter_limit",
    "aworkflow", "ahierarchical",
}


def test_part_a_methods_do_not_log_to_the_root_logger():
    tree = ast.parse((Path(praisonaiagents.__file__).parent / "process/process.py").read_text())
    process = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Process")
    methods = {m.name: m for m in process.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert PART_A <= set(methods)
    calls = {
        name: [n.lineno for n in ast.walk(methods[name])
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr in LEVELS and isinstance(n.func.value, ast.Name)
               and n.func.value.id == "logging"]
        for name in PART_A
    }
    assert {k: v for k, v in calls.items() if v} == {}
