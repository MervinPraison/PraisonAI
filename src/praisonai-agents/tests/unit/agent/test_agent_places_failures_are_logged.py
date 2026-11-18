"""Swallowed failures in agent placement/journal helpers leave a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import logging
import sys
import types
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents.agent import durable, heartbeat, placement
from praisonaiagents.agent.durable import DurableRunContext
from praisonaiagents.agent.heartbeat import Heartbeat
from praisonaiagents.runtime import RunJournal

_FILES = [
    "agent/durable.py",
    "agent/execution_location.py",
    "agent/handoff.py",
    "agent/heartbeat.py",
    "agent/placement.py",
]


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
def test_no_silent_broad_handlers_left(rel):
    assert _silent_broad_handlers(rel) == []


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_registry_failure_is_logged_and_fallback_returned(monkeypatch, caplog):
    fake = types.ModuleType("praisonai.integrations.backend_registry")

    def _boom():
        raise RuntimeError("registry broke")

    fake.get_backend_registry = _boom
    monkeypatch.setitem(sys.modules, "praisonai.integrations.backend_registry", fake)

    with caplog.at_level(logging.DEBUG, logger=placement.__name__):
        result = placement.managed_runtimes()

    assert result == ("anthropic",)
    assert _debug_records(caplog, placement.__name__)


def test_schedule_parser_failure_is_logged_and_keyword_fallback_used(monkeypatch, caplog):
    import praisonaiagents.scheduler.parser as parser

    def _boom(_schedule):
        raise ValueError("cannot parse")

    monkeypatch.setattr(parser, "parse_schedule", _boom)

    with caplog.at_level(logging.DEBUG, logger=heartbeat.__name__):
        daily = Heartbeat._resolve_interval("daily")
        every = Heartbeat._resolve_interval("every 5m")

    assert daily == 86400.0
    assert every == 300.0
    records = _debug_records(caplog, heartbeat.__name__)
    assert len(records) == 2
    assert "daily" in records[0].getMessage()


def test_verification_journal_failure_is_logged_and_never_raises(caplog):
    journal = RunJournal(":memory:")
    context = DurableRunContext(journal, "run-1", replaying=False)
    start_seq = context._next_seq

    def _boom(_event):
        raise RuntimeError("disk full")

    journal.append = _boom

    with caplog.at_level(logging.DEBUG, logger=durable.__name__):
        context.record_verification([{"ok": True}, {"ok": False}])

    assert context._next_seq == start_seq + 2
    records = _debug_records(caplog, durable.__name__)
    assert len(records) == 2
    assert "run-1" in records[0].getMessage()
