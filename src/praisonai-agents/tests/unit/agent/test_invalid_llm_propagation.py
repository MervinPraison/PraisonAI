"""Unit and regression tests for invalid ``llm`` handling & exception propagation (#5956).

Verifies that ``Agent.start()``, ``Agent.run()``, ``Agent.chat()``, and their
async counterparts (``astart()``, ``arun()``, ``achat()``) raise ``LLMError``
to callers when configured with an invalid ``llm`` parameter or when the
provider rejects the model, even after the Rich UI renderer displays the error,
and never leak API keys in ``str(exc)`` or Rich UI output.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from praisonaiagents import Agent
from praisonaiagents.errors import LLMError, PraisonAIError, sanitize_llm_error_message

INVALID_MODEL = "not-a-real-model-xyz"
SECRET_API_KEY = "sk-proj-supersecretkey1234567890abcdef"


def _make_not_found_error(
    model: str = INVALID_MODEL, secret: str = ""
) -> openai.NotFoundError:
    """Construct a realistic OpenAI 404 NotFoundError without network I/O."""
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    detail = f"The model `{model}` does not exist or you do not have access to it."
    if secret:
        detail += f" (api_key={secret} Bearer {secret})"
    resp = httpx.Response(
        404,
        request=req,
        json={
            "error": {
                "message": detail,
                "type": "invalid_request_error",
                "param": None,
                "code": "model_not_found",
            }
        },
    )
    return openai.NotFoundError(
        f"Error code: 404 - {{'error': {{'message': {detail!r}, 'code': 'model_not_found'}}}}",
        response=resp,
        body={"error": {"message": detail, "code": "model_not_found"}},
    )


def _wire_failing_openai_client(agent: Agent, error: Exception) -> MagicMock:
    """Attach a mock OpenAIClient whose sync and async transports raise ``error``."""
    client = MagicMock()
    client.api_key = SECRET_API_KEY
    client.build_messages.side_effect = lambda prompt, **kw: (
        [{"role": "user", "content": str(prompt)}],
        prompt,
    )
    client.sync_client.chat.completions.create.side_effect = error
    client.async_client.chat.completions.create = AsyncMock(side_effect=error)
    client.chat_completion_with_tools.side_effect = error
    client.achat_completion_with_tools = AsyncMock(side_effect=error)
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None
    return client


class TestSyncInvalidModelPropagation:
    """Sync start(), run(), and chat() must raise LLMError on invalid models."""

    def test_start_raises_on_invalid_model_non_tty(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error())

        with pytest.raises(LLMError) as exc_info:
            agent.start("Say hello")

        exc = exc_info.value
        assert isinstance(exc, PraisonAIError)
        assert exc.model_name == INVALID_MODEL
        assert INVALID_MODEL in str(exc)
        assert exc.error_category == "model_not_found"
        assert exc.is_retryable is False
        assert agent._last_stop_reason == "error"
        assert agent.chat_history == []

    def test_start_raises_on_invalid_model_tty_after_rich_display(self, monkeypatch):
        """Rich UI display_error may render the error, but start() MUST still raise."""
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

        displayed_errors: list[str] = []
        from praisonaiagents.agent import chat_mixin

        real_get_display = chat_mixin._get_display_functions

        def _capturing_display_functions():
            funcs = dict(real_get_display())
            orig_display_error = funcs["display_error"]

            def _record_error(msg, *args, **kwargs):
                displayed_errors.append(str(msg))
                return orig_display_error(msg, *args, **kwargs)

            funcs["display_error"] = _record_error
            return funcs

        monkeypatch.setattr(
            chat_mixin, "_get_display_functions", _capturing_display_functions
        )

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL, output="verbose")
        client = _wire_failing_openai_client(
            agent, _make_not_found_error(secret=SECRET_API_KEY)
        )

        with pytest.raises(LLMError) as exc_info:
            agent.start("Say hello")

        assert exc_info.value.model_name == INVALID_MODEL
        assert exc_info.value.error_category == "model_not_found"
        # Rich UI rendered the error AND exception still propagated
        assert len(displayed_errors) >= 1
        for rendered in displayed_errors:
            assert SECRET_API_KEY not in rendered
        # Provider must only be called once (steering wrapper must not re-run chat on LLMError)
        total_calls = (
            client.chat_completion_with_tools.call_count
            + client.achat_completion_with_tools.await_count
        )
        assert total_calls == 1

    def test_start_stream_raises_on_invalid_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error())

        with pytest.raises(LLMError) as exc_info:
            list(agent.start("Say hello", stream=True))

        assert exc_info.value.model_name == INVALID_MODEL
        assert exc_info.value.__cause__ is not None

    def test_run_raises_on_invalid_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error())

        with pytest.raises(LLMError) as exc_info:
            agent.run("Say hello")

        assert exc_info.value.model_name == INVALID_MODEL
        assert exc_info.value.error_category == "model_not_found"
        assert agent.chat_history == []

    def test_run_return_outcome_captures_llm_error_as_failed(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error(secret=SECRET_API_KEY))

        outcome = agent.run("Say hello", return_outcome=True)
        assert outcome.reason == "failed"
        assert outcome.succeeded is False
        assert outcome.error is not None
        assert INVALID_MODEL in outcome.error
        assert SECRET_API_KEY not in outcome.error

    def test_chat_raises_on_invalid_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error())

        with pytest.raises(LLMError) as exc_info:
            agent.chat("Say hello")

        assert exc_info.value.model_name == INVALID_MODEL
        assert exc_info.value.error_category == "model_not_found"
        assert agent.chat_history == []


class TestAsyncInvalidModelPropagation:
    """Async astart(), arun(), and achat() must raise LLMError (including TTY stream)."""

    @pytest.mark.asyncio
    async def test_astart_non_tty_raises_llm_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error())

        with pytest.raises(LLMError) as exc_info:
            await agent.astart("Say hello")

        assert exc_info.value.model_name == INVALID_MODEL
        assert exc_info.value.error_category == "model_not_found"
        assert agent.chat_history == []

    @pytest.mark.asyncio
    async def test_astart_tty_streaming_raises_llm_error_via_real_openai_client(
        self, monkeypatch
    ):
        """Regression: OpenAIClient.process_stream_response_async previously returned None."""
        from praisonaiagents.llm.openai_client import OpenAIClient

        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        real_client = OpenAIClient(api_key=SECRET_API_KEY)
        fake_async = MagicMock()
        fake_async.chat.completions.create = AsyncMock(
            side_effect=_make_not_found_error()
        )
        real_client._async_client = fake_async
        agent._Agent__openai_client = real_client
        agent._unified_dispatcher = None

        with pytest.raises(LLMError) as exc_info:
            await agent.astart("Say hello")

        assert exc_info.value.model_name == INVALID_MODEL
        assert exc_info.value.error_category == "model_not_found"
        assert agent.chat_history == []

    @pytest.mark.asyncio
    async def test_arun_and_achat_raise_llm_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)

        agent = Agent(instructions="Reply with OK", llm=INVALID_MODEL)
        _wire_failing_openai_client(agent, _make_not_found_error())

        with pytest.raises(LLMError):
            await agent.arun("Say hello")
        assert agent.chat_history == []

        with pytest.raises(LLMError):
            await agent.achat("Say hello")
        assert agent.chat_history == []


class TestCustomLLMAndInvalidParameterInitialization:
    """Custom provider strings, dict configs, blank strings, and invalid objects."""

    @pytest.mark.parametrize(
        "llm_param,expected_model",
        [
            (f"openai/{INVALID_MODEL}", f"openai/{INVALID_MODEL}"),
            ({"model": f"openai/{INVALID_MODEL}"}, f"openai/{INVALID_MODEL}"),
        ],
    )
    def test_custom_llm_sync_methods_raise_llm_error(
        self, monkeypatch, llm_param, expected_model
    ):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

        agent = Agent(instructions="Reply with OK", llm=llm_param)
        assert agent._using_custom_llm is True
        agent.llm_instance.get_response = MagicMock(
            side_effect=_make_not_found_error(
                model=expected_model, secret=SECRET_API_KEY
            )
        )

        for method_name in ("start", "run", "chat"):
            with pytest.raises(LLMError) as exc_info:
                getattr(agent, method_name)("Say hello")
            exc = exc_info.value
            assert exc.model_name == expected_model
            assert exc.error_category == "model_not_found"
            assert SECRET_API_KEY not in str(exc)
            assert agent.chat_history == []

    @pytest.mark.asyncio
    async def test_custom_llm_async_methods_raise_llm_error(self, monkeypatch):
        expected_model = f"openai/{INVALID_MODEL}"
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

        agent = Agent(instructions="Reply with OK", llm=expected_model)
        agent.llm_instance.get_response_async = AsyncMock(
            side_effect=_make_not_found_error(
                model=expected_model, secret=SECRET_API_KEY
            )
        )

        for method_name in ("astart", "arun", "achat"):
            with pytest.raises(LLMError) as exc_info:
                await getattr(agent, method_name)("Say hello")
            exc = exc_info.value
            assert exc.model_name == expected_model
            assert exc.error_category == "model_not_found"
            assert SECRET_API_KEY not in str(exc)
            assert agent.chat_history == []

    @pytest.mark.parametrize("bad_llm", ["", "   ", 12345, object()])
    def test_invalid_llm_value_raises_llm_error_across_sync_entrypoints(
        self, monkeypatch, bad_llm
    ):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

        agent = Agent(instructions="Reply with OK", llm=bad_llm)
        assert agent._using_custom_llm is False

        for method_name in ("start", "run", "chat"):
            with pytest.raises(LLMError) as exc_info:
                getattr(agent, method_name)("Say hello")
            assert exc_info.value.error_category == "model_not_found"
            assert exc_info.value.is_retryable is False
            assert agent.chat_history == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_llm", ["", "   ", 12345, object()])
    async def test_invalid_llm_value_raises_llm_error_across_async_entrypoints(
        self, monkeypatch, bad_llm
    ):
        monkeypatch.setenv("OPENAI_API_KEY", SECRET_API_KEY)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

        agent = Agent(instructions="Reply with OK", llm=bad_llm)

        for method_name in ("astart", "arun", "achat"):
            with pytest.raises(LLMError) as exc_info:
                await getattr(agent, method_name)("Say hello")
            assert exc_info.value.error_category == "model_not_found"
            assert exc_info.value.is_retryable is False
            assert agent.chat_history == []


class TestSecretRedactionAndProcessExit:
    """API keys must never appear in str(exc), and unhandled scripts must exit non-zero."""

    def test_no_api_key_in_str_exc(self, monkeypatch):
        env_secret = "custom-provider-secret-987654321"
        monkeypatch.setenv("OPENAI_API_KEY", env_secret)

        raw_msg = (
            f"Authentication/model failure for {INVALID_MODEL}: "
            f"Bearer {SECRET_API_KEY}, api_key={env_secret}, raw={env_secret}"
        )
        err = LLMError(
            raw_msg,
            model_name=INVALID_MODEL,
            agent_id="test-agent",
            error_category="model_not_found",
        )

        rendered = str(err)
        assert INVALID_MODEL in rendered
        assert SECRET_API_KEY not in rendered
        assert env_secret not in rendered
        assert SECRET_API_KEY not in err.message
        assert env_secret not in err.message
        assert "[REDACTED]" in rendered

    def test_sanitize_llm_error_message_preserves_model_name(self):
        cleaned = sanitize_llm_error_message(
            f"Model {INVALID_MODEL} rejected token {SECRET_API_KEY}",
            extra_secrets=("my-custom-key-abcdef",),
            preserve_tokens=(INVALID_MODEL,),
        )
        assert INVALID_MODEL in cleaned
        assert SECRET_API_KEY not in cleaned

    def test_unhandled_start_exits_nonzero_in_subprocess(self):
        """Issue #5956: unhandled invalid llm in a script must exit non-zero, not 0."""
        code = (
            "from praisonaiagents import Agent; "
            "Agent(instructions='Reply OK', llm='   ').start('Hello')"
        )
        env = dict(os.environ)
        pkg_root = str(Path(__file__).resolve().parents[3])
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{pkg_root}{os.pathsep}{existing_pp}" if existing_pp else pkg_root
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        assert proc.returncode != 0
        assert "LLMError" in proc.stderr
