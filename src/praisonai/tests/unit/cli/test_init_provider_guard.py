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
