"""Swallowed failures in the run journal, runtime plugin discovery, the task
guardrail model lookup and the context trace sink leave a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import importlib.metadata
import logging
import types
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents import guardrails
from praisonaiagents.config import loader
from praisonaiagents.runtime import registry
from praisonaiagents.task import task as task_mod
from praisonaiagents.trace import context_events

_FILES = [
    "runtime/journal.py",
    "runtime/registry.py",
    "task/task.py",
    "trace/context_events.py",
]


def _silent_broad_handlers(rel):
    path = Path(praisonaiagents.__file__).parent / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)):
            continue
        t = node.type
        names = ([t.id] if isinstance(t, ast.Name)
                 else [e.id for e in t.elts if isinstance(e, ast.Name)]
                 if isinstance(t, ast.Tuple) else [])
        if t is None or {"Exception", "BaseException"} & set(names):
            found.append((rel, node.lineno))
    return found


@pytest.mark.parametrize("rel", _FILES)
def test_no_silent_broad_handlers_left(rel):
    assert _silent_broad_handlers(rel) == []


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_trace_sink_failure_is_logged_and_emission_continues(caplog):
    class _BrokenSink:
        def emit(self, event):
            raise RuntimeError("sink broke")

        def flush(self):
            pass

        def close(self):
            pass

    emitter = context_events.ContextTraceEmitter(sink=_BrokenSink(), session_id="s1")

    with caplog.at_level(logging.DEBUG, logger=context_events.__name__):
        emitter.agent_start("writer")
        emitter.agent_start("writer")

    records = _debug_records(caplog, context_events.__name__)
    assert len(records) == 2
    assert "AGENT_START" in records[0].getMessage()


def test_small_model_lookup_failure_is_logged_and_primary_model_used(monkeypatch, caplog):
    seen = {}

    class _FakeGuardrail:
        def __init__(self, description, llm=None):
            seen["description"], seen["llm"] = description, llm

    def _boom(**kwargs):
        raise RuntimeError("config broke")

    monkeypatch.setattr(guardrails, "LLMGuardrail", _FakeGuardrail)
    monkeypatch.setattr(loader, "get_small_model", _boom)
    task = object.__new__(task_mod.Task)
    task.guardrail = "Reply must be polite"
    task.agent = types.SimpleNamespace(llm="gpt-4o-mini", llm_instance=None)

    with caplog.at_level(logging.DEBUG, logger=task_mod.logger.name):
        task._setup_guardrail()

    assert seen == {"description": "Reply must be polite", "llm": "gpt-4o-mini"}
    assert isinstance(task._guardrail_fn, _FakeGuardrail)
    assert _debug_records(caplog, task_mod.logger.name)


def test_runtime_discovery_failure_is_logged_and_registry_unchanged(monkeypatch, caplog):
    def _boom(**kwargs):
        raise RuntimeError("metadata broke")

    before = dict(registry._runtimes)
    monkeypatch.setattr(importlib.metadata, "entry_points", _boom)

    with caplog.at_level(logging.DEBUG, logger=registry.__name__):
        result = registry._discover_entry_point_runtimes()

    assert result is None
    assert registry._runtimes == before
    assert _debug_records(caplog, registry.__name__)
