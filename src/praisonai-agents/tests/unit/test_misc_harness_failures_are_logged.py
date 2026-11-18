"""Swallowed failures in task routing, push quiet hours, observability
auto-detection, scripted-model accounting and the run ledger leave a debug
trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import logging
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents.process import process as process_mod
from praisonaiagents.push import policy

_FILES = [
    "model_harness/scripted.py",
    "obs/__init__.py",
    "process/process.py",
    "push/policy.py",
    "runs/sqlite_ledger.py",
]

_OBS_ENV_VARS = [
    "LANGFUSE_PUBLIC_KEY", "LANGSMITH_API_KEY", "AGENTOPS_API_KEY", "ARIZE_API_KEY",
    "DATADOG_API_KEY", "MLFLOW_TRACKING_URI", "OPENLIT_API_KEY", "OPIK_API_KEY",
    "PORTKEY_API_KEY", "TRACELOOP_API_KEY", "WANDB_API_KEY", "BRAINTRUST_API_KEY",
]


def _silent_broad_handlers(rel):
    path = Path(praisonaiagents.__file__).parent / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ExceptHandler) and len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)):
            continue
        t = node.type
        names = ([t.id] if isinstance(t, ast.Name)
                 else [e.id for e in t.elts if isinstance(e, ast.Name)]
                 if isinstance(t, ast.Tuple) else [])
        if t is None or {"Exception", "BaseException"} & set(names):
            found.append((rel, node.lineno))
    return found


@pytest.mark.parametrize("rel", _FILES)
def test_no_silent_broad_handlers_left(rel):
    assert _silent_broad_handlers(rel) == []


def _debug_records(caplog, logger_name):
    return [r for r in caplog.records
            if r.name == logger_name and r.levelno == logging.DEBUG and r.exc_info]


def test_routing_to_dict_failure_is_logged_and_raw_output_kept(caplog):
    class _Result:
        raw = "score: 91"

        def to_dict(self):
            raise RuntimeError("to_dict broke")

    task = types.SimpleNamespace(name="grade", result=_Result())
    proc = object.__new__(process_mod.Process)

    with caplog.at_level(logging.DEBUG, logger=process_mod.logger.name):
        context = proc._build_routing_context(task)

    assert context == {"previous_output": "score: 91"}
    assert _debug_records(caplog, process_mod.logger.name)


def test_unknown_time_zone_is_logged_and_naive_time_returned(caplog):
    now = datetime(2026, 11, 18, 22, 30, tzinfo=timezone.utc)

    with caplog.at_level(logging.DEBUG, logger=policy.__name__):
        result = policy._localised_time(now, "Not/AZone")

    assert result == now.timetz().replace(tzinfo=None)
    records = _debug_records(caplog, policy.__name__)
    assert records
    assert "Not/AZone" in records[0].getMessage()


def test_unreadable_langfuse_env_is_logged_and_auto_returns_none(monkeypatch, tmp_path, caplog):
    import praisonaiagents.obs as obs_mod

    (tmp_path / ".praisonai" / "langfuse.env").mkdir(parents=True)  # open() fails
    # Path.home() reads USERPROFILE on Windows, so pin it directly.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    for name in _OBS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with caplog.at_level(logging.DEBUG, logger=obs_mod.__name__):
        result = obs_mod.obs.auto()

    assert result is None
    assert _debug_records(caplog, obs_mod.__name__)
