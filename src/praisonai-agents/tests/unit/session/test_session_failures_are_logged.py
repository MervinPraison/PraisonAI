"""Failures swallowed in ``praisonaiagents/session/`` leave a debug trace (T-08).

Each of these used to be ``except Exception: pass``. Return values are
unchanged, but a debug record with the traceback now says what went wrong.
"""

import ast
import asyncio
import logging
import sqlite3
from pathlib import Path

import praisonaiagents.session as session_pkg
from praisonaiagents.session import SqliteTranscriptStore
from praisonaiagents.session import sqlite_transcript_store as sqlite_store_mod
from praisonaiagents.session import title as title_mod

SESSION_DIR = Path(session_pkg.__file__).parent

# (file, function) pairs deliberately left as broad silent handlers. None.
KEPT_SILENT = set()


def _silent_broad_handlers():
    found = set()
    for path in sorted(SESSION_DIR.rglob("*.py")):
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
                    found.add((path.relative_to(SESSION_DIR).as_posix(), func.name))
    return found


def _debug_records_with_traceback(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_only_deliberate_silent_handlers_remain():
    assert _silent_broad_handlers() == KEPT_SILENT


class _RollbackFailsConnection:
    """Delegates to a real connection, but ROLLBACK raises."""

    def __init__(self, real):
        self._real = real

    def execute(self, sql, *args):
        if sql == "ROLLBACK":
            raise sqlite3.OperationalError("cannot rollback")
        return self._real.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_failed_rollback_after_failed_append_is_logged(tmp_path, monkeypatch, caplog):
    store = SqliteTranscriptStore(session_dir=str(tmp_path), db_path=":memory:")
    real = store._connect()
    monkeypatch.setattr(store, "_connect", lambda: _RollbackFailsConnection(real))

    def boom(*_a, **_kw):
        raise RuntimeError("read failed")

    monkeypatch.setattr(store, "_read_row", boom)
    logger_name = sqlite_store_mod.logger.name
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        assert store.add_message("s1", "user", "hello") is False
    real.execute("ROLLBACK")

    records = _debug_records_with_traceback(caplog, logger_name)
    assert records and "s1" in records[0].getMessage()
    # The existing error report for the lost message is still there.
    assert any(r.levelno == logging.ERROR and "s1" in r.getMessage()
               for r in caplog.records if r.name == logger_name)


class _FailingLLM:
    def __init__(self, model):
        self.model = model

    async def get_response_async(self, **_kw):
        raise RuntimeError("provider down")


def test_title_llm_failure_is_logged_and_fallback_returned(monkeypatch, caplog):
    import praisonaiagents.llm as llm_pkg

    monkeypatch.setattr(llm_pkg, "LLM", _FailingLLM)
    with caplog.at_level(logging.DEBUG, logger=title_mod.__name__):
        title = asyncio.run(title_mod.generate_title_async(
            "Help me debug this Python code", "Sure", llm_model="fake-title-model",
        ))
    assert title == title_mod._create_fallback_title("Help me debug this Python code", 60)
    records = _debug_records_with_traceback(caplog, title_mod.__name__)
    assert records and "fake-title-model" in records[0].getMessage()


def test_small_model_config_failure_is_logged_and_primary_used(monkeypatch, caplog):
    from praisonaiagents.config import loader

    def boom(**_kw):
        raise RuntimeError("bad config")

    monkeypatch.setattr(loader, "get_small_model", boom)
    with caplog.at_level(logging.DEBUG, logger=title_mod.__name__):
        assert title_mod._resolve_small_model(None, "primary-model") == "primary-model"
    assert _debug_records_with_traceback(caplog, title_mod.__name__)
