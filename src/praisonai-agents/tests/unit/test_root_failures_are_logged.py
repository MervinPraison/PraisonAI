"""Swallowed failures in the package root, version lookup and outbound
redaction leave a debug trace (T-08).

Each block used to be ``except Exception: pass``. The fallbacks are unchanged;
these tests pin that, and that a debug record with a traceback is written.
"""

import ast
import importlib.metadata
import logging
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents import _config, _version, secrets
from praisonaiagents import telemetry as telemetry_pkg

_FILES = ["__init__.py", "_version.py", "secrets.py"]


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


def test_redaction_failure_is_logged_and_registered_redaction_kept(monkeypatch, caplog):
    monkeypatch.setattr(secrets, "_redaction_values", set())
    secrets.register_secret_for_redaction("t08-registered-value-123")
    text = "token t08-registered-value-123 here"
    expected = secrets.redact_secrets(text)

    def _boom():
        raise RuntimeError("regex broke")

    monkeypatch.setattr(secrets, "_get_credential_shape_re", _boom)
    with caplog.at_level(logging.DEBUG, logger=secrets.__name__):
        result = secrets.redact_outbound(text)

    assert result == expected
    assert "t08-registered-value-123" not in result
    records = _debug_records(caplog, secrets.__name__)
    assert records
    # The text being scrubbed is never put in the log.
    assert all("t08-registered" not in r.getMessage() for r in records)


def test_version_metadata_failure_is_logged_and_unknown_returned(monkeypatch, caplog):
    def _boom(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(_version, "_version_from_source_tree", lambda: None)
    monkeypatch.setattr(importlib.metadata, "version", _boom)
    with caplog.at_level(logging.DEBUG, logger=_version.__name__):
        with pytest.warns(RuntimeWarning, match="Could not determine"):
            result = _version.get_version()

    assert result == "unknown"
    assert _debug_records(caplog, _version.__name__)


def test_telemetry_init_failure_is_logged_and_import_unaffected(monkeypatch, caplog):
    def _boom():
        raise RuntimeError("telemetry broke")

    monkeypatch.setattr(_config, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(telemetry_pkg, "get_telemetry", _boom)
    with caplog.at_level(logging.DEBUG, logger=praisonaiagents.__name__):
        result = praisonaiagents._init_telemetry()

    assert result is None
    assert _debug_records(caplog, praisonaiagents.__name__)
