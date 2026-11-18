"""Failures swallowed in ``praisonaiagents/plugins/`` leave a debug trace (T-08).

Each of these used to be ``except Exception: pass``. Behaviour is unchanged,
but a debug record with the traceback now says what went wrong.
"""

import ast
import logging
from pathlib import Path

import praisonaiagents.plugins as plugins_pkg
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.plugins import manager as manager_mod
from praisonaiagents.plugins.manager import PluginManager, _write_back
from praisonaiagents.plugins.plugin import Plugin, PluginHook, PluginInfo

PLUGINS_DIR = Path(plugins_pkg.__file__).parent
LOGGER = manager_mod.logger.name

# (file, function) pairs deliberately left as broad silent handlers. None.
KEPT_SILENT = set()


def _silent_broad_handlers():
    found = set()
    for path in sorted(PLUGINS_DIR.rglob("*.py")):
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
                    found.add((path.relative_to(PLUGINS_DIR).as_posix(), func.name))
    return found


def _debug_records_with_traceback(caplog):
    return [r for r in caplog.records
            if r.name == LOGGER and r.levelno == logging.DEBUG and r.exc_info]


def test_logger_is_the_module_logger():
    assert LOGGER == "praisonaiagents.plugins.manager"


def test_only_deliberate_silent_handlers_remain():
    assert _silent_broad_handlers() == KEPT_SILENT


class _FrozenPayload:
    """A hook payload that refuses new attribute values."""

    def __init__(self):
        object.__setattr__(self, "credentials", None)

    def __setattr__(self, key, value):
        raise AttributeError("frozen")


def test_write_back_failure_is_logged_and_payload_unchanged(caplog):
    data = _FrozenPayload()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert _write_back(data, "credentials", {"token": "x"}) is None
    assert data.credentials is None
    records = _debug_records_with_traceback(caplog)
    assert records and "credentials" in records[0].getMessage()


class _MarkerRefusingPlugin(Plugin):
    """A plugin object that refuses the wiring bookkeeping attributes."""

    @property
    def info(self):
        return PluginInfo(name="refuser", hooks=[PluginHook.BEFORE_TOOL])

    def before_tool(self, tool_name, args):
        return args

    def __setattr__(self, key, value):
        if key in ("_wired_into_registry", "_wired_hook_ids"):
            raise AttributeError("read-only")
        object.__setattr__(self, key, value)


def test_wiring_record_failure_is_logged_and_hooks_still_wired(caplog):
    mgr = PluginManager()
    mgr.register(_MarkerRefusingPlugin())
    registry = HookRegistry()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert mgr.wire_into_hook_registry(registry) == 1
    assert registry.has_hooks(HookEvent.BEFORE_TOOL)
    records = _debug_records_with_traceback(caplog)
    assert records and "refuser" in records[0].getMessage()
