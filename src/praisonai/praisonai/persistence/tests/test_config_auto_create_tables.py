"""PersistenceConfig.auto_create_tables reaches the conversation store (issue #6315)."""

import sqlite3

from praisonai.persistence.config import PersistenceConfig
from praisonai.persistence.factory import create_stores_from_config


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_auto_create_tables_false_skips_ddl(tmp_path):
    db = str(tmp_path / "conv.db")
    config = PersistenceConfig(conversation_store="sqlite", conversation_url=db, auto_create_tables=False)
    create_stores_from_config(config)
    assert _tables(db) == set()


def test_auto_create_tables_default_creates_tables(tmp_path):
    db = str(tmp_path / "conv.db")
    create_stores_from_config(PersistenceConfig(conversation_store="sqlite", conversation_url=db))
    assert _tables(db)


def test_explicit_conversation_option_wins(tmp_path):
    db = str(tmp_path / "conv.db")
    config = PersistenceConfig(
        conversation_store="sqlite", conversation_url=db,
        auto_create_tables=False, conversation_options={"auto_create_tables": True},
    )
    create_stores_from_config(config)
    assert _tables(db)


def test_backend_without_flag_still_works(tmp_path):
    config = PersistenceConfig(
        conversation_store="json", conversation_url=str(tmp_path / "j"), auto_create_tables=False
    )
    assert create_stores_from_config(config)["conversation"] is not None
