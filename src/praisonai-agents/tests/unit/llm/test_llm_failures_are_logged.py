"""T-08, llm/llm.py: swallowed failures are logged at debug and the result is
unchanged (no block in this file runs from a finalizer).
"""
import ast
import logging
from pathlib import Path

import pytest

import praisonaiagents.llm.adapters as adapters
import praisonaiagents.llm.llm as llm_mod
from praisonaiagents.llm.llm import LLM, _replay_observe


def _boom(*a, **k):
    raise RuntimeError("boom")


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_no_silent_broad_handlers_left():
    tree = ast.parse(Path(llm_mod.__file__).read_text(encoding="utf-8"))
    silent = [n.lineno for n in ast.walk(tree)
              if isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)
              and (n.type is None or getattr(n.type, "id", None) in ("Exception", "BaseException"))]
    assert silent == []


def test_failed_provider_discovery_is_logged_and_openai_used(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    llm = LLM(model="myprov/some-model")
    monkeypatch.setattr(adapters, "load_provider_entry_points", _boom)
    with caplog.at_level(logging.DEBUG, logger=llm_mod.logger.name):
        assert llm._detect_provider() == "openai"
    assert _records(caplog, "Provider adapter discovery failed for 'myprov'")


def test_failed_replay_tracing_is_logged_and_span_untouched(caplog):
    class _Bad:  # a response object whose attributes blow up when read
        @property
        def usage(self):
            raise RuntimeError("boom")

    span = {"content": []}
    with caplog.at_level(logging.DEBUG, logger=llm_mod.logger.name):
        assert _replay_observe(span, _Bad(), True) is None
    assert span == {"content": []}
    assert _records(caplog, "Replay tracing could not read a model response")
