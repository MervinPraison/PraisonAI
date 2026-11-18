"""Failures swallowed by the file, edit, LSP, artifact and resolver tools are logged (T-08).

These blocks are best-effort: the tool must still return the same result when
they fail. Before, the failure left no trace at all, so a stale-file check that
silently stopped working, or artifact metadata that silently went missing, could
not be diagnosed. Now each one leaves a debug record with the traceback.
"""

import ast
import logging
from pathlib import Path

import pytest

import praisonaiagents
from praisonaiagents.approval import reset_yaml_approved_tools, set_yaml_approved_tools

TOOLS_DIR = Path(praisonaiagents.__file__).parent / "tools"

# Files this change covers. Every broad handler in them now logs, so none may
# be a bare ``pass``.
GUARDED_FILES = ("artifact_tools.py", "edit_tools.py", "file_tools.py", "lsp_tools.py", "resolver.py")
KEPT_SILENT: set = set()


def _silent_broad_handlers(path: Path):
    """Return {(file, function)} for each ``except Exception/BaseException/bare: pass``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()

    def visit(node, func):
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
            if (isinstance(child, ast.ExceptHandler) and len(child.body) == 1
                    and isinstance(child.body[0], ast.Pass)):
                t = child.type
                names = ([t.id] if isinstance(t, ast.Name)
                         else [e.id for e in t.elts if isinstance(e, ast.Name)] if isinstance(t, ast.Tuple)
                         else [])
                if t is None or {"Exception", "BaseException"} & set(names):
                    found.add((path.name, func))
            visit(child, name)

    visit(tree, "<module>")
    return found


def test_no_new_silent_broad_handlers_in_guarded_tool_files():
    found = set()
    for name in GUARDED_FILES:
        found |= _silent_broad_handlers(TOOLS_DIR / name)
    assert found == KEPT_SILENT, (
        f"Silent 'except Exception: pass' blocks in tools/: {sorted(found - KEPT_SILENT)}. "
        "Log them with logger.debug(..., exc_info=True)."
    )


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


@pytest.fixture
def file_tools(tmp_path):
    from praisonaiagents.tools.file_tools import FileTools
    from praisonaiagents.workspace import Workspace

    return FileTools(workspace=Workspace(root=tmp_path))


def _broken_hash_recorder(monkeypatch):
    from praisonaiagents.tools import file_tools as ft

    def boom(*_a, **_k):
        raise RuntimeError("hash store unavailable")

    monkeypatch.setattr(ft._file_locks, "record_read_hash", boom)


def test_read_file_logs_failed_hash_record_and_still_returns_content(file_tools, tmp_path, monkeypatch, caplog):
    target = tmp_path / "notes.txt"
    target.write_text("hello\n", encoding="utf-8")
    _broken_hash_recorder(monkeypatch)

    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.tools.file_tools"):
        content = file_tools.read_file(str(target), line_numbers=False)

    assert content == "hello\n"
    recs = _records(caplog, "could not record read hash")
    assert recs and str(target.resolve()) in recs[0].getMessage()
    assert "hash store unavailable" in str(recs[0].exc_info[1])


def test_write_file_logs_failed_hash_record_and_still_writes(file_tools, tmp_path, monkeypatch, caplog):
    target = tmp_path / "out.txt"
    _broken_hash_recorder(monkeypatch)
    token = set_yaml_approved_tools(["write_file"])
    try:
        with caplog.at_level(logging.DEBUG, logger="praisonaiagents.tools.file_tools"):
            ok = file_tools.write_file(str(target), "data")
    finally:
        reset_yaml_approved_tools(token)

    assert ok is True
    assert target.read_text(encoding="utf-8") == "data"
    recs = _records(caplog, "could not record content hash")
    assert recs and str(target.resolve()) in recs[0].getMessage()


def test_artifact_load_logs_unreadable_metadata_and_still_loads(tmp_path, monkeypatch, caplog):
    from praisonaiagents.tools import artifact_tools

    path = tmp_path / "result.artifact"
    path.write_text("payload", encoding="utf-8")
    path.with_suffix(".meta.json").write_text("{not json", encoding="utf-8")

    seen = []

    class FakeStore:
        def load(self, ref):
            seen.append(ref)
            return "payload"

    monkeypatch.setattr(artifact_tools._artifact_stores, "stores", {"default": FakeStore()}, raising=False)

    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.tools.artifact_tools"):
        result = artifact_tools.artifact_load(str(path))

    assert result == "payload"
    assert seen[0].mime_type == "text/plain" and seen[0].checksum == ""
    recs = _records(caplog, "could not read metadata")
    assert recs and str(path) in recs[0].getMessage()


def test_tool_suggestions_log_registry_failure_and_keep_other_names(monkeypatch, caplog):
    from praisonaiagents.tools import registry, resolver
    from praisonaiagents.tools import TOOL_MAPPINGS

    def boom():
        raise RuntimeError("registry broken")

    monkeypatch.setattr(registry, "get_registry", boom)

    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.tools.resolver"):
        names = resolver._available_tool_names()

    assert set(TOOL_MAPPINGS) <= set(names)
    recs = _records(caplog, "could not list registry tools")
    assert recs and "registry broken" in str(recs[0].exc_info[1])
