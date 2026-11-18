"""Swallowed failures in ``praisonaiagents/context/*.py`` leave a debug trace (T-08).

Each test makes a guarded call raise and checks two things: a debug record with
``exc_info`` is emitted, and the fallback result is exactly what it was before.
"""

import ast
import logging
from pathlib import Path

import praisonaiagents
from praisonaiagents.context import budgeter, monitor, optimizer
from praisonaiagents.context.manager import ContextManager


# Silent broad handlers kept on purpose in context/*.py (context/fast/ has its own
# guard), pinned by (file, enclosing function).
# manager.py _flush_async_writes runs from atexit, where logging may already be torn down.
KEPT_SILENT = {("context/manager.py", "_flush_async_writes")}


def _silent_broad_handlers_by_function():
    root = Path(praisonaiagents.__file__).parent
    found = set()
    for path in sorted((root / "context").glob("*.py")):
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
                    found.add((path.relative_to(root).as_posix(), func.name))
    return found


def test_only_deliberate_silent_handlers_remain():
    assert _silent_broad_handlers_by_function() == KEPT_SILENT


def _debug_records_with_exc(caplog, name):
    return [r for r in caplog.records
            if r.name == name and r.levelno == logging.DEBUG and r.exc_info]


def test_local_window_lookup_failure_is_logged_and_falls_back(monkeypatch, caplog):
    import praisonaiagents.local.embed as embed

    def boom(model):
        raise RuntimeError("probe cache broken")

    monkeypatch.setattr(embed, "context_length_for", boom)
    monkeypatch.setattr(budgeter, "_litellm_model_info", lambda model: None)
    with caplog.at_level(logging.DEBUG, logger=budgeter.__name__):
        limit = budgeter.get_model_limit("gpt-4o-mini")
    assert limit == budgeter.MODEL_LIMITS["gpt-4o-mini"]
    recs = _debug_records_with_exc(caplog, budgeter.__name__)
    assert recs and "gpt-4o-mini" in recs[0].getMessage()


def test_snapshot_callback_failure_is_logged_and_others_still_run(caplog):
    cm = ContextManager(model="gpt-4o-mini")
    seen = []

    def bad(data):
        raise ValueError("callback bug")

    cm.register_snapshot_callback(bad)
    cm.register_snapshot_callback(seen.append)
    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.context.manager"):
        data = cm.capture_llm_boundary([{"role": "user", "content": "hi"}], [])
    assert seen == [data]
    assert _debug_records_with_exc(caplog, "praisonaiagents.context.manager")


def test_llm_summary_failure_is_logged_and_truncation_fallback_used(caplog):
    def boom(messages, max_tokens):
        raise RuntimeError("summarizer down")

    msgs = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "second"}]
    expected = optimizer.SummarizeOptimizer()._create_summary(msgs)
    opt = optimizer.SummarizeOptimizer(llm_summarize_fn=boom)
    with caplog.at_level(logging.DEBUG, logger=optimizer.__name__):
        assert opt._create_summary(msgs) == expected
    assert _debug_records_with_exc(caplog, optimizer.__name__)


def test_tool_output_summary_failure_is_logged_and_original_kept(caplog):
    def boom(content, max_tokens):
        raise RuntimeError("summarizer down")

    msgs = [{"role": "tool", "name": "search", "content": "x" * 3000}] * 3
    opt = optimizer.SummarizeToolOutputsOptimizer(llm_summarize_fn=boom, preserve_recent=0)
    with caplog.at_level(logging.DEBUG, logger=optimizer.__name__):
        result, stats = opt.optimize(list(msgs), target_tokens=10)
    assert result == msgs
    recs = _debug_records_with_exc(caplog, optimizer.__name__)
    assert len(recs) == 3 and "search" in recs[0].getMessage()


def test_unreadable_praisonignore_is_logged(tmp_path, monkeypatch, caplog):
    (tmp_path / ".praisonignore").write_text("*.log\n")
    real = Path.read_text

    def read_text(self, *a, **k):
        if self.name == ".praisonignore":
            raise PermissionError("denied")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", read_text)
    with caplog.at_level(logging.DEBUG, logger=monitor.__name__):
        assert monitor.load_ignore_patterns(str(tmp_path)) == ([], [])
    assert _debug_records_with_exc(caplog, monitor.__name__)
