"""Natural-language queries must recall facts from the SQLite adapter (#5942)."""

import pytest

from praisonaiagents.memory.adapters.sqlite_adapter import SqliteMemoryAdapter


@pytest.fixture
def adapter(tmp_path):
    a = SqliteMemoryAdapter(short_db=str(tmp_path / "s.db"), long_db=str(tmp_path / "l.db"))
    yield a
    a.close_connections()


@pytest.mark.parametrize("query", [
    "dark mode",
    "user prefers Python",
    "Which mode does the user prefer?",
    "What language does the user work in?",
])
def test_long_term_matches_on_words(adapter, query):
    adapter.store_long_term("The user prefers dark mode and works in Python.")
    adapter.store_long_term("The weather is sunny.")
    results = adapter.search_long_term(query)
    assert results and "dark mode" in results[0]["text"]


def test_exact_phrase_ranks_first_and_unrelated_query_misses(adapter):
    adapter.store_short_term("python tips")
    adapter.store_short_term("I write python code daily")
    assert adapter.search_short_term("write python")[0]["text"] == "I write python code daily"
    assert adapter.search_short_term("zebra") == []
