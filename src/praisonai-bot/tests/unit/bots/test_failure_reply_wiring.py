"""Regression tests for canonical bot failure rendering."""

from pathlib import Path

from praisonaiagents.errors import PraisonAIConfigError

from praisonai_bot.bots._failure import failure_reply_text


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
        "telegram.py": 2,
        "discord.py": 3,
        "slack.py": 3,
        "whatsapp.py": 2,
    }

    for filename, minimum in expected_calls.items():
        source = (bots_dir / filename).read_text(encoding="utf-8")
        assert source.count("failure_reply_text(e)") >= minimum


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
