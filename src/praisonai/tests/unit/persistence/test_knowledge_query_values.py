"""Numbers and field names that knowledge stores write into query text.

``search()`` in clickhouse, surrealdb and cosmosdb (SQL API) writes ``limit``,
``score_threshold`` and the query embedding into the query string. They must be
numbers before they get there; Cosmos field names must be identifiers.
"""

from __future__ import annotations

from unittest import mock

import pytest

BAD_VECTOR = [0.1, "0.2]) as score FROM secret --"]
BAD_LIMIT = ["5; DROP TABLE users", "5 UNION SELECT 1", True, 0, -3]


def _clickhouse():
    from praisonai.persistence.knowledge.clickhouse import ClickHouseKnowledgeStore
    store = object.__new__(ClickHouseKnowledgeStore)
    store.database = "praisonai"
    store._client = mock.MagicMock()
    store._client.query.return_value.result_rows = []
    return store


def _surreal():
    from praisonai.persistence.knowledge.surrealdb_vector import SurrealDBVectorKnowledgeStore
    store = SurrealDBVectorKnowledgeStore(username="u", password="p")
    store._initialized = True
    store._client = mock.MagicMock()
    store._run_async = mock.MagicMock(return_value=[])
    return store


def _cosmos(**kw):
    from praisonai.persistence.knowledge.cosmosdb_vector import CosmosDBVectorKnowledgeStore
    store = CosmosDBVectorKnowledgeStore(connection_string="x", api_mode="sql", **kw)
    store._initialized = True
    store._db = mock.MagicMock()
    store._db.get_container_client.return_value.query_items.return_value = []
    return store


def _sent(store):
    """Query calls that reached the (fake) driver."""
    if getattr(store, "_db", None) is not None:
        return store._db.get_container_client.return_value.query_items.call_args_list
    return store._client.query.call_args_list


STORES = {"clickhouse": _clickhouse, "surrealdb": _surreal, "cosmosdb": _cosmos}


@pytest.mark.parametrize("make", STORES.values(), ids=STORES.keys())
@pytest.mark.parametrize("limit", BAD_LIMIT)
def test_search_rejects_non_integer_limit(make, limit):
    store = make()
    with pytest.raises((ValueError, TypeError)):
        store.search("docs", [0.1, 0.2], limit=limit)
    assert _sent(store) == []


@pytest.mark.parametrize("make", [_clickhouse, _surreal], ids=["clickhouse", "surrealdb"])
def test_search_rejects_non_numeric_embedding(make):
    store = make()
    with pytest.raises(ValueError):
        store.search("docs", BAD_VECTOR)
    assert _sent(store) == []


def test_clickhouse_rejects_non_numeric_threshold():
    store = _clickhouse()
    with pytest.raises(ValueError):
        store.search("docs", [0.1], score_threshold="0 OR 1=1")
    assert _sent(store) == []


def test_clickhouse_search_text_holds_only_numbers():
    store = _clickhouse()
    store.search("docs", [1, 0.5], limit=3, score_threshold=0.25)
    (query,), _ = store._client.query.call_args
    assert "[1.0,0.5]" in query and ">= 0.25" in query and query.rstrip().endswith("LIMIT 3")


def test_surreal_search_text_holds_only_numbers():
    store = _surreal()
    store.search("docs", [1, 0.5], limit=4)
    (query,), _ = store._client.query.call_args
    assert "[1.0, 0.5]" in query and "LIMIT 4" in query


@pytest.mark.parametrize("field", ["text_field", "embedding_field"])
def test_cosmos_rejects_field_names_that_are_not_identifiers(field):
    with pytest.raises(ValueError):
        _cosmos(**{field: "content, c.password"})


def test_cosmos_sql_search_still_builds_query():
    store = _cosmos()
    store.search("docs", [0.1], limit=7)
    kwargs = store._db.get_container_client.return_value.query_items.call_args.kwargs
    assert "SELECT TOP 7 c.id, c.content" in kwargs["query"]
    assert kwargs["parameters"] == [{"name": "@embedding", "value": [0.1]}]


def test_guard_every_store_writing_numbers_into_query_text_is_covered():
    """Every store whose f-strings interpolate a search value is listed and checks ``limit``."""
    import ast
    from pathlib import Path
    from praisonai.persistence.knowledge import base

    names = {"limit", "embedding_str", "score_threshold", "top_k"}
    found = set()
    for path in Path(base.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FormattedValue):
                inner = node.value.args[0] if isinstance(node.value, ast.Call) and node.value.args else node.value
                if getattr(inner, "id", None) in names:
                    found.add(path.stem.replace("_vector", ""))
    assert found == set(STORES) | {"redis", "valkey"}
    for stem in found:
        path = Path(base.__file__).parent / (stem + ("" if stem == "clickhouse" else "_vector") + ".py")
        assert 'limit = validate_dimension(limit, name="limit")' in path.read_text(), stem
