"""Regression tests for issue #6294: no root log handler by default."""
import logging


def test_import_leaves_root_logging_to_host(monkeypatch):
    from praisonaiagents import _logging

    root = logging.getLogger()
    monkeypatch.delenv("LOGLEVEL", raising=False)
    monkeypatch.setattr(root, "handlers", [])
    _logging.configure_root_logger()
    assert root.handlers == []


def test_explicit_loglevel_still_installs_root_handler(monkeypatch):
    from praisonaiagents import _logging

    root = logging.getLogger()
    monkeypatch.setenv("LOGLEVEL", "WARNING")
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", root.level)
    _logging.configure_root_logger()
    assert root.handlers


def test_structured_logging_works_without_loglevel(monkeypatch):
    from praisonaiagents import _logging

    root = logging.getLogger()
    monkeypatch.delenv("LOGLEVEL", raising=False)
    monkeypatch.setenv("PRAISONAI_STRUCTURED_LOGS", "true")
    monkeypatch.setattr(root, "handlers", [])
    _logging.configure_root_logger()
    _logging.configure_structured_logging()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, _logging.StructuredFormatter)
