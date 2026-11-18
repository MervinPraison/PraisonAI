"""Failures swallowed in ``praisonaiagents/managed/`` leave a debug trace (T-08).

Each of these used to be ``except Exception: pass``. Behaviour is unchanged:
the same fallback values come back, but a debug record with the traceback now
says what went wrong.
"""

import ast
import logging
from pathlib import Path

import praisonaiagents.managed as managed_pkg
from praisonaiagents.managed import _compute_bridge, _sandbox_adapter
from praisonaiagents.managed.shared_compute import CAPABILITY_PROMPT, SharedCompute

MANAGED_DIR = Path(managed_pkg.__file__).parent

# (file, function) pairs deliberately left as broad silent handlers. None.
KEPT_SILENT = set()


def _silent_broad_handlers():
    found = set()
    for path in sorted(MANAGED_DIR.rglob("*.py")):
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
                    found.add((path.relative_to(MANAGED_DIR).as_posix(), func.name))
    return found


def _debug_records_with_traceback(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_only_deliberate_silent_handlers_remain():
    assert _silent_broad_handlers() == KEPT_SILENT


def test_entry_point_discovery_failure_is_logged_and_returns_empty(monkeypatch, caplog):
    import importlib.metadata

    def boom(**_kw):
        raise RuntimeError("broken metadata")

    monkeypatch.setattr(importlib.metadata, "entry_points", boom)
    with caplog.at_level(logging.DEBUG, logger=_compute_bridge.__name__):
        assert _compute_bridge._entry_point_providers() == {}
    assert _debug_records_with_traceback(caplog, _compute_bridge.__name__)


def test_sandbox_registry_failure_is_logged_and_floor_still_returned(monkeypatch, caplog):
    from praisonaiagents.sandbox import _sandbox_bridge

    def boom():
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(_sandbox_bridge, "get_sandbox_registry", boom)
    with caplog.at_level(logging.DEBUG, logger=_sandbox_adapter.__name__):
        names = _sandbox_adapter.sandbox_only_names()
    assert names == ("novita", "sandlock", "ssh", "subprocess")
    assert _debug_records_with_traceback(caplog, _sandbox_adapter.__name__)


class _FakeProvider:
    provider_name = "fake"

    def provision(self, *a, **kw):  # pragma: no cover - never called
        raise AssertionError

    def execute(self, *a, **kw):  # pragma: no cover - never called
        raise AssertionError


class _AgentRefusingMarker:
    """An agent object that refuses the ``_tools_sandbox`` attribute."""

    name = "refuser"
    backend = None
    tools_run_on = None

    def __init__(self):
        self.tools = []
        self.backstory = "original"

    def __setattr__(self, key, value):
        if key == "_tools_sandbox":
            raise AttributeError("read-only")
        object.__setattr__(self, key, value)


def test_attach_marker_failure_is_logged_and_tools_still_attached(caplog):
    from praisonaiagents.managed import shared_compute

    shared = SharedCompute(_FakeProvider())
    agent = _AgentRefusingMarker()
    with caplog.at_level(logging.DEBUG, logger=shared_compute.__name__):
        shared.attach([agent])

    assert [t.__name__ for t in agent.tools] == [t.__name__ for t in shared.build_tools()]
    assert agent.backstory == f"original\n\n{CAPABILITY_PROMPT}"
    assert len(shared._patched) == 1
    assert _debug_records_with_traceback(caplog, shared_compute.__name__)
