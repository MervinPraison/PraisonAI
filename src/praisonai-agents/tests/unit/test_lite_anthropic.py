"""Tests for the Anthropic helper in praisonaiagents.lite."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.lite import create_anthropic_llm_fn


def test_default_model_and_leading_thinking_block():
    anthropic = MagicMock()
    create = anthropic.Anthropic.return_value.messages.create
    create.return_value = SimpleNamespace(content=[
        SimpleNamespace(type="thinking", thinking="", signature="sig"),
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="text", text=" world"),
    ])

    with patch.dict(sys.modules, {"anthropic": anthropic}):
        result = create_anthropic_llm_fn(api_key="k")([{"role": "user", "content": "hi"}])

    assert result == "hello world"
    assert create.call_args.kwargs["model"] == "claude-sonnet-5-5"


@pytest.mark.parametrize("sampling", [{"temperature": 0.5}, {"top_p": 0.8}, {"top_k": 5}])
def test_sonnet_55_rejects_sampling_before_calling_provider(sampling):
    anthropic = MagicMock()
    with patch.dict(sys.modules, {"anthropic": anthropic}):
        with pytest.raises(ValueError, match="does not support sampling"):
            create_anthropic_llm_fn(api_key="k", **sampling)(
                [{"role": "user", "content": "hi"}]
            )

    anthropic.Anthropic.return_value.messages.create.assert_not_called()


def test_explicit_anthropic_model_preserves_sampling():
    anthropic = MagicMock()
    with patch.dict(sys.modules, {"anthropic": anthropic}):
        create_anthropic_llm_fn(model="claude-sonnet-4-6", api_key="k", temperature=0.3)(
            [{"role": "user", "content": "hi"}]
        )

    request = anthropic.Anthropic.return_value.messages.create.call_args.kwargs
    assert request["model"] == "claude-sonnet-4-6"
    assert request["temperature"] == 0.3
