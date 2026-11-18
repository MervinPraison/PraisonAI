"""Swallowed failures in bot delivery, the event log and the compactor leave a
debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import asyncio
import logging
from pathlib import Path
from unittest import mock

import pytest

import praisonaiagents
from praisonaiagents.bots import BasePlatformAdapter, PlatformCapabilities, SendResult
from praisonaiagents.bots import base as bots_base
from praisonaiagents.bus import event_log
from praisonaiagents.bus.event_log import SqliteEventLog
from praisonaiagents.compaction import compactor as compactor_mod
from praisonaiagents.compaction.compactor import ContextCompactor
from praisonaiagents.context.tokens import estimate_tokens_heuristic

_FILES = [
    "bots/base.py",
    "bus/event_log.py",
    "compaction/compactor.py",
    "frameworks/base.py",
]

# Kept silent on purpose: runs from __del__, possibly during interpreter
# shutdown when module globals (including logging) are gone.
_KEPT = {("frameworks/base.py", "__del__")}


def _silent_broad_handlers(rel):
    path = Path(praisonaiagents.__file__).parent / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
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
                found.append((rel, func.name))
    return found


@pytest.mark.parametrize("rel", _FILES)
def test_only_deliberate_silent_handlers_remain(rel):
    assert set(_silent_broad_handlers(rel)) <= _KEPT
    if rel == "frameworks/base.py":
        assert _silent_broad_handlers(rel) == [("frameworks/base.py", "__del__")]


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


class _TypingFailsBot(BasePlatformAdapter):
    capabilities = PlatformCapabilities(max_message_length=100, supports_typing=True)

    def __init__(self):
        self.sends = []

    async def connect(self, *, is_reconnect=False):
        return True

    async def disconnect(self):
        return None

    async def send(self, chat_id, content, *, reply_to=None, metadata=None):
        self.sends.append((chat_id, content))
        return SendResult(ok=True, message_id="m1", chat_id=chat_id)

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}

    async def send_typing(self, chat_id):
        raise RuntimeError("typing broke")


def test_typing_failure_is_logged_and_message_still_delivered(caplog):
    bot = _TypingFailsBot()
    with caplog.at_level(logging.DEBUG, logger=bots_base.__name__):
        result = asyncio.run(bot.deliver("chat-7", "hello"))

    assert result.ok is True
    assert result.message_id == "m1"
    assert bot.sends == [("chat-7", "hello")]
    records = _debug_records(caplog, bots_base.__name__)
    assert any("chat-7" in r.getMessage() for r in records)


def test_accurate_count_failure_is_logged_and_heuristic_used(monkeypatch, caplog):
    import praisonaiagents.context.tokens as tokens

    monkeypatch.setattr(compactor_mod, "_accurate_tokeniser_available", lambda: True)
    monkeypatch.setattr(tokens, "estimate_tokens_accurate",
                        mock.Mock(side_effect=RuntimeError("tokeniser broke")))
    text = "the quick brown fox jumps over the lazy dog " * 5

    with caplog.at_level(logging.DEBUG, logger=compactor_mod.__name__):
        count = ContextCompactor().estimate_tokens(text)

    assert count == estimate_tokens_heuristic(text)
    assert _debug_records(caplog, compactor_mod.__name__)


def test_event_log_close_failure_is_logged_and_never_raises(caplog):
    log = SqliteEventLog(":memory:")
    real = log._conn
    broken = mock.Mock()
    broken.close.side_effect = RuntimeError("close broke")
    log._conn = broken
    try:
        with caplog.at_level(logging.DEBUG, logger=event_log.logger.name):
            log.close()
    finally:
        real.close()

    broken.close.assert_called_once()
    records = _debug_records(caplog, event_log.logger.name)
    assert any(":memory:" in r.getMessage() for r in records)
