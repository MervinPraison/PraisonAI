"""T-10: include() finds a local recipe even when agent_recipes is installed.

agent_recipes.get_template_path raises ValueError for a name it does not
ship. The local-path fallback ran only on ImportError, so with the package
installed a local recipe directory was never found and a missing recipe gave
"Template not found" instead of "Recipe not found".
"""
import sys
import types

import pytest

from praisonaiagents import Workflow
from praisonaiagents.workflows import include


@pytest.fixture
def agent_recipes_installed(monkeypatch, tmp_path):
    fake = types.ModuleType("agent_recipes")

    def get_template_path(name):
        raise ValueError(f"Template not found: {name}")

    fake.get_template_path = get_template_path
    monkeypatch.setitem(sys.modules, "agent_recipes", fake)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_local_recipe_is_found(agent_recipes_installed):
    for name, other in (("recA", "recB"), ("recB", "recA")):
        (agent_recipes_installed / name).mkdir()
        (agent_recipes_installed / name / "workflow.yaml").write_text(
            f"name: {name}\nsteps:\n  - include: {other}\n")
    res = Workflow(name="o", steps=[include("recA")]).run("go")
    assert res["status"] == "failed"
    assert "Circular include" in str(res["steps"])  # reached recB -> recA


def test_missing_recipe_still_says_recipe_not_found(agent_recipes_installed):
    res = Workflow(name="o", steps=[include("does-not-exist-t10")]).run("go")
    assert res["status"] == "failed"
    assert "Recipe not found: does-not-exist-t10" in res["error"]


def test_other_agent_recipes_errors_are_not_hidden(monkeypatch, tmp_path):
    # Only "not installed" (ImportError) and "not shipped" (ValueError) fall
    # back to a local path; a real fault in agent_recipes must surface.
    fake = types.ModuleType("agent_recipes")

    def get_template_path(name):
        raise RuntimeError("agent_recipes index is corrupt")

    fake.get_template_path = get_template_path
    monkeypatch.setitem(sys.modules, "agent_recipes", fake)
    monkeypatch.chdir(tmp_path)
    res = Workflow(name="o", steps=[include("anything")]).run("go")
    assert res["status"] == "failed"
    assert "agent_recipes index is corrupt" in str(res)
