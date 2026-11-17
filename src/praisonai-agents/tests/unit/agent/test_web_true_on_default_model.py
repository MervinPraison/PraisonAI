"""X-14: ``web=True`` works on a model without native web fetch.

``True`` means "sensible defaults", which turned on both search and fetch;
fetch is Claude-only, so ``Agent(web=True)`` on the default model raised
``ValueError``. Now ``web=True`` (and a dict that does not mention fetch)
enables what the model supports and logs once that fetch was left off. An
explicit request for fetch still raises.
"""

import logging

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import WebConfig


@pytest.fixture(autouse=True)
def _key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))


@pytest.mark.parametrize("web", [True, {"search": True}], ids=["true", "dict_without_fetch"])
def test_default_web_on_openai_model_keeps_search(web, caplog):
    with caplog.at_level(logging.INFO):
        agent = Agent(name="w", instructions="x", llm="gpt-4o-mini", web=web)
    assert agent.web_search and not agent.web_fetch
    assert any("fetch" in r.getMessage() and "gpt-4o-mini" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("web", [WebConfig(fetch=True), {"fetch": True}, "fetch_only"],
                         ids=["config", "dict", "preset"])
def test_explicit_fetch_on_openai_model_still_raises(web):
    with pytest.raises(ValueError, match="web_fetch is only supported"):
        Agent(name="w", instructions="x", llm="gpt-4o-mini", web=web)


def test_web_true_on_claude_keeps_fetch(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-local-fake")
    agent = Agent(name="w", instructions="x", llm="anthropic/claude-sonnet-4-5", web=True)
    assert agent.web_search and agent.web_fetch


def test_custom_llm_route_also_leaves_fetch_off():
    agent = Agent(name="w", instructions="x", llm="openai/gpt-4o-mini", base_url="http://127.0.0.1:9/v1",
                  api_key="x", web=True)
    assert not agent.web_fetch
    assert getattr(agent.llm_instance, "web_fetch", False) is False
    assert agent._llm_option_kwargs.get("web_fetch") is False
