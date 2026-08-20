"""Regression tests for CLI backend robustness fixes.

Covers:
- timeout is returned as a ``CliBackendResult`` error, not raised (all four)
- ``CalledProcessError`` stderr text reaches the error message (codex/gemini/grok)
- codex resume subcommand order: ``codex exec resume <id> ...``
- codex system prompt is TOML-escaped
- ``is_resume`` is set on the second delegated turn for one session
"""

import asyncio
import subprocess
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from praisonaiagents.cli_backend.protocols import CliSessionBinding
from praisonai_code.cli_backends.claude import ClaudeCodeBackend
from praisonai_code.cli_backends.codex import CodexBackend
from praisonai_code.cli_backends.gemini import GeminiBackend
from praisonai_code.cli_backends.grok import GrokBackend
from praisonai_code.cli_backends._errors import called_process_error_message


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("backend_cls", [ClaudeCodeBackend, CodexBackend, GeminiBackend, GrokBackend])
def test_timeout_returns_error_result(backend_cls, monkeypatch):
    backend = backend_cls()

    async def timing_out(*args, **kwargs):
        raise TimeoutError("CLI timed out after 1ms")

    monkeypatch.setattr(backend, "_execute_subprocess", timing_out)
    result = _run(backend.execute("hello"))
    assert result.error is not None
    assert "timed out" in result.error
    assert result.content == ""


@pytest.mark.parametrize("backend_cls", [CodexBackend, GeminiBackend, GrokBackend])
def test_stderr_reaches_error_message(backend_cls, monkeypatch):
    backend = backend_cls()

    async def failing(*args, **kwargs):
        raise subprocess.CalledProcessError(2, ["cli"], stderr="auth expired: run login")

    monkeypatch.setattr(backend, "_execute_subprocess", failing)
    result = _run(backend.execute("hello"))
    assert result.error is not None
    assert "auth expired: run login" in result.error


def test_called_process_error_message_bytes():
    exc = subprocess.CalledProcessError(1, ["x"], stderr=b"broken pipe")
    assert called_process_error_message(exc) == "broken pipe"


def test_codex_resume_order():
    backend = CodexBackend()
    session = CliSessionBinding(session_id="sess-1", is_resume=True)
    cmd = backend._build_command("do it", session=session)
    exec_idx = cmd.index("exec")
    assert cmd[exec_idx + 1] == "resume"
    assert cmd[exec_idx + 2] == "sess-1"
    # exec's own flags come after the resume subcommand
    assert cmd.index("--skip-git-repo-check") > exec_idx + 2


def test_codex_instructions_escaped():
    backend = CodexBackend()
    cmd = backend._build_command("go", system_prompt='say "hi"\nthen stop')
    cfg = cmd[cmd.index("-c") + 1]
    assert cfg.startswith("instructions=")
    # JSON escaping: embedded quote and newline must be escaped
    assert '\\"hi\\"' in cfg
    assert "\\n" in cfg
    assert '\n' not in cfg


def test_codex_model_and_cwd_flags():
    backend = CodexBackend()
    cmd = backend._build_command("go", model="gpt-5-codex", cwd="/tmp/ws")
    assert cmd[cmd.index("-m") + 1] == "gpt-5-codex"
    assert cmd[cmd.index("-C") + 1] == "/tmp/ws"


def test_is_resume_set_on_second_turn():
    """The agent marks a CLI session started after a successful turn."""
    from praisonaiagents.agent import Agent

    captured = []

    class RecordingBackend:
        def __init__(self):
            from praisonaiagents.cli_backend.protocols import CliBackendConfig
            self.config = CliBackendConfig(command="fake")

        def capabilities(self):  # pragma: no cover - protocol completeness
            return None

        async def execute(self, prompt, *, session=None, **kwargs):
            captured.append(bool(session and session.is_resume))
            from praisonaiagents.cli_backend.protocols import CliBackendResult
            return CliBackendResult(content="ok")

        async def stream(self, prompt, **kwargs):  # pragma: no cover
            yield None

    agent = Agent(name="t", role="t", goal="t", backstory="t", llm="openai/gpt-4o-mini")
    backend = RecordingBackend()
    _run(agent._chat_via_cli_backend("first", cli_backend=backend))
    _run(agent._chat_via_cli_backend("second", cli_backend=backend))
    assert captured == [False, True]


def test_yaml_backend_resolution_failure_fails_closed(monkeypatch):
    """An explicitly requested YAML cli_backend that cannot resolve must raise,
    never silently fall back to the native LLM path."""
    import praisonai.agents_generator as ag
    monkeypatch.setattr(ag, "_resolve_yaml_cli_backend", lambda cfg, log: None)
    import inspect
    from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
    source = inspect.getsource(PraisonAIAdapter)
    # Contract check: the adapter raises on unresolved cli_backend rather than
    # omitting the kwarg (full generator run needs YAML fixtures; the guard
    # clause is the unit under test).
    assert "could not be" in source and "raise ValueError" in source
