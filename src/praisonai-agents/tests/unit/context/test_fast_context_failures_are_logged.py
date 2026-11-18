"""Swallowed failures under ``praisonaiagents/context/fast/`` leave a debug trace (T-08)."""

import ast
import builtins
import logging
from pathlib import Path

import praisonaiagents
from praisonaiagents.context.fast import search_tools
from praisonaiagents.context.fast.indexer import file_indexer


def _silent_broad_handlers():
    root = Path(praisonaiagents.__file__).parent
    found = []
    for path in sorted((root / "context" / "fast").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                    and isinstance(node.body[0], ast.Pass)):
                continue
            t = node.type
            names = ([t.id] if isinstance(t, ast.Name)
                     else [e.id for e in t.elts if isinstance(e, ast.Name)]
                     if isinstance(t, ast.Tuple) else [])
            if t is None or {"Exception", "BaseException"} & set(names):
                found.append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    return found


def test_no_silent_broad_handlers_in_fast_context():
    assert _silent_broad_handlers() == []


def _fail_opening(monkeypatch, filename):
    real_open = builtins.open

    def fake_open(file, *a, **k):
        if Path(file).name == filename:
            raise PermissionError("denied")
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)


def test_unreadable_gitignore_in_search_tools_is_logged(tmp_path, monkeypatch, caplog):
    (tmp_path / ".gitignore").write_text("*.log\n")
    _fail_opening(monkeypatch, ".gitignore")
    with caplog.at_level(logging.DEBUG, logger=search_tools.logger.name):
        patterns = search_tools._load_gitignore_patterns(str(tmp_path))
    assert "*.log" not in patterns
    assert any(r.exc_info and ".gitignore" in r.getMessage() for r in caplog.records
               if r.name == search_tools.logger.name and r.levelno == logging.DEBUG)


def test_unreadable_gitignore_in_file_indexer_is_logged(tmp_path, monkeypatch, caplog):
    (tmp_path / ".gitignore").write_text("*.log\n")
    indexer = file_indexer.FileIndexer(str(tmp_path))
    _fail_opening(monkeypatch, ".gitignore")
    with caplog.at_level(logging.DEBUG, logger=file_indexer.logger.name):
        indexer._load_gitignore()
    assert "*.log" not in indexer._gitignore_patterns
    assert any(r.exc_info and ".gitignore" in r.getMessage() for r in caplog.records
               if r.name == file_indexer.logger.name and r.levelno == logging.DEBUG)
