"""Exercise model selection through the real direct-prompt CLI dispatch."""

from types import SimpleNamespace

import praisonaiagents
import pytest

from praisonai.cli.legacy.direct_prompt import handle_direct_prompt


@pytest.mark.parametrize(
    "requested_model", [None, "gpt-image-2.5-flare"], ids=["default", "explicit"]
)
def test_direct_prompt_image_generation(monkeypatch, requested_model):
    calls = []
    result = {"data": [{"b64_json": "dGVzdA=="}]}

    class FakeImageAgent:
        def __init__(self, *, llm, **kwargs):
            self.model = llm

        def chat(self, prompt):
            calls.append((self.model, prompt))
            return result

    monkeypatch.setattr(praisonaiagents, "ImageAgent", FakeImageAgent)
    cli = SimpleNamespace(
        args=SimpleNamespace(
            image_generate=True,
            llm=requested_model,
            no_rules=True,
            no_tools=True,
            tool_timeout=0,
            tool_retry_attempts=1,
        ),
        _rewrite_query_if_enabled=lambda prompt: prompt,
        _expand_prompt_if_enabled=lambda prompt: prompt,
    )

    assert handle_direct_prompt(cli, "A blue square") == result
    assert calls == [("gpt-image-2.5-flare", "A blue square")]
