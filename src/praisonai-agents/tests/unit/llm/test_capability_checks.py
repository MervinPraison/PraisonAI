"""Capability checks must return False, not crash, when LiteLLM can't answer."""

from unittest.mock import patch

import pytest

pytest.importorskip("litellm")

from praisonaiagents.llm.llm import LLM


@pytest.mark.parametrize("method", ["can_use_tools", "can_use_stop_words"])
def test_capability_check_returns_false_for_unknown_model(method):
    llm = LLM(model="my-custom-provider/unknown-model")
    # LiteLLM returns None for models it doesn't know about.
    # Patch by import path so we hit whatever litellm is currently in sys.modules
    # (other tests may have swapped the module object).
    with patch("litellm.get_supported_openai_params", return_value=None):
        assert getattr(llm, method)() is False


@pytest.mark.parametrize("method", ["can_use_tools", "can_use_stop_words"])
def test_capability_check_returns_false_when_litellm_raises(method):
    llm = LLM(model="gpt-4o-mini")
    with patch("litellm.get_supported_openai_params", side_effect=RuntimeError("boom")):
        assert getattr(llm, method)() is False
