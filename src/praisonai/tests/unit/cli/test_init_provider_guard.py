"""
Unit tests for the `praisonai --init` provider pre-flight guard.

Verifies that when no LLM provider credential is configured, the guard returns a
clear, actionable message (pointing at `praisonai setup`) instead of letting the
`--init` flow call the LLM and surface a raw stack trace. When a provider IS
configured, the guard must return None so generation proceeds.
"""

from unittest.mock import patch

import pytest

try:
    import praisonai.cli.main as cli_main
    from praisonai.cli.main import _provider_preflight_message
except ImportError as e:  # pragma: no cover - environment guard
    pytest.skip(f"Could not import praisonai.cli.main: {e}", allow_module_level=True)


class TestProviderPreflightMessage:
    def test_returns_message_when_unconfigured(self):
        with patch("praisonai.llm.credentials.is_configured", return_value=False):
            msg = _provider_preflight_message()

        assert msg is not None
        assert "No LLM provider is configured" in msg
        # Points beginners at the no-export interactive setup.
        assert "praisonai setup" in msg
        # Mentions multiple providers so users know it's not OpenAI-only.
        assert "Anthropic" in msg and "Gemini" in msg

    def test_returns_none_when_configured(self):
        with patch("praisonai.llm.credentials.is_configured", return_value=True):
            assert _provider_preflight_message() is None

    def test_never_blocks_on_internal_error(self):
        # If the credential check itself raises, the guard must not block a
        # potentially configured user (returns None -> generation proceeds).
        with patch(
            "praisonai.llm.credentials.is_configured",
            side_effect=RuntimeError("boom"),
        ):
            assert _provider_preflight_message() is None

    def test_injects_stored_credentials_before_gating(self):
        # A key stored via `praisonai setup` must be exported into the env
        # before gating, otherwise the env-only AutoGenerator path would still
        # fail with a raw auth error despite the guard passing.
        with patch(
            "praisonai.llm.credentials.inject_credentials_into_env"
        ) as inject, patch(
            "praisonai.llm.credentials.is_configured", return_value=True
        ):
            assert _provider_preflight_message() is None
            inject.assert_called_once()

    def test_gates_on_runtime_model_override(self):
        # With a stale OpenAI model override and only a non-OpenAI key, the
        # gate must use the exact runtime model so the mismatch is caught here
        # (message returned) rather than failing later at the LLM call.
        with patch.dict(
            "os.environ", {"MODEL_NAME": "gpt-4o-mini"}, clear=False
        ), patch(
            "praisonai.llm.credentials.inject_credentials_into_env"
        ), patch(
            "praisonai.llm.credentials.is_configured", return_value=False
        ) as is_configured:
            msg = _provider_preflight_message()

        assert msg is not None
        # The runtime model override must be passed through to the gate.
        is_configured.assert_called_once_with(model="gpt-4o-mini")


class TestInitGuardWiring:
    def test_init_returns_early_without_calling_generator(self):
        # The real --init path must print guidance and return early WITHOUT
        # constructing the AutoGenerator when no provider is configured. This
        # protects against the guard being removed or moved after generation.
        instance = cli_main.PraisonAI.__new__(cli_main.PraisonAI)
        instance.agent_file = "agents.yaml"
        instance.config_list = [{"model": "gpt-4o-mini"}]
        instance.framework = None
        instance.auto = False
        instance.init = False
        instance.topic = ""

        # Use a plain namespace (not MagicMock) so unset attributes don't read
        # as truthy and trip earlier branches before the --init guard.
        from types import SimpleNamespace

        args = SimpleNamespace(
            command=None,
            framework=None,
            model=None,
            prompt_flag=None,
            file=None,
            direct_prompt=None,
            deploy=False,
            auto=False,
            init="build me a team",
            ui=None,
            merge=False,
        )

        with patch.object(instance, "parse_args", return_value=(args, [])), patch.object(
            cli_main, "_load_env_once"
        ), patch.object(
            instance, "read_stdin_if_available", return_value=None
        ), patch.object(
            instance, "read_file_if_provided", return_value=None
        ), patch.object(
            cli_main, "_provider_preflight_message", return_value="SETUP GUIDANCE"
        ), patch.object(
            cli_main, "_get_auto_generator"
        ) as get_gen, patch("builtins.print"):
            result = instance.main()

        assert result == "SETUP GUIDANCE"
        get_gen.assert_not_called()
