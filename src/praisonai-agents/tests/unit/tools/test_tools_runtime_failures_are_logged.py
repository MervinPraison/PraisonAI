"""Failures swallowed by the circuit breaker, subagent, code bridge and crawl tools are logged (T-08).

These blocks are best-effort: behaviour must not change when they fail. Before,
the failure left no trace at all (a health check that always raised looked the
same as one that returned False). Now each one leaves a debug record with the
traceback.
"""

import asyncio
import ast
import logging
from pathlib import Path

import praisonaiagents

TOOLS_DIR = Path(praisonaiagents.__file__).parent / "tools"

# Covered by the sibling change for file/edit/LSP/artifact/resolver tools
# (test_tools_failures_are_logged.py); this guard covers every other file.
OTHER_GUARD = {"artifact_tools.py", "edit_tools.py", "file_tools.py", "lsp_tools.py", "resolver.py"}

# Kept silent on purpose: _kill_process_tree runs from the atexit hook
# ShellTools._stop_all_background (via _terminate_background on Windows), where
# logging during interpreter shutdown can fail. Two handlers: taskkill and
# process.kill().
KEPT_SILENT = [("shell_tools.py", "_kill_process_tree")] * 2


def _silent_broad_handlers(path: Path):
    """Return [(file, function)] for each ``except Exception/BaseException/bare: pass``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []

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
                    found.append((path.relative_to(TOOLS_DIR).as_posix(), func))
            visit(child, name)

    visit(tree, "<module>")
    return found


def test_only_the_deliberate_silent_handlers_remain_in_tools():
    found = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        if path.relative_to(TOOLS_DIR).as_posix() not in OTHER_GUARD:
            found += _silent_broad_handlers(path)
    assert sorted(found) == sorted(KEPT_SILENT), (
        f"Silent 'except Exception: pass' blocks in tools/: {sorted(found)}. "
        "Log them with logger.debug(..., exc_info=True), or document why one must stay silent."
    )


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_failing_health_check_is_logged_and_circuit_stays_open(caplog):
    from praisonaiagents.tools.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

    calls = []

    async def health_check():
        calls.append(1)
        raise RuntimeError("probe exploded")

    async def failing():
        raise RuntimeError("service down")

    async def scenario():
        breaker = CircuitBreaker(
            "db",
            CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60,
                                 health_check_interval=0.01),
            health_check=health_check,
        )
        try:
            await breaker.acall(failing)
        except RuntimeError:
            pass
        for _ in range(500):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0.01)
        state = breaker.state
        # Close the circuit so the probe loop ends on its own (cancelling it
        # while OPEN makes it schedule a replacement probe).
        task = breaker._health_check_task
        breaker.reset()
        if task is not None:
            await asyncio.wait_for(task, timeout=5)
        return state

    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.tools.circuit_breaker"):
        state = asyncio.run(scenario())

    assert len(calls) >= 2  # the loop kept probing after the first failure
    assert state == CircuitState.OPEN
    recs = _records(caplog, "health check raised")
    assert recs and "'db'" in recs[0].getMessage()
    assert "probe exploded" in str(recs[0].exc_info[1])


def test_unresolvable_link_is_logged_and_kept_as_written(caplog):
    from praisonaiagents.tools.web_crawl_tools import _html_to_markdown

    html = '<p><a href="http://[bad/x">go</a> <a href="/ok">ok</a></p>'
    with caplog.at_level(logging.DEBUG, logger="praisonaiagents.tools.web_crawl_tools"):
        markdown, _ = _html_to_markdown(html, "https://example.com/a/")

    assert markdown == "[go](http://[bad/x) [ok](https://example.com/ok)"
    recs = _records(caplog, "Could not resolve link")
    assert recs and "http://[bad/x" in recs[0].getMessage()
    assert isinstance(recs[0].exc_info[1], ValueError)
