"""Tests for the Anthropic helper in praisonaiagents.lite."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
