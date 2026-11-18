"""Swallowed failures in ``praisonaiagents.eval`` leave a debug trace (T-08).

Each attempt in a trial runs on a copy of the agent with its own history and
its memory/knowledge detached. When one of those steps fails the attempt still
runs, but it may share history or write to the caller's stores, so the failure
must be visible at debug level.
"""

import ast
import logging
from pathlib import Path

import praisonaiagents
from praisonaiagents.eval import evalport, trials

EVAL_DIR = Path(praisonaiagents.__file__).parent / "eval"

# (file, function) pairs allowed to keep a silent ``except Exception: pass``.
KEPT_SILENT = set()


def _silent_broad_handlers():
    found = set()
    for path in sorted(EVAL_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                        and isinstance(node.body[0], ast.Pass)):
                    continue
                t = node.type
                names = ([t.id] if isinstance(t, ast.Name)
                         else [e.id for e in t.elts if isinstance(e, ast.Name)]
                         if isinstance(t, ast.Tuple) else [])
                if t is None or {"Exception", "BaseException"} & set(names):
                    found.add((path.relative_to(EVAL_DIR).as_posix(), func.name))
    return found


def test_only_known_silent_handlers_remain():
    assert _silent_broad_handlers() == KEPT_SILENT


class _LockedAgent:
    """Agent whose memory and chat history cannot be replaced on a copy."""

    def __init__(self):
        self._history = ["hello"]
        self.name = "locked"

    @property
    def memory(self):
        return "caller-store"

    @property
    def chat_history(self):
        return self._history


def _records_with_exc_info(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_memory_detach_failure_is_logged_and_copy_still_returned(caplog):
    agent = _LockedAgent()
    with caplog.at_level(logging.DEBUG, logger=trials.logger.name):
        clone = trials._isolated_agent_copy(agent)

    assert clone is not agent
    assert clone.memory == "caller-store"
    assert _records_with_exc_info(caplog, "Could not detach memory")


def test_chat_history_failure_is_logged(caplog):
    agent = _LockedAgent()
    with caplog.at_level(logging.DEBUG, logger=trials.logger.name):
        clone = trials._isolated_agent_copy(agent)

    assert clone.chat_history == ["hello"]
    assert _records_with_exc_info(caplog, "own chat history")


def test_runner_version_failure_is_logged(caplog, monkeypatch):
    import importlib.metadata

    def boom(_name):
        raise importlib.metadata.PackageNotFoundError("praisonaiagents")

    monkeypatch.setattr(importlib.metadata, "version", boom)
    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.eval.evalport"):
        runner = evalport._runner_info()

    assert runner == {"name": "praisonaiagents"}
    assert _records_with_exc_info(caplog, "praisonaiagents version")
