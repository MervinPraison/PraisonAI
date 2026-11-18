"""Swallowed failures in the async tool path leave a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import asyncio
import difflib
import logging
from pathlib import Path
from unittest import mock

import pytest

import praisonaiagents
from praisonaiagents import Agent
from praisonaiagents.agent import execution_mixin

_FILES = ["agent/execution_mixin.py", "agent/sandbox_mixin.py"]
_LOGGER = execution_mixin.__name__


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
def test_no_silent_broad_handlers_left(rel):
    assert _silent_broad_handlers(rel) == []


def lookup(text: str) -> str:
    """Look something up."""
    return "R:" + text


def _agent():
    return Agent(name="t", instructions="x", tools=[lookup], model="gpt-4o-mini")


def _debug_records(caplog, needle):
    return [r for r in caplog.records
            if r.name == _LOGGER and r.levelno == logging.DEBUG and r.exc_info
            and needle in r.getMessage()]


def test_fence_failure_is_logged_and_raw_result_returned(caplog):
    agent = _agent()
    with mock.patch("praisonaiagents.tools.trust.wrap_if_external",
                    side_effect=RuntimeError("trust broke")):
        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            result = asyncio.run(agent.execute_tool_async("lookup", {"text": "x"}))

    assert result == "R:x"
    assert _debug_records(caplog, "external-content fence")


def test_close_match_failure_is_logged_and_error_has_no_hint(caplog):
    agent = _agent()
    with mock.patch.object(difflib, "get_close_matches",
                           side_effect=RuntimeError("difflib broke")):
        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            result = asyncio.run(agent.execute_tool_async("lookp", {"text": "x"}))

    assert result == {
        "error": "Tool 'lookp' not found. Available tools: ['lookup']",
        "available_tools": ["lookup"],
    }
    assert _debug_records(caplog, "closest-match hint")
