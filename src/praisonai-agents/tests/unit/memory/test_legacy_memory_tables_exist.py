"""R-02 (crash half): the direct-SQLite memory paths find their tables.

They read and write ``short_mem`` / ``long_mem``, which nothing created, so a
chroma-backed agent raised ``sqlite3.OperationalError: no such table:
long_mem`` out of ``chat()`` on a later turn, and a failed adapter write fell
back into the same missing table (X-12).
"""

import pytest

from praisonaiagents.memory.memory import Memory


class _FailingAdapter:
    def store_short_term(self, *a, **k):
        raise RuntimeError("embeddings unavailable")

    def search_short_term(self, *a, **k):
        raise RuntimeError("embeddings unavailable")


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    return Memory(config={"short_db": str(tmp_path / "stm.db"), "long_db": str(tmp_path / "ltm.db")})


def test_both_tables_exist_on_a_fresh_store(memory):
    for conn, table in ((memory._get_stm_conn(), "short_mem"), (memory._get_ltm_conn(), "long_mem")):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)


def test_failed_adapter_write_falls_back_instead_of_raising(memory):
    memory.memory_adapter = _FailingAdapter()
    ident = memory.store_short_term("Session state: {'k': 'v'}")
    rows = memory._get_stm_conn().execute("SELECT id, content FROM short_mem").fetchall()
    assert rows == [(ident, "Session state: {'k': 'v'}")]
