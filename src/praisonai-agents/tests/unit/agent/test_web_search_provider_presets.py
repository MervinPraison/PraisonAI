"""X-01: the web search provider preset picks the search tool.

``web="duckduckgo"``, ``"tavily"``, ``"google"``, ``"bing"`` and ``"serper"``
built identical agents with the DuckDuckGo tool: ``WebConfig.search_provider``
was set by the presets and read nowhere. Now ``"tavily"`` gives the Tavily
search tool when it is installed and ``TAVILY_API_KEY`` is set; a provider
with no built-in tool, or Tavily without its key or package, keeps DuckDuckGo
and says so in a warning (a build that works today still works).
"""

import logging

import pytest

from praisonaiagents import Agent
from praisonaiagents.tools import tavily_tools


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


def _tool_names(**kwargs):
    agent = Agent(name="w", instructions="x", llm="gpt-4o-mini", **kwargs)
    return [getattr(t, "__name__", getattr(t, "name", None)) for t in agent.tools]


def test_tavily_preset_uses_tavily_when_available(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-local-fake")
    monkeypatch.setattr(tavily_tools, "_check_tavily_available", lambda: (True, None))
    names = _tool_names(web="tavily")
    assert "tavily_search" in names and "internet_search" not in names


def test_tavily_without_key_keeps_duckduckgo_and_says_why(monkeypatch, caplog):
    # Report the package as installed so the real key check runs whether or
    # not tavily-python is present in this environment.
    real_find_spec = tavily_tools.util.find_spec
    monkeypatch.setattr(tavily_tools.util, "find_spec",
                        lambda name, *a: object() if name == "tavily" else real_find_spec(name, *a))
    with caplog.at_level(logging.WARNING):
        names = _tool_names(web="tavily")
    assert names.count("internet_search") == 1
    assert any("tavily" in r.getMessage().lower() and "TAVILY_API_KEY" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("provider", ["google", "bing", "serper"])
def test_provider_without_a_tool_keeps_duckduckgo_and_says_why(provider, caplog):
    with caplog.at_level(logging.WARNING):
        names = _tool_names(web=provider)
    assert names.count("internet_search") == 1
    assert any(provider in r.getMessage() and "DuckDuckGo" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("web", ["duckduckgo", True], ids=["duckduckgo", "true"])
def test_default_provider_unchanged_and_quiet(web, caplog):
    with caplog.at_level(logging.WARNING):
        names = _tool_names(web=web)
    assert names.count("internet_search") == 1
    assert not [r for r in caplog.records if "DuckDuckGo" in r.getMessage() and r.levelno >= logging.WARNING]
