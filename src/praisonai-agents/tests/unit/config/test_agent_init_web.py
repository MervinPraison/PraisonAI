"""G-19: the web= block of Agent.__init__ as a pure function.

Expected values were measured on main before the move. The resolver returns
what the block computed before Agent's later model check (which turns a
default fetch off for models without web fetch).
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_web
from praisonaiagents.config.feature_configs import WebConfig


def _shape(result):
    config, search, fetch, provider, fetch_is_default = result
    cfg = None if config is None else (
        type(config).__name__, config.search, config.fetch)
    return cfg, search, fetch, provider, fetch_is_default


@pytest.mark.parametrize("value, expected", [
    (None, (None, None, None, "duckduckgo", False)),
    (False, (None, False, False, "duckduckgo", False)),
    (True, (("WebConfig", True, True), True, True, "duckduckgo", True)),
    (WebConfig(search=False), (("WebConfig", False, True), False, True, "duckduckgo", False)),
    (WebConfig(fetch=True, search_provider="google"),
     (("WebConfig", True, True), True, True, "google", False)),
    ({"search": True}, (("WebConfig", True, True), True, True, "duckduckgo", True)),
    ({"fetch": True}, (("WebConfig", True, True), True, True, "duckduckgo", False)),
    ("tavily", (("WebConfig", True, False), True, False, "tavily", False)),
    ("search_only", (("WebConfig", True, False), True, False, "duckduckgo", False)),
])
def test_resolve_agent_web(value, expected):
    assert _shape(resolve_agent_web(value)) == expected


def test_web_config_passes_through_unchanged():
    wc = WebConfig(search=False)
    assert resolve_agent_web(wc)[0] is wc


@pytest.mark.parametrize("value", [None, False, True, {"search": True}, "tavily", "search_only"])
def test_agent_stores_what_the_resolver_returns(monkeypatch, value):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", llm="gpt-4o-mini", web=value)
    config, search, _fetch, _provider, _default = resolve_agent_web(value)
    assert type(agent._web_config) is type(config)
    assert agent.web_search == search
