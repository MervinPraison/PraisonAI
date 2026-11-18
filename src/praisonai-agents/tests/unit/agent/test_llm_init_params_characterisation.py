"""T-05 step 2d: pin the LLM settings dict (_llm_init_params) each branch of
Agent.__init__'s backend choice builds, before that code moves out. The
branches differ on purpose (dict routes forward only metrics/max_iter; the
base_url+dict route overrides a dict api_key, the plain dict route does not;
retry= never overrides a dict's own max_retries). Recorded on main 33d767a0ce.
"""
import pytest

from praisonaiagents import Agent

OPTS = {"metrics": False, "max_iter": 20, "web_search": None, "web_fetch": None,
        "prompt_caching": None, "claude_memory": None}

CASES = [
    ("base_url+str", dict(llm="gpt-4o-mini", base_url="http://x/v1", api_key="k"),
     ("gpt-4o-mini", True, {"model": "gpt-4o-mini", "base_url": "http://x/v1", "api_key": "k", "auth": None, **OPTS})),
    ("base_url+str+retry", dict(llm="gpt-4o-mini", base_url="http://x/v1", retry=False),
     ("gpt-4o-mini", True, {"model": "gpt-4o-mini", "base_url": "http://x/v1", "api_key": None, "auth": None,
                            **OPTS, "max_retries": 0})),
    ("base_url+dict", dict(llm={"model": "openai/m", "temperature": 0.2}, base_url="http://x/v1", api_key="k"),
     ("openai/m", True, {"model": "openai/m", "temperature": 0.2, "base_url": "http://x/v1", "api_key": "k",
                         "metrics": False, "max_iter": 20})),
    ("base_url+dict+retry", dict(llm={"model": "openai/m", "max_retries": 9}, base_url="http://x/v1", retry=False),
     ("openai/m", True, {"model": "openai/m", "max_retries": 9, "base_url": "http://x/v1",
                         "metrics": False, "max_iter": 20})),
    ("base_url+dict overrides dict key", dict(llm={"model": "openai/m", "api_key": "own"}, base_url="http://x/v1", api_key="k"),
     ("openai/m", True, {"model": "openai/m", "api_key": "k", "base_url": "http://x/v1", "metrics": False, "max_iter": 20})),
    ("base_url only", dict(base_url="http://x/v1"),
     ("gpt-4o-mini", True, {"model": "gpt-4o-mini", "base_url": "http://x/v1", "api_key": None, "auth": None, **OPTS})),
    ("dict", dict(llm={"model": "openai/m", "temperature": 0.2}, api_key="k"),
     ("openai/m", True, {"model": "openai/m", "temperature": 0.2, "api_key": "k", "metrics": False, "max_iter": 20})),
    ("dict+retry", dict(llm={"model": "openai/m"}, retry={"max_retries": 4}),
     ("openai/m", True, {"model": "openai/m", "metrics": False, "max_iter": 20, "max_retries": 4})),
    ("dict keeps own key", dict(llm={"model": "openai/m", "api_key": "own"}, api_key="k"),
     ("openai/m", True, {"model": "openai/m", "api_key": "own", "metrics": False, "max_iter": 20})),
    ("provider/model", dict(llm="anthropic/claude-3-haiku", api_key="k"),
     ("anthropic/claude-3-haiku", True, {"model": "anthropic/claude-3-haiku", "api_key": "k", **OPTS})),
    ("provider/model+retry+effort", dict(llm="anthropic/claude-3-haiku", retry=False, reasoning_effort="low"),
     ("anthropic/claude-3-haiku", True, {"model": "anthropic/claude-3-haiku", **OPTS, "max_retries": 0,
                                         "reasoning_effort": "low"})),
    ("plain", dict(llm="gpt-4o-mini"), ("gpt-4o-mini", False, None)),
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_MODEL_NAME"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("name,kwargs,expected", CASES, ids=[c[0] for c in CASES])
def test_init_params(name, kwargs, expected):
    agent = Agent(name="a", instructions="hi", **kwargs)
    assert (agent.llm, agent._using_custom_llm, agent._llm_init_params) == expected


def test_provider_prefixed_default_model_builds_an_llm(monkeypatch):
    monkeypatch.setattr(Agent, "_get_default_model", staticmethod(lambda: "anthropic/claude-3-haiku"))
    agent = Agent(name="a", instructions="hi")
    assert (agent.llm, agent._using_custom_llm, agent._llm_init_params) == (
        "anthropic/claude-3-haiku", True, {"model": "anthropic/claude-3-haiku", **OPTS})


def test_provider_model_keeps_the_tools(monkeypatch):
    def my_tool(x: str) -> str:
        """t"""
        return x
    agent = Agent(name="a", instructions="hi", llm="anthropic/claude-3-haiku", tools=[my_tool])
    assert my_tool in agent.tools
