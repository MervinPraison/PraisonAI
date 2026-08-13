"""Regression tests for canonical bot failure rendering."""

import ast
from pathlib import Path

from praisonaiagents.errors import PraisonAIConfigError

from praisonai_bot.bots._failure import failure_reply_text


def _count_failure_replies_in_handlers(source: str) -> int:
    """Count ``failure_reply_text(e)`` calls that live inside ``except`` handlers.

    AST-based so that comments, strings, or dead code outside an exception
    handler cannot satisfy the wiring contract — only genuine terminal
    failure paths count.
    """
    count = 0
    for handler in ast.walk(ast.parse(source)):
        if not isinstance(handler, ast.ExceptHandler):
            continue
        for node in ast.walk(handler):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "failure_reply_text"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == (handler.name or "e")
            ):
                count += 1
    return count


def test_failure_reply_uses_core_taxonomy_and_hides_raw_exception():
    error = PraisonAIConfigError(
        "secret-token-should-not-leak",
        config_key="OPENAI_API_KEY",
        remediation_hint="Run `praisonai onboard`, then resend.",
    )

    reply = failure_reply_text(error)

    assert reply == "I couldn't complete that. Run `praisonai onboard`, then resend."
    assert "secret-token" not in reply


def test_terminal_agent_paths_use_the_canonical_renderer():
    bots_dir = Path(__file__).parents[3] / "praisonai_bot" / "bots"
    expected_calls = {
        "telegram.py": 3,
        "discord.py": 3,
        "slack.py": 3,
        "whatsapp.py": 2,
    }

    for filename, minimum in expected_calls.items():
        source = (bots_dir / filename).read_text(encoding="utf-8")
        wired = _count_failure_replies_in_handlers(source)
        assert wired >= minimum, f"{filename}: {wired} handler calls < {minimum}"


def test_retry_paths_do_not_interpolate_raw_exception():
    bots_dir = Path(__file__).parents[3] / "praisonai_bot" / "bots"
    for filename in ("telegram.py", "discord.py", "slack.py"):
        source = (bots_dir / filename).read_text(encoding="utf-8")
        assert "Retry failed: {e}" not in source


def test_failure_reply_falls_back_when_core_renderer_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "praisonaiagents.bots.failure":
            raise ImportError("simulated older core without bots.failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    reply = failure_reply_text(RuntimeError("secret-token-should-not-leak"))

    assert "secret-token" not in reply
    assert reply
