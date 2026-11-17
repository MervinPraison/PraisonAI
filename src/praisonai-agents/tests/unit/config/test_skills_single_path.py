"""Agent(skills="path") resolves like skills=["path"] (F-22).

The resolver's "path_as_source" mode built config_class(sources=[path]), but
SkillsConfig names the field ``paths``: a single skill path raised
TypeError: SkillsConfig.__init__() got an unexpected keyword argument 'sources'.
"""

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import KnowledgeConfig, SkillsConfig
from praisonaiagents.config.param_resolver import resolve


def test_single_skill_path_string(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="hi", skills="./one")
    assert agent._skills == ["./one"]


def test_non_path_skill_string_is_not_dropped(monkeypatch):
    # Bare names and '@bundle' selectors are not path-like but are valid list items.
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert Agent(name="a", instructions="hi", skills="my-skill")._skills == ["my-skill"]
    assert Agent(name="a", instructions="hi", skills="@research")._skills == ["@research"]


def test_path_as_source_uses_the_config_field_that_exists():
    assert resolve(value="./one", param_name="skills", config_class=SkillsConfig,
                   string_mode="path_as_source").paths == ["./one"]
    assert resolve(value="./doc.md", param_name="knowledge", config_class=KnowledgeConfig,
                   string_mode="path_as_source").sources == ["./doc.md"]
