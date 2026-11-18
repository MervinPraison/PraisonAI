"""The two resolver families give the same answer (T-04).

``config.param_resolver.resolve_<param>`` (exported at the package root; the
``config.feature_configs`` versions delegate to it) and
``config.agent_init.resolve_agent_<param>`` (what ``Agent`` uses, with fast
paths) must not drift apart. They differ on purpose in one place only: for
``None`` the Agent supplies its own default where the generic resolver
returns ``None``; and ``resolve_agent_execution`` falls back to the defaults
for an unknown preset name, because ``Agent`` has already rejected it. Those
differences are pinned here too.
"""
import pytest

from praisonaiagents.config import agent_init as A
from praisonaiagents.config import feature_configs as FC
from praisonaiagents.config import param_resolver as P

PAIRS = {
    "planning": (lambda v: P.resolve_planning(v, FC.PlanningConfig),
                 lambda v: A.resolve_agent_planning(v)[0],
                 [None, False, True, "reasoning", "read_only", "READ_ONLY", {"reasoning": True},
                  ["reasoning", {"auto_approve": True}]]),
    "reflection": (lambda v: P.resolve_reflection(v, FC.ReflectionConfig),
                   lambda v: A.resolve_agent_reflection(v)[0],
                   [None, False, True, "minimal", "standard", "thorough", "THOROUGH",
                    {"max_iterations": 2}, ["minimal", {"max_iterations": 4}]]),
    "web": (lambda v: P.resolve_web(v, FC.WebConfig),
            lambda v: A.resolve_agent_web(v)[0],
            [None, False, True, {"search": False}]),
    "caching": (lambda v: P.resolve_caching(v, FC.CachingConfig),
                lambda v: A.resolve_agent_caching(v)[0],
                [False, True, "prompt", "PROMPT", {"enabled": False}]),
    "memory": (lambda v: P.resolve_memory(v, FC.MemoryConfig),
               A.resolve_agent_memory,
               [None, False, True, "file", "FILE", {"backend": "file"}, ["file", {"user_id": "u"}]]),
    "execution": (lambda v: P.resolve_execution(v, FC.ExecutionConfig),
                  A.resolve_agent_execution,
                  [False, True, "fast", "FAST", "thorough", {"max_iter": 3}, ["fast", {"max_iter": 3}]]),
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


def test_unknown_execution_preset_is_rejected_before_the_agent_resolver():
    # The generic resolver raises; the Agent resolver falls back to defaults
    # because Agent validates preset strings first. Users see the same error.
    from praisonaiagents import Agent
    with pytest.raises(ValueError):
        P.resolve_execution("bogus", FC.ExecutionConfig)
    assert A.resolve_agent_execution("bogus") == FC.ExecutionConfig()
    with pytest.raises(ValueError):
        Agent(name="x", instructions="y", execution="bogus")


@pytest.mark.parametrize("value", [5, 1.5, object()])
@pytest.mark.parametrize("name,config_class", [("caching", FC.CachingConfig), ("execution", FC.ExecutionConfig)])
def test_unrecognised_type_falls_back_to_the_agent_default(name, config_class, value):
    # The Agent resolver passes its default down for a value resolve() does not
    # recognise; the generic resolver keeps returning None for it unless asked.
    generic, agent, _ = PAIRS[name]
    assert generic(value) is None
    assert agent(value) == config_class()
    assert getattr(P, f"resolve_{name}")(value, config_class, default=config_class()) == config_class()


def test_agent_resolvers_delegate_to_param_resolver(monkeypatch):
    # One body per parameter: resolve_agent_<param> calls resolve_<param> for
    # anything its fast paths do not handle (T-04 step 2).
    calls = []
    for name in ("planning", "reflection", "web", "caching", "memory", "execution"):
        real = getattr(P, f"resolve_{name}")
        monkeypatch.setattr(A, f"resolve_{name}",
                            lambda *a, _n=name, _r=real, **k: calls.append(_n) or _r(*a, **k))
    A.resolve_agent_planning({"reasoning": True})
    A.resolve_agent_reflection({"max_iterations": 2})
    A.resolve_agent_web({"search": False})
    A.resolve_agent_caching({"enabled": False})
    A.resolve_agent_memory({"backend": "file"})
    A.resolve_agent_execution({"max_iter": 3})
    assert calls == ["planning", "reflection", "web", "caching", "memory", "execution"]
