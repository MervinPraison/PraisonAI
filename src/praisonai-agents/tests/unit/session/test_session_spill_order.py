"""Spilled turns are re-ingested in the order they were written (F-04).

Spill files were named ``<id>.<ms>.<pid>.<random>.json`` and re-ingested in
name order, so two spills in the same millisecond (a user message, then its
reply) came back in random-token order: about one turn in six, the reply
was restored before the question. That made
``test_agent_resume_transient[whole_turn]`` fail about 1 run in 3.
"""

import os
import time

from praisonaiagents.session import store as store_mod
from praisonaiagents.session.store import DefaultSessionStore, SessionMessage


def test_same_millisecond_spills_reingest_in_write_order(tmp_path, monkeypatch):
    spill_dir = tmp_path / "spill"
    monkeypatch.setattr(DefaultSessionStore, "_spill_dir", lambda self: str(spill_dir))
    DefaultSessionStore(session_dir=str(tmp_path)).add_user_message("s", "old")

    writer = DefaultSessionStore(session_dir=str(tmp_path))
    tokens = iter([b"\xff" * 4, b"\x00" * 4])  # the second spill's token sorts first
    real_urandom, frozen = os.urandom, time.time()
    with monkeypatch.context() as m:
        m.setattr(store_mod.os, "urandom", lambda n: next(tokens) if n == 4 else real_urandom(n))
        m.setattr(store_mod.time, "time", lambda: frozen)  # both spills in the same millisecond
        assert writer._spill("s", [SessionMessage("user", "new", timestamp=1.0)])
        assert writer._spill("s", [SessionMessage("assistant", "answer", timestamp=2.0)])

    reader = DefaultSessionStore(session_dir=str(tmp_path))
    assert [m["content"] for m in reader.get_chat_history("s")] == ["old", "new", "answer"]
