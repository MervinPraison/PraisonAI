"""Recipe tool policy sees tools in every agent layout a workflow can use.

A dangerous tool declared by an agent must hit the denied-by-default check
whether the agents are a mapping, a list, or the classic ``roles:`` mapping.
"""
import pytest

from praisonai.recipe.core import _check_tool_policy
from praisonai.recipe.models import RecipeConfig

LAYOUTS = {
    "dict": "agents:\n  helper:\n    tools: [execute_command]\n",
    "list": "agents:\n  - name: helper\n    tools: [execute_command]\n",
    "roles": "roles:\n  helper:\n    tools: [execute_command]\n",
}


def _recipe(tmp_path, text, **kw):
    (tmp_path / "workflow.yaml").write_text(text)
    return RecipeConfig(name="t", version="1.0.0", path=str(tmp_path),
                        raw={"workflow": "workflow.yaml"}, requires={}, **kw)


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_dangerous_tool_is_denied_in_every_layout(tmp_path, monkeypatch, layout):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    message = _check_tool_policy(_recipe(tmp_path, LAYOUTS[layout]), {})
    assert message and "execute_command" in message


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_explicit_allow_still_works(tmp_path, monkeypatch, layout):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    recipe = _recipe(tmp_path, LAYOUTS[layout], tools={"allow": ["execute_command"]})
    assert _check_tool_policy(recipe, {}) is None
