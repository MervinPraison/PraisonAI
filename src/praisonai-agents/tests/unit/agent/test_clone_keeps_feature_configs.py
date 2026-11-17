"""clone_for_channel() must keep every feature setting (F-19).

Every gateway / bot channel and HTTP invocation is served by a clone. The clone
read 11 ``self._<x>_config`` attributes that Agent never set, so each fell back
to its default: caching=False came back on, templates, planning, context,
knowledge, reflection, web, autonomy, output, hooks and skills were dropped.
Same class of bug as #4284 (guardrails).
"""

import warnings

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import TemplateConfig, WebConfig


def _hook(event):
    return None


CASES = {
    "caching": (dict(caching=False), lambda a: a.cache),
    "templates": (dict(templates=TemplateConfig(system="SYS {role}")), lambda a: a.system_template),
    "planning": (dict(planning=True), lambda a: a.planning),
    "context": (dict(context=True), lambda a: a._context_param),
    "knowledge": (dict(knowledge=["Paris is in France."]), lambda a: a._knowledge_sources),
    "reflection": (dict(reflection=True), lambda a: a.self_reflect),
    "web": (dict(web=WebConfig(search=True, fetch=False)), lambda a: (a.web_search, a.web_fetch)),
    "autonomy": (dict(autonomy=True), lambda a: a.autonomy_enabled),
    "output": (dict(output="verbose"), lambda a: (a.verbose, a._has_explicit_output_config)),
    "hooks": (dict(hooks=[_hook]), lambda a: a._hooks),
}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("name", sorted(CASES))
def test_clone_keeps_setting(name):
    kwargs, probe = CASES[name]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        agent = Agent(name="a", instructions="hi", **kwargs)
        clone = agent.clone_for_channel()
    assert probe(clone) == probe(agent), f"{name}: clone={probe(clone)!r} original={probe(agent)!r}"


def test_clone_keeps_skills(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    agent = Agent(name="a", instructions="hi", skills=[str(skills_dir)])
    assert agent.clone_for_channel()._skills == agent._skills == [str(skills_dir)]


def test_clone_does_not_share_a_user_context_manager():
    # A live ContextManager holds per-session ledger/history; sharing it would
    # leak one channel's context into another.
    from praisonaiagents.context import ContextManager

    cm = ContextManager(model="gpt-4o-mini")
    agent = Agent(name="a", instructions="hi", context=cm)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clone = agent.clone_for_channel()
    assert clone.context_manager is not None
    assert clone.context_manager is not cm
    assert agent.context_manager is cm


def test_default_output_stays_implicit_on_the_clone():
    # Defaults must not turn into an explicit output mode on the clone; start()
    # only auto-enables verbose in a terminal when output was not set.
    agent = Agent(name="a", instructions="hi")
    assert agent.clone_for_channel()._has_explicit_output_config is False
