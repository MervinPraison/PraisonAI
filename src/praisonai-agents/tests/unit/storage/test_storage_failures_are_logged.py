"""T-08, storage/: failures that used to vanish in 'except Exception: pass'
are logged at debug, and best-effort clean-up of files only swallows OSError.
"""
import logging
import sys
from pathlib import Path

import pytest

import praisonaiagents.storage.base as base
import praisonaiagents.storage.sqlite as sq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_silent_except_ratchet import _silent_handlers  # noqa: E402


def test_storage_has_no_silent_broad_handlers():
    assert [h for h in _silent_handlers() if h.startswith("storage/")] == []


class _Conn:
    """WAL is accepted; PRAGMA synchronous fails (a silent durability downgrade)."""

    def execute(self, sql):
        if sql.startswith("PRAGMA synchronous"):
            raise RuntimeError("synchronous refused")
        return self

    def fetchone(self):
        return ("wal",)


def test_failed_synchronous_pragma_is_logged(caplog):
    with caplog.at_level(logging.DEBUG, logger=sq.logger.name):
        assert sq.apply_wal_with_fallback(_Conn(), "/tmp/x.db") == "wal"
    rec = [r for r in caplog.records if "synchronous=FULL" in r.getMessage()]
    assert rec and isinstance(rec[0].exc_info[1], RuntimeError)


def test_unreadable_session_is_listed_and_logged(tmp_path, caplog):
    (tmp_path / "bad.json").write_text("{not json")
    with caplog.at_level(logging.DEBUG, logger=base.logger.name):
        sessions = base.list_json_sessions(tmp_path)
    assert [s.path.name for s in sessions] == ["bad.json"]
    rec = [r for r in caplog.records if "bad.json" in r.getMessage()]
    assert rec and rec[0].exc_info is not None
