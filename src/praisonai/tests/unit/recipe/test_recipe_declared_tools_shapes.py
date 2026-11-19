"""The recipe tool policy sees every agent shape the executor runs.

``_execute_praisonai_workflow`` accepts ``agents`` as a dict or a list, and a
``tools`` value as a list or a single name. The policy check must collect
tools from each shape, or a recipe declares a denied tool in a shape the
check skips and the executor still loads it.
"""

import pytest

SHAPES = {
    "dict": "agents:\n  helper:\n    tools: [execute_command]\n",
    "list": "agents:\n  - name: helper\n    tools: [execute_command]\n",
    "list-str": "agents:\n  - name: helper\n    tools: execute_command\n",
    "dict-str": "agents:\n  helper:\n    tools: execute_command\n",
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_denied_tool_found_in_every_agent_shape(tmp_path, shape):
    from praisonai.recipe.core import _check_tool_policy
    from praisonai.recipe.models import RecipeConfig

    (tmp_path / "workflow.yaml").write_text(SHAPES[shape] + "tasks: []\n")
    cfg = RecipeConfig(name="t", version="1.0.0", path=str(tmp_path),
                       raw={"workflow": "workflow.yaml"}, requires={})
    err = _check_tool_policy(cfg, {"allow_dangerous_tools": False})
    assert err is not None and "execute_command" in err
    assert _check_tool_policy(cfg, {"allow_dangerous_tools": True}) is None


@pytest.mark.parametrize("opt_in", [False, True])
def test_template_tools_source_path_needs_template_opt_in(tmp_path, monkeypatch, opt_in):
    """A template's ``tools_sources`` path runs only with PRAISONAI_ALLOW_TEMPLATE_TOOLS,
    whichever caller builds the registry (the CLI gate alone left the builder open)."""
    from praisonai.templates.tool_override import create_tool_registry_with_overrides

    for name in ("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "PRAISONAI_ALLOW_LOCAL_TOOLS"):
        monkeypatch.delenv(name, raising=False)
    if opt_in:
        monkeypatch.setenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "true")
    marker = tmp_path / "ran"
    src = tmp_path / "cache" / "rogue_tools.py"
    src.parent.mkdir()
    src.write_text(f"open({str(marker)!r}, 'w').write('x')\ndef t():\n    return 1\n")
    create_tool_registry_with_overrides(tools_sources=[str(src)], include_defaults=False)
    assert marker.exists() is opt_in
