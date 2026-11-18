"""Swallowed failures in planning, approval and the background job store leave
a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import logging
from pathlib import Path
from unittest import mock

import pytest

import praisonaiagents
from praisonaiagents.approval import registry as registry_mod
from praisonaiagents.approval.protocols import ApprovalDecision
from praisonaiagents.approval.registry import ApprovalRegistry
from praisonaiagents.background import sqlite_store
from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore

_FILES = [
    "agents/agents.py",
    "approval/registry.py",
    "background/runner.py",
    "background/sqlite_store.py",
]

# Kept silent on purpose: _shutdown_bg_loop is registered with atexit, where
# logging may already be torn down.
_KEPT = {("background/runner.py", "_shutdown_bg_loop")}


def _silent_broad_handlers(rel):
    path = Path(praisonaiagents.__file__).parent / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
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
                found.append((rel, func.name))
    return found


@pytest.mark.parametrize("rel", _FILES)
def test_only_deliberate_silent_handlers_remain(rel):
    assert set(_silent_broad_handlers(rel)) <= _KEPT
    if rel == "background/runner.py":
        assert _silent_broad_handlers(rel) == [("background/runner.py", "_shutdown_bg_loop")]


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_nameless_always_grant_fallback_failure_is_logged(caplog):
    reg = ApprovalRegistry()
    decision = ApprovalDecision(approved=True, scope="always")
    with mock.patch("praisonaiagents.approval.utils.build_permission_target",
                    side_effect=RuntimeError("target broke")):
        with caplog.at_level(logging.DEBUG, logger=registry_mod.logger.name):
            reg._persist_scoped_decision(None, "write_file", {"path": "a"}, decision)

    assert reg._session_scoped_targets == set()
    records = _debug_records(caplog, registry_mod.logger.name)
    assert any("write_file" in r.getMessage() for r in records)


def test_approval_cache_eviction_failure_is_logged(caplog):
    reg = ApprovalRegistry()
    broken = mock.Mock()
    broken.get.side_effect = RuntimeError("context broke")
    reg._approved_context = broken

    with caplog.at_level(logging.DEBUG, logger=registry_mod.logger.name):
        reg.release_scope("scope-1")

    broken.set.assert_not_called()
    records = _debug_records(caplog, registry_mod.logger.name)
    assert any("scope-1" in r.getMessage() for r in records)


def test_job_store_close_failure_is_logged_and_never_raises(caplog):
    store = SqliteBackgroundJobStore(":memory:")
    real = store._conn
    broken = mock.Mock()
    broken.close.side_effect = RuntimeError("close broke")
    store._conn = broken
    try:
        with caplog.at_level(logging.DEBUG, logger=sqlite_store.logger.name):
            store.close()
    finally:
        real.close()

    broken.close.assert_called_once()
    records = _debug_records(caplog, sqlite_store.logger.name)
    assert any(":memory:" in r.getMessage() for r in records)
