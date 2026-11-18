"""The two resolver families give the same answer (T-04).

``config.param_resolver.resolve_<param>`` (exported at the package root; the
``config.feature_configs`` versions delegate to it) and
``config.agent_init.resolve_agent_<param>`` (what ``Agent`` uses, with fast
paths) must not drift apart. They differ on purpose in one place only: for
``None`` the Agent supplies its own default where the generic resolver
returns ``None``. That difference is pinned here too.
"""
import pytest

from praisonaiagents.config import agent_init as A
from praisonaiagents.config import feature_configs as FC
from praisonaiagents.config import param_resolver as P

PAIRS = {
    "planning": (lambda v: P.resolve_planning(v, FC.PlanningConfig),
                 lambda v: A.resolve_agent_planning(v)[0],
                 [None, False, True, "reasoning", "read_only", {"reasoning": True}]),
    "reflection": (lambda v: P.resolve_reflection(v, FC.ReflectionConfig),
                   lambda v: A.resolve_agent_reflection(v)[0],
                   [None, False, True, "minimal", "standard", "thorough", {"max_iterations": 2}]),
    "web": (lambda v: P.resolve_web(v, FC.WebConfig),
            lambda v: A.resolve_agent_web(v)[0],
            [None, False, True, {"search": False}]),
    "caching": (lambda v: P.resolve_caching(v, FC.CachingConfig),
                lambda v: A.resolve_agent_caching(v)[0],
                [False, True, "prompt", {"enabled": False}]),
    "memory": (lambda v: P.resolve_memory(v, FC.MemoryConfig),
               A.resolve_agent_memory,
               [None, False, True, "file", {"backend": "file"}]),
    "execution": (lambda v: P.resolve_execution(v, FC.ExecutionConfig),
                  A.resolve_agent_execution,
                  [False, True, "fast", "thorough", {"max_iter": 3}]),
}
CASES = [(name, v) for name, (_, _, values) in PAIRS.items() for v in values]


def _outcome(fn, value):
    try:
        return ("ok", fn(value))
    except Exception as e:  # the same error type on both sides counts as agreeing
        return ("raises", type(e))


@pytest.mark.parametrize("name,value", CASES, ids=[f"{n}-{v!r}"[:40] for n, v in CASES])
def test_both_families_agree(name, value):
    generic, agent, _ = PAIRS[name]
    assert _outcome(generic, value) == _outcome(agent, value)


@pytest.mark.parametrize("name,config_class", [("caching", FC.CachingConfig), ("execution", FC.ExecutionConfig)])
def test_agent_supplies_a_default_for_none(name, config_class):
    generic, agent, _ = PAIRS[name]
    assert generic(None) is None
    assert agent(None) == config_class()
