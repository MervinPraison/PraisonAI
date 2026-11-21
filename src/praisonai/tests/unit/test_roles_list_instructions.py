"""List-form roles preserve the documented instructions shorthand."""

from types import SimpleNamespace

from praisonai.agents_generator import AgentsGenerator
from praisonai.framework_adapters._config_builder import build_agent_specs


def test_list_roles_instructions_reach_agent_specs():
    source = SimpleNamespace(
        agent_yaml="""roles:
  - role: Researcher
    goal: Find evidence
    instructions: Use cited sources
  - role: Editor
    instructions: Ignored when explicit
    backstory: Experienced editor
""",
        cli_config=None,
        _is_strict=lambda: False,
    )
    config = AgentsGenerator._load_config(source)
    specs = build_agent_specs(config, "", {}, lambda value, **_: value)
    assert [(spec.role, spec.backstory) for spec in specs] == [
        ("Researcher", "Use cited sources"),
        ("Editor", "Experienced editor"),
    ]
