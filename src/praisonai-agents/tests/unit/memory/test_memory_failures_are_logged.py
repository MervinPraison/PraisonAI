"""Swallowed failures in ``praisonaiagents.memory`` leave a debug trace (T-08).

A vector search that fails, frontmatter that cannot be parsed, or a reset that
cannot delete the old collection all carry on quietly. That behaviour stays,
but the reason must be visible at debug level.
"""

import ast
import logging
from pathlib import Path

import praisonaiagents
from praisonaiagents.memory import docs_manager
from praisonaiagents.memory.adapters import factories

MEMORY_DIR = Path(praisonaiagents.__file__).parent / "memory"

# (file, function) pairs allowed to keep a silent ``except Exception: pass``.
# SqliteMemoryAdapter.close_connections can run from Agent.__del__ when the
# adapter is passed in directly as the agent's memory, so it must not log.
KEPT_SILENT = {("adapters/sqlite_adapter.py", "close_connections")}


def _silent_broad_handlers():
    found = set()
    for path in sorted(MEMORY_DIR.rglob("*.py")):
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
                    found.add((path.relative_to(MEMORY_DIR).as_posix(), func.name))
    return found


def test_only_known_silent_handlers_remain():
    assert _silent_broad_handlers() == KEPT_SILENT


def _records_with_exc_info(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


class _Cursor(list):
    def limit(self, n):
        return _Cursor(self[:n])


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def aggregate(self, pipeline):
        raise RuntimeError("vector index missing")

    def find(self, search_filter):
        return _Cursor(self.docs)


def test_mongo_vector_search_failure_is_logged_and_text_search_used(caplog):
    adapter = factories.MongoDBMemoryAdapter.__new__(factories.MongoDBMemoryAdapter)
    adapter.use_vector_search = True
    adapter._get_embedding = lambda text: [0.1, 0.2]
    collection = _Collection([{"_id": 1, "content": "likes tea", "metadata": {"k": "v"}}])

    with caplog.at_level(logging.DEBUG, logger=factories.logger.name):
        results = adapter._search(collection, "tea", limit=5)

    assert results == [{"id": "1", "text": "likes tea", "metadata": {"k": "v"}, "score": 1.0}]
    assert _records_with_exc_info(caplog, "vector search failed")


def test_chroma_reset_delete_failure_is_logged_and_collection_recreated(caplog):
    calls = []

    class _Client:
        def delete_collection(self, name):
            raise ValueError("no such collection")

        def create_collection(self, name, metadata):
            calls.append(name)
            return "new-collection"

    adapter = factories.ChromaMemoryAdapter.__new__(factories.ChromaMemoryAdapter)
    adapter.client = _Client()
    adapter.collection_name = "memory_store"

    with caplog.at_level(logging.DEBUG, logger=factories.logger.name):
        adapter._reset_collection()

    assert calls == ["memory_store"]
    assert adapter.collection == "new-collection"
    assert _records_with_exc_info(caplog, "Could not delete Chroma collection")


def test_bad_doc_frontmatter_is_logged_and_content_kept(caplog):
    manager = docs_manager.DocsManager.__new__(docs_manager.DocsManager)
    content = "---\ntitle: [unclosed\n---\nbody text\n"

    with caplog.at_level(logging.DEBUG, logger=docs_manager.logger.name):
        frontmatter, remaining = manager._parse_frontmatter(content)

    assert frontmatter == {}
    assert remaining == content
    assert _records_with_exc_info(caplog, "Could not parse doc frontmatter")
