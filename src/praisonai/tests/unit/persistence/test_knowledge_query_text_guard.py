"""Values that knowledge stores write into query text are checked first.

Identifiers and DDL numbers cannot be bound as query parameters, so every
store that builds SQL/CQL/N1QL text must pass them through the shared
helpers in ``persistence/knowledge/base.py`` (``validate_identifier``,
``validate_dimension``). No database is needed: fake drivers record what
would have been sent.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest import mock

import pytest

from praisonai.persistence.knowledge import base
from praisonai.persistence.knowledge.base import validate_identifier


def test_validate_identifier_rejects_trailing_newline():
    # ``re.match`` with ``$`` accepted "name\n"; fullmatch does not.
    with pytest.raises(ValueError):
        validate_identifier("name\n")


# --- Couchbase: bucket / scope / collection go into N1QL text ----------------

def _couchbase(**kw):
    from praisonai.persistence.knowledge.couchbase import CouchbaseKnowledgeStore

    # The store lacks ``collection_exists`` on main and cannot be built as is;
    # fill the gap here so the constructor check is what gets tested.
    class _Store(CouchbaseKnowledgeStore):
        def collection_exists(self, name):
            return True

    return _Store(connection_string="couchbase://x", username="u", password="p", **kw)


@pytest.mark.parametrize("field", ["bucket_name", "scope_name", "collection_name"])
@pytest.mark.parametrize("bad", [
    "b`.`s`.`c` WHERE 1=1 OR `x",
    "b` ; DELETE FROM `other",
    "name with space",
    "name\n",
    "",
])
def test_couchbase_rejects_keyspace_names_that_leave_backticks(field, bad):
    with pytest.raises(ValueError):
        _couchbase(**{field: bad})


def test_couchbase_accepts_real_names_and_queries_quoted_keyspace():
    store = _couchbase(bucket_name="travel-sample", scope_name="_default", collection_name="my%docs")
    store._initialized = True
    store._cluster = mock.Mock()
    store._cluster.query.return_value = [{"count": 3}]
    assert store.count("ignored") == 3
    (query,), _ = store._cluster.query.call_args
    assert query == "SELECT COUNT(*) as count FROM `travel-sample`.`_default`.`my%docs`"


# --- SingleStore: dimension goes into CREATE TABLE ... VECTOR(n) -------------

@pytest.mark.parametrize("bad", ["3) ; DROP TABLE users; -- ", 0, -1, True, 1.5, 10**9])
def test_singlestore_rejects_bad_dimension_before_sql(bad):
    from praisonai.persistence.knowledge.singlestore_vector import SingleStoreVectorKnowledgeStore
    store = SingleStoreVectorKnowledgeStore(host="h", database="d", user="u", password="p")
    store._initialized = True
    store._conn = mock.MagicMock()
    with pytest.raises(ValueError):
        store.create_collection("docs", dimension=bad)
    store._conn.cursor.assert_not_called()


def test_singlestore_create_collection_still_works():
    from praisonai.persistence.knowledge.singlestore_vector import SingleStoreVectorKnowledgeStore
    store = SingleStoreVectorKnowledgeStore(host="h", database="d", user="u", password="p")
    store._initialized = True
    store._conn = mock.MagicMock()
    store.create_collection("docs", dimension=768)
    cur = store._conn.cursor.return_value.__enter__.return_value
    assert "VECTOR(768)" in cur.execute.call_args[0][0]


# --- guard: every store that writes query text uses the shared helpers -------

KNOWLEDGE_DIR = Path(base.__file__).parent
# Modules that build SQL/CQL/N1QL text with f-strings. Adding a store that does
# so means adding it here and validating what it interpolates.
QUERY_TEXT_STORES = {
    "cassandra.py",
    "clickhouse.py",
    "cosmosdb_vector.py",
    "couchbase.py",
    "pgvector.py",
    "singlestore_vector.py",
    "surrealdb_vector.py",
}
# Stores whose interpolated names come only from fixed config fields checked elsewhere.
NO_IDENTIFIER_HELPER = {"cosmosdb_vector.py"}
_SQL_WORD = re.compile(r"\b(?:FROM|TABLE|INTO|UPDATE|SELECT|DELETE|VECTOR\()")


def _builds_query_text(source: str) -> bool:
    """True if any f-string with an interpolated value contains a query keyword."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.JoinedStr) and any(isinstance(v, ast.FormattedValue) for v in node.values):
            text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
            if _SQL_WORD.search(text):
                return True
    return False


def test_guard_query_text_stores_are_listed():
    found = {p.name for p in KNOWLEDGE_DIR.glob("*.py")
             if p.name != "base.py" and _builds_query_text(p.read_text())}
    assert found == QUERY_TEXT_STORES


@pytest.mark.parametrize("module", sorted(QUERY_TEXT_STORES - NO_IDENTIFIER_HELPER))
def test_guard_query_text_stores_use_identifier_helper(module):
    source = (KNOWLEDGE_DIR / module).read_text()
    assert re.search(r"from \.base import [^\n]*validate_identifier", source), module
    assert "validate_identifier(" in source.split("from .base import", 1)[1].split("\n", 1)[1]


@pytest.mark.parametrize("module", ["cassandra.py", "pgvector.py", "singlestore_vector.py"])
def test_guard_dimension_in_ddl_uses_dimension_helper(module):
    source = (KNOWLEDGE_DIR / module).read_text()
    if re.search(r"\{dimension\}|\{dim\}", source):
        assert "validate_dimension(" in source, module
