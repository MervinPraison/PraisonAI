"""Swallowed failures in token tracking, provider discovery, knowledge tracing
and LSP shutdown leave a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import importlib.metadata
import logging
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents.knowledge import knowledge as knowledge_mod
from praisonaiagents.llm import adapters
from praisonaiagents.llm import openai_client
from praisonaiagents.telemetry import token_collector
from praisonaiagents.trace import context_events

_FILES = [
    "knowledge/knowledge.py",
    "llm/adapters/__init__.py",
    "llm/openai_client.py",
    "lsp/client.py",
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


def test_token_tracking_failure_is_logged_and_metrics_kept(monkeypatch, caplog):
    class _BrokenCollector:
        def track_tokens(self, **kwargs):
            raise RuntimeError("collector broke")

    monkeypatch.setattr(token_collector, "get_token_collector", lambda: _BrokenCollector())
    client = object.__new__(openai_client.OpenAIClient)
    response = {"usage": {"prompt_tokens": 7, "completion_tokens": 5}}

    with caplog.at_level(logging.DEBUG, logger=openai_client.__name__):
        result = client._track_token_usage(response, "gpt-4o-mini")

    assert result is None
    assert client.last_token_metrics.input_tokens == 7
    assert client.last_token_metrics.output_tokens == 5
    assert _debug_records(caplog, openai_client.__name__)


def test_provider_discovery_failure_is_logged_and_builtins_kept(monkeypatch, caplog):
    def _boom(**kwargs):
        raise RuntimeError("metadata broke")

    before = dict(adapters._provider_adapters)
    monkeypatch.setattr(adapters, "_provider_entry_points_loaded", False)
    monkeypatch.setattr(importlib.metadata, "entry_points", _boom)

    with caplog.at_level(logging.DEBUG, logger=adapters.__name__):
        result = adapters.load_provider_entry_points()

    assert result is None
    assert adapters._provider_adapters == before
    assert adapters._provider_entry_points_loaded is True
    assert _debug_records(caplog, adapters.__name__)


def test_knowledge_trace_failure_is_logged_and_swallowed(monkeypatch, caplog):
    def _boom():
        raise RuntimeError("emitter broke")

    monkeypatch.setattr(context_events, "get_context_emitter", _boom)
    kb = object.__new__(knowledge_mod.Knowledge)

    with caplog.at_level(logging.DEBUG, logger=knowledge_mod.logger.name):
        result = kb._emit_knowledge_event("add", source="notes.txt", chunk_count=2)

    assert result is None
    assert _debug_records(caplog, knowledge_mod.logger.name)
