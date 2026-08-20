"""One rule for the llm=/model= alias pair, across every class that has it."""
import importlib
import pytest

from praisonaiagents.config import LLMConfig

MODULES = ("praisonaiagents", "praisonaiagents.agent",
           "praisonaiagents.agents", "praisonaiagents.workflows")
# classes that store a bare model name (so an LLMConfig must be unwrapped)
UNWRAPPING = ["Agent", "ImageAgent", "ContextAgent", "VisionAgent", "AudioAgent",
              "OCRAgent", "VideoAgent", "EmbeddingAgent", "CodeAgent", "RealtimeAgent"]
ALL = UNWRAPPING + ["AgentTeam", "AgentFlow"]


def _cls(name):
    for m in MODULES:
        try:
            return getattr(importlib.import_module(m), name)
        except (ImportError, AttributeError):
            pass
    raise AssertionError(f"{name} not importable")


def _extra(name):
    """Minimum kwargs needed to construct each class at all."""
    if name in ("Agent", "ImageAgent", "ContextAgent"):
        return {"instructions": "t"}
    if name == "AgentTeam":
        return {"agents": [_cls("Agent")(instructions="t")]}
    return {}


@pytest.mark.parametrize("name", ALL)
def test_passing_both_is_refused(name):
    with pytest.raises(TypeError, match="both llm= and model="):
        _cls(name)(llm="gpt-4o", model="gpt-3.5-turbo", **_extra(name))


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("kw", ["model", "llm"])
def test_either_name_alone_is_honoured(kw, name):
    assert _cls(name)(**{kw: "gpt-4o"}, **_extra(name)).llm == "gpt-4o"


@pytest.mark.parametrize("name", UNWRAPPING)
def test_llmconfig_is_unwrapped_to_a_model_string(name):
    # Otherwise the LLMConfig object itself is handed to litellm as model=.
    assert _cls(name)(llm=LLMConfig(model="gpt-4o"), **_extra(name)).llm == "gpt-4o"
