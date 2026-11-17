"""G-19, skills block: Agent(skills=...) resolution as a pure function.
Expected values were recorded on the F-22 branch before the move."""

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_skills
from praisonaiagents.config.feature_configs import SkillsConfig

# (_skills, _skills_dirs, _skills_auto_discover, _skills_config type)
EXPECTED = [
    (None, (None, None, False, "NoneType")),
    (False, (None, None, False, "NoneType")),
    (42, (None, None, False, "NoneType")),
    (True, ([], [], False, "SkillsConfig")),
    ([], ([], [], False, "SkillsConfig")),
    (["a", "b"], (["a", "b"], [], False, "SkillsConfig")),
    ("./skills", (["./skills"], [], False, "SkillsConfig")),
    ("pdf", (["pdf"], [], False, "SkillsConfig")),
    ("@bundle", (["@bundle"], [], False, "SkillsConfig")),
    (SkillsConfig(paths=["x"], dirs=["d"], auto_discover=True), (["x"], ["d"], True, "SkillsConfig")),
    (SkillsConfig(dirs=["d"]), ([], ["d"], False, "SkillsConfig")),
    ({"paths": ["p"]}, (["p"], [], False, "SkillsConfig")),
    ({"dirs": ["d"], "auto_discover": True}, ([], ["d"], True, "SkillsConfig")),
]
IDS = [repr(v)[:30] for v, _ in EXPECTED]


@pytest.mark.parametrize("value,expected", EXPECTED, ids=IDS)
def test_agent_still_resolves_the_same(value, expected, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="hi", skills=value)
    got = (agent._skills, agent._skills_dirs, agent._skills_auto_discover,
           type(agent._skills_config).__name__)
    assert got == expected


@pytest.mark.parametrize("value,expected", EXPECTED, ids=IDS)
def test_resolver_matches_agent(value, expected):
    config, paths, dirs, auto = resolve_agent_skills(value)
    assert (paths, dirs, auto, type(config).__name__) == expected


def test_config_object_is_kept_as_is():
    cfg = SkillsConfig(paths=["x"])
    assert resolve_agent_skills(cfg)[0] is cfg
